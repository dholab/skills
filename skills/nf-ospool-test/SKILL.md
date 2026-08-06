---
name: nf-ospool-test
description: Use when you want to verify a CHTC / OSPool Nextflow setup actually works BEFORE launching a long real run — a live smoke test that submits one tiny throwaway job through the nf-ospool executor and confirms it lands on a HasCHTCStaging node, resolves a symlinked /staging input, writes output back, and completes. Catches the instant-crash and multi-day ghost-job hang failure modes early. Companion to the nf-ospool skill.
license: MIT
compatibility: Requires Python 3, Nextflow 25.10+, Java, the nf-ospool executor plugin, and access to UW-Madison CHTC / OSPool with the CHTC /staging filesystem.
---

# nf-ospool-test (live smoke test)

## Overview

A one-command probe that proves the CHTC/OSPool staging path is healthy before you commit to a multi-day run. It submits a real but trivial (1 cpu / 2 GB / <1 min) Nextflow task through the `ospool` executor and checks the three things that fail silently in production:

1. the job matches a **HasCHTCStaging** node (real `requirements` expression, not a bare attribute),
2. a **symlinked `/staging` input** resolves on the execute node,
3. the task **writes back to `/staging`** and Nextflow sees the `.exitcode` completion signal.

If all three pass, the run you're about to launch will not hit the instant-crash or the ghost-job hang. See the **nf-ospool** skill for the underlying design and full debugging playbook.

## When to use

- Before launching any new/edited CHTC OSPool Nextflow workflow, especially after changing `clusterOptions`, `requirements`, `pathMappings`, `workDir`, or `submitFileDir`.
- After a pool/AP change, or when a previous run mysteriously hung with `condor_q` empty.
- NOT for validating pipeline logic — it only tests the executor/staging plumbing.

## Run it

`smoke_test.py` sits next to this `SKILL.md` in the skill's own directory — wherever
your agent installed it (e.g. `~/.claude/skills/nf-ospool-test/` for Claude Code,
`~/.agents/skills/nf-ospool-test/` for other agents). Substitute that path below.

```bash
# From a dir containing your nextflow.config (auto-detects accounting group + /staging group):
pixi run python <skill-dir>/smoke_test.py

# Or pass explicitly:
python <skill-dir>/smoke_test.py \
    --staging-dir /staging/groups/<group>/nf-ospool-smoke \
    --accounting-group <YourLab_Group>
```

Useful flags: `--timeout <sec>` (default 900), `--keep` (don't delete temp dirs), `--nextflow "<cmd>"` (default `nextflow`).

**Run it inside the same environment as your real runs** (e.g. `pixi run python ...`). The plugin needs Nextflow **≥ 25.10.0** and a Java VM on `PATH`; a bare `nextflow` from a global install is often too old (you'll get `Plugin nf-ospool requires Nextflow version >=25.10.0`) or missing Java. Using `pixi run` from your project dir activates the correct Nextflow + Java for the whole process tree regardless of where the temp launch dir lives.

## Reading the result

| Outcome | Meaning | Next step |
|---|---|---|
| **PASS** | Probe ran on a staging node, read the `/staging` symlink, wrote output, exited 0 | Safe to launch the real run |
| **FAIL** | Task errored fast. If `.command.begin` is absent, it landed on a non-staging node (dangling symlink) | Check `requirements` is a real expression `(Target.HasCHTCStaging == true)`, not a bare `HasCHTCStaging=true` |
| **HANG** | Job left the queue but `.exitcode` never appeared → Nextflow polls forever | The ghost-job hang — fix the staging `requirements` so tasks only run where `/staging` is writable |

## What it does behind the scenes

Generates a throwaway `main.nf` + `nextflow.config` in a temp dir under `$HOME` (never `/staging` — HTCondor can't submit from there), stages a probe file onto `/staging`, runs `nextflow run`, then inspects the task work dir (`.command.begin` / `.exitcode`) and `condor_q` to classify the outcome. Uses a regenerated **known-good** config (real `requirements`, live-detected `pathMappings` via `readlink -f /staging`) so a PASS is a clean reference, not a copy of a possibly-broken config. Cleans up both temp dirs unless `--keep`.

**It submits a real job.** Tiny and short, but it consumes a slot briefly and writes under `/staging/groups/<group>/nf-ospool-smoke/`. It will not touch your real run's work dir.
