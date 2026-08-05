#!/usr/bin/env python3
"""
nf-ospool smoke test
====================

Submits ONE tiny throwaway Nextflow task through the real `ospool` executor to
prove the CHTC/OSPool staging path is healthy *before* you launch a multi-day run.

What it actually exercises (the exact chain that fails silently in production):
  1. nf-ospool parses the config and submits an HTCondor job with a real
     `requirements` expression pinning it to a HasCHTCStaging node.
  2. The task gets a `path` input that lives on /staging, so nf-ospool SYMLINKS
     it into the sandbox. The task must resolve that symlink on the execute node
     (fails if it lands on a non-staging node -> dangling symlink).
  3. The task writes output back to the /staging work dir, and Nextflow detects
     completion via the `.exitcode` file appearing there (the signal whose
     absence causes the classic multi-day hang).

If the task succeeds, all three worked -> the staging path is healthy.

Outcomes:
  PASS  - task ran on a staging node, read the /staging probe, wrote output back.
  FAIL  - task errored fast (usually landed on a non-staging node: dangling
          symlink, or could not write /staging).
  HANG  - job left the HTCondor queue but `.exitcode` never appeared, so Nextflow
          polls forever. This is the ghost-job hang from the nf-ospool skill.

This submits a real (1 cpu / 2 GB / <1 min) job and cleans up after itself.
See the `nf-ospool` skill for the full design rationale and debugging playbook.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# --------------------------------------------------------------------------- #
# Config discovery
# --------------------------------------------------------------------------- #
def detect_from_config(config_path: Path) -> dict:
    """Best-effort scrape of an existing nextflow.config for sane defaults.

    We only pull the two values that vary per lab/AP: the AccountingGroup and the
    /staging group directory (derived from the existing workDir). Everything else
    (requirements, pathMappings) is regenerated known-good so the smoke test is a
    clean reference, not a copy of a possibly-broken config.
    """
    found = {}
    if not config_path.is_file():
        return found
    text = config_path.read_text()

    m = re.search(r'\+AccountingGroup\s*=\s*"([^"]+)"', text)
    if m:
        found["accounting_group"] = m.group(1)

    # workDir = "/staging/groups/<group>/<experiment>/..."  -> take the group root
    m = re.search(r'workDir\s*=\s*["\']([^"\']*/staging/groups/[^"\']+)', text)
    if m:
        parts = Path(m.group(1)).parts
        # .../staging/groups/<group>/...  -> keep up to <group>
        if "groups" in parts:
            i = parts.index("groups")
            group_root = Path(*parts[: i + 2])  # /staging/groups/<group>
            found["staging_dir"] = str(group_root / "nf-ospool-smoke")
    return found


def staging_canonical_prefix() -> str:
    """The cephfs prefix /staging resolves to on THIS access point.

    Used as the pathMappings key. Varies per AP (e.g. /kernel/ vs /fuse/), so we
    read it live instead of hardcoding.
    """
    try:
        real = subprocess.run(
            ["readlink", "-f", "/staging"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return real or "/mnt/htc-cephfs/kernel/root/staging"
    except Exception:
        return "/mnt/htc-cephfs/kernel/root/staging"


# --------------------------------------------------------------------------- #
# Smoke pipeline generation
# --------------------------------------------------------------------------- #
MAIN_NF = '''\
nextflow.enable.dsl = 2

// Minimal probe. The input file lives on /staging, so nf-ospool symlinks it into
// the task sandbox; the task must resolve that symlink on the execute node and
// write output back to the /staging work dir. This is the exact path that fails
// (silently) when a task lands on a node without /staging.
process SMOKE {
    executor 'ospool'
    cpus   1
    memory '2 GB'
    disk   '1 GB'
    time   '10m'

    clusterOptions """
    requirements = ((OpSysMajorVer == 8) || (OpSysMajorVer == 9)) && (Target.HasCHTCStaging == true)
    +AccountingGroup = "${params.accounting_group}"
    transfer_output_files = ""
    """

    // Fail fast: we WANT to see a staging failure, not have retries hide it.
    errorStrategy 'terminate'

    publishDir "${params.outdir}", mode: 'copy'

    input:
    path probe

    output:
    path 'smoke_result.txt'

    script:
    """
    {
      echo "node=\\$(hostname)"
      echo "probe_seen=\\$(cat ${probe})"
      echo "staging_write=ok"
    } > smoke_result.txt
    """
}

workflow {
    probe = file(params.probe, checkIfExists: true)
    SMOKE(probe)
}
'''


def config_nf(staging_dir: str, submit_dir: str, mapping_key: str) -> str:
    return f'''\
plugins {{ id 'nf-ospool@0.1.0' }}

process {{ executor = 'ospool' }}

executor {{
    $ospool {{
        submitFileDir = '{submit_dir}'
        pathMappings  = [ '{mapping_key}': '/staging' ]
    }}
}}

// Work dir MUST be on /staging (compute nodes reach it).
workDir = '{staging_dir}/work'
'''


# --------------------------------------------------------------------------- #
# Verification helpers
# --------------------------------------------------------------------------- #
def condor_queue_empty() -> bool:
    """True if the current user has no jobs in the HTCondor queue."""
    try:
        out = subprocess.run(
            ["condor_q", "-totals"], capture_output=True, text=True, timeout=30
        ).stdout
        m = re.search(r"(\d+)\s+jobs;", out)
        return m is not None and int(m.group(1)) == 0
    except Exception:
        return False


def find_task_workdir(staging_dir: Path) -> Path | None:
    """Locate the single SMOKE task work dir under <staging>/work/<xx>/<hash>."""
    work = staging_dir / "work"
    if not work.is_dir():
        return None
    for two in work.iterdir():
        if two.is_dir() and len(two.name) == 2:
            for h in two.iterdir():
                if (h / ".command.sh").exists():
                    return h
    return None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="nf-ospool live smoke test")
    ap.add_argument("--staging-dir", help="/staging base for the smoke work dir + probe")
    ap.add_argument("--accounting-group", help='HTCondor +AccountingGroup value')
    ap.add_argument("--nextflow", default="nextflow", help="nextflow command (default: nextflow)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds before declaring HANG (default: 900)")
    ap.add_argument("--keep", action="store_true", help="keep temp dirs for inspection")
    args = ap.parse_args()

    # Fill defaults from ./nextflow.config when present, then CLI overrides.
    detected = detect_from_config(Path.cwd() / "nextflow.config")
    staging_dir = args.staging_dir or detected.get("staging_dir")
    accounting_group = args.accounting_group or detected.get("accounting_group")

    if not staging_dir or not accounting_group:
        print("ERROR: could not determine --staging-dir and/or --accounting-group.")
        print("       Run from a dir with a nextflow.config, or pass them explicitly:")
        print("       smoke_test.py --staging-dir /staging/groups/<grp>/nf-ospool-smoke \\")
        print("                     --accounting-group <YourLab_Group>")
        return 2

    staging_dir = Path(staging_dir)
    mapping_key = staging_canonical_prefix()

    # Launch dir must NOT be on /staging (HTCondor cannot submit from there).
    launch_dir = Path(tempfile.mkdtemp(prefix="nf-ospool-smoke-", dir=Path.home()))
    submit_dir = str(launch_dir / ".condor")
    probe = staging_dir / "probe.txt"

    print("nf-ospool smoke test")
    print(f"  staging dir      : {staging_dir}")
    print(f"  accounting group : {accounting_group}")
    print(f"  /staging maps from: {mapping_key}")
    print(f"  launch dir       : {launch_dir}")
    print()

    try:
        # Stage the probe input onto /staging and write the pipeline.
        staging_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text("staging-visible\n")
        (launch_dir / "main.nf").write_text(MAIN_NF)
        (launch_dir / "nextflow.config").write_text(
            config_nf(str(staging_dir), submit_dir, mapping_key)
        )

        cmd = [
            *args.nextflow.split(),
            "run", "main.nf",
            "-ansi-log", "false",
            "--probe", str(probe),
            "--accounting_group", accounting_group,
            "--outdir", str(launch_dir / "out"),
        ]
        print(f"launching probe job (timeout {args.timeout}s)...")
        start = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=launch_dir, timeout=args.timeout,
                capture_output=True, text=True,
            )
        except subprocess.TimeoutExpired:
            return report_hang(staging_dir)

        elapsed = int(time.time() - start)

        if proc.returncode == 0:
            result = launch_dir / "out" / "smoke_result.txt"
            node = "?"
            if result.exists():
                for line in result.read_text().splitlines():
                    if line.startswith("node="):
                        node = line.split("=", 1)[1]
            print()
            print(f"  PASS  probe ran on {node} in {elapsed}s")
            print("        staging symlink resolved + /staging write + .exitcode all OK")
            print("        -> the nf-ospool staging path is healthy; safe to launch.")
            return 0

        return report_fail(staging_dir, proc)

    finally:
        if args.keep:
            print(f"\n(kept: {launch_dir} and {staging_dir})")
        else:
            shutil.rmtree(launch_dir, ignore_errors=True)
            shutil.rmtree(staging_dir, ignore_errors=True)


def report_fail(staging_dir: Path, proc: subprocess.CompletedProcess) -> int:
    print()
    print("  FAIL  probe task errored.")
    wd = find_task_workdir(staging_dir)
    if wd is None:
        print("        no task work dir found on /staging.")
    else:
        began = (wd / ".command.begin").exists()
        exited = (wd / ".exitcode").exists()
        print(f"        workdir: {wd}")
        print(f"        .command.begin present: {began}   .exitcode present: {exited}")
        if not began:
            print("        -> .command.begin absent = the node could NOT write /staging.")
            print("           Most likely it landed on a non-staging node and the")
            print("           symlinked probe dangled. Check the `requirements` line is a")
            print("           real expression (Target.HasCHTCStaging == true), not a bare attr.")
        err = wd / ".command.err"
        if err.exists() and err.stat().st_size:
            print("        --- .command.err (tail) ---")
            print("        " + "\n        ".join(err.read_text().splitlines()[-8:]))
    tail = "\n        ".join((proc.stderr or "").splitlines()[-6:])
    if tail.strip():
        print("        --- nextflow stderr (tail) ---")
        print("        " + tail)
    return 1


def report_hang(staging_dir: Path) -> int:
    print()
    print("  HANG  probe did not finish within the timeout.")
    empty = condor_queue_empty()
    wd = find_task_workdir(staging_dir)
    exited = wd is not None and (wd / ".exitcode").exists()
    print(f"        condor_q empty: {empty}   .exitcode present: {exited}")
    if empty and not exited:
        print("        -> GHOST-JOB HANG: the job left the queue but never wrote")
        print("           .exitcode to /staging, so Nextflow polls forever. This is the")
        print("           multi-day hang from the nf-ospool skill. Fix the staging")
        print("           `requirements` so tasks only run on nodes that can write /staging.")
    else:
        print("        -> still genuinely running or queued; try a longer --timeout.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
