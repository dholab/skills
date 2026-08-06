---
name: nf-ospool
description: Use when setting up, launching, or debugging a Nextflow workflow on UW-Madison CHTC / OSPool with the nf-ospool executor plugin — jobs that fail in seconds, a run that hangs with condor_q empty while Nextflow still shows tasks SUBMITTED, "Input file not found" / staging errors, HasCHTCStaging matchmaking, outputs landing in the wrong place, running tasks in a container (container_image vs process.container), understanding why sharedFilesystem is false, or writing the executor/config block from scratch.
license: MIT
compatibility: Requires Nextflow 25.10+ with the nf-ospool executor plugin and access to UW-Madison CHTC / OSPool; examples assume HTCondor and the CHTC /staging filesystem.
---

# nf-ospool (Nextflow on CHTC / OSPool)

## Overview

`nf-ospool` is a Nextflow executor plugin that submits tasks to UW-Madison CHTC's OSPool via HTCondor. Its whole model rests on one assumption: **the CHTC `/staging` filesystem is a shared filesystem that both the access point (AP) and the execute nodes can read and write.** Almost every failure below is a violation of that assumption.

**Core mental model:** Nextflow's work dir lives on `/staging`. The plugin runs in "restricted filesystem mode" — it **symlinks** `/staging` inputs into each task instead of transferring them, and the task's wrapper writes outputs, `.command.begin`, `.command.err`, and `.exitcode` **directly to the `/staging` work dir**. Nextflow decides a task is done by watching for its `.exitcode` file to appear there. If a task lands on a node where `/staging` isn't mounted, the symlinks dangle, the writes fail, `.exitcode` never appears, and Nextflow waits forever.

## The #1 gotcha (staging matchmaking)

`clusterOptions 'HasCHTCStaging=true'` **does not work.** In HTCondor submit syntax a bare `HasCHTCStaging=true` sets a job *attribute* — it has **zero effect on which machine the job matches**. Jobs scatter onto any node, and the ones that land on non-staging nodes die in ~2 seconds. To actually require staging-capable nodes you need a `requirements` *expression*:

```groovy
// WRONG — bare attribute, no matchmaking effect. Jobs land anywhere.
clusterOptions 'HasCHTCStaging=true'

// RIGHT — a real requirements expression constrains matchmaking.
clusterOptions '''
requirements = ((OpSysMajorVer == 8) || (OpSysMajorVer == 9)) && (Target.HasCHTCStaging == true)
+AccountingGroup = "YourLab_Group"
transfer_output_files = ""
'''
```

Note the **explicit parentheses** around the OS check: in ClassAd, `&&` binds tighter than `||`, so `A || B && C` means `A || (B && C)` — without the parens an OS8 node *without* staging can still match.

## Known-good executor config block

```groovy
process {
    executor = 'ospool'
}

executor {
    $ospool {
        // HTCondor CANNOT submit from /staging — keep submit files off it (on /home).
        submitFileDir = "${HOME}/.nextflow/ospool-submit"

        // /home is NOT visible to compute nodes. Any dir the tasks need that lives
        // under /home (e.g. a bundled binary) must be auto-staged onto /staging once
        // per run. Omit this if all inputs already live on /staging.
        autoStageDirectories = ["${projectDir}"]

        // /staging canonicalizes to the underlying cephfs mount; Nextflow would build
        // stage-in symlinks the nodes can't resolve. Map the canonical prefix back to
        // /staging. VERIFY the key on your AP with:  readlink -f /staging
        pathMappings = [ '/mnt/htc-cephfs/kernel/root/staging': '/staging' ]
    }
}

// Work dir MUST be on /staging (compute nodes can reach it). Launch from /home, not /staging.
workDir = "/staging/groups/<group>/<experiment>/work"
```

Per-process directives that matter:
```groovy
process FOO {
    publishDir "${params.outdir}", mode: 'copy'   // flat; add /${sample_id} only if you WANT subfolders
    clusterOptions '''
    requirements = ((OpSysMajorVer == 8) || (OpSysMajorVer == 9)) && (Target.HasCHTCStaging == true)
    +AccountingGroup = "YourLab_Group"
    transfer_output_files = ""
    '''
    errorStrategy 'retry'   // OSPool nodes get preempted/evicted
    maxRetries 2
}
```

**Why `transfer_output_files = ""`:** the wrapper already writes outputs to the `/staging` work dir. Without this line, HTCondor's default `ON_EXIT` transfer *also* copies every large output file back to the submit dir under `/home`, blowing your home quota. It is only safe *because* the `requirements` line guarantees `/staging` is mounted — the two directives are a pair.

## Containers

Two mutually exclusive ways to run each task in a container. Pick one.

**A. HTCondor-native — recommended on OSPool.** Pass the image as an HTCondor submit directive inside `clusterOptions`, and do **NOT** set `apptainer.enabled` or `process.container`. HTCondor/OSPool launches the whole task wrapper (`.command.run`, with its `/staging` symlink resolution) *inside* the image and auto-bind-mounts `/staging` for you.

```groovy
clusterOptions '''
requirements = ((OpSysMajorVer == 8) || (OpSysMajorVer == 9)) && (Target.HasCHTCStaging == true)
+AccountingGroup = "YourLab_Group"
container_image = docker://youruser/yourimage:tag
transfer_output_files = ""
'''
```

- nf-ospool does **not** emit `container_image` for you — you add it yourself.
- A `docker://` URL is pulled by HTCondor; a `.sif` file must sit on a node-accessible path (`/staging`), never `/home`.

**B. Nextflow-native — for apptainer HPC (e.g. Slurm), not the usual OSPool path.** Set `apptainer.enabled = true` + `process.container = "docker://..."`. Nextflow wraps the command in `apptainer exec`, and nf-ospool's wrapper builder fixes the bind mounts: it normalizes symlinked input paths and adds `-B <stagedPath>:<originalPath>` for each auto-staged directory so paths resolve inside the container. **Requires Singularity/Apptainer** — Docker is rejected when `autoStageDirectories` is in use.

**Rule of thumb:** on OSPool use A; reserve B for apptainer-based HPC clusters.

## Why the config looks weird: `sharedFilesystem = false` on a shared filesystem

`/staging` genuinely **is** a shared filesystem, and the plugin knows it — `isAccessibleFromComputeNodes()` whitelists `/staging`, and even in "restricted" mode the plugin **symlinks** `/staging` inputs (reads them in place; it does **not** HTCondor-transfer them). So why default `sharedFilesystem = false`?

Because CHTC's filesystem is *partially, conditionally, and topologically-disguised* shared, and Nextflow's `sharedFilesystem` is a single boolean that can only say "all shared" or "nothing shared." The plugin picks `false` ("assume closed"), then hand-codes the real, selective sharing:

- **Only some paths are shared.** `/staging` is; `/home` (your project, bundled binaries, secrets) is **not** visible on compute nodes. A `true` executor would wrongly assume `/home` is reachable → so the plugin auto-stages `/home` dirs onto `/staging` instead.
- **Only some nodes have `/staging`.** It's gated behind `HasCHTCStaging`. "Shared" is a property of the *node*, not the filesystem — which is why the `requirements` expression is load-bearing, and why tasks on non-staging nodes die instantly with dangling symlinks.
- **You can't submit from the shared part.** HTCondor blocks `condor_submit` from `/staging`, so `submitFileDir` must live on `/home` while `workDir` lives on `/staging`.
- **The shared part has a disguised path.** `/staging` is a fuse/cephfs symlink (`readlink -f /staging`); Nextflow canonicalizes to that cephfs path, which nodes and container bind-mounts can't use, so `pathMappings` rewrites it back to `/staging`.
- **Execution is in an isolated scratch sandbox** (`/var/lib/condor/execute/.../scratch`), not the work dir — so shared-FS mode's "run dir == work dir" premise is false regardless.

**Common misconception (correct this):** `sharedFilesystem = false` does **NOT** mean "transfer every file." For `/staging` the plugin **symlinks** (reads in place); it only stages/transfers the paths that are genuinely inaccessible (`/home`). The symlink-not-transfer behavior is the whole point of `/staging` — huge data you must not copy — and the reason the staging `requirements` matters so much.

## Debugging playbook

Run these in order when a run misbehaves. `<jobId>` comes from the Nextflow log line `Submitted process ... jobId: NNNNN.0`.

```bash
# 1. Is anything actually queued/running on HTCondor RIGHT NOW?
condor_q
#   -> empty WHILE Nextflow still runs & shows tasks SUBMITTED  = ghost-job hang (see below)
#   -> jobs in 'R'  = running (good; long runtime is normal for big inputs, NOT a hang)
#   -> jobs in 'H'  = held (usually disk/memory over-request; check HoldReason)

# 2. What actually happened to the jobs that left the queue?
condor_history <jobId> -af ClusterId JobStatus ExitCode RemoteWallClockTime DiskUsage MemoryUsage LastRemoteHost
#   JobStatus: 1=Idle 2=Running 3=Removed 4=Completed 5=Held
#   ExitCode 1 + RemoteWallClockTime 2-8s + MemoryUsage 0  = instant startup crash (staging not reachable)

# 3. Did the task actually start on the node? Look in its /staging work dir.
ls -la <workDir>          # workDir is in the Nextflow log's "Submitted process" line
#   .command.begin PRESENT  = node reached & wrote /staging (good)
#   .command.begin ABSENT but job left queue = node could NOT write /staging (the smoking gun)
#   .exitcode present = Nextflow's completion signal; its ABSENCE is why a run hangs

# 4. What requirements/resources were REALLY submitted?
cat <submitFileDir>/<hash>/.command.condor    # check the requirements line is an expression, not a bare attr

# 5. Full HTCondor event timeline for one job (submit/execute/evict/terminate/hold reason).
cat <submitFileDir>/<hash>/.condor.log

# 6. Sanity-check node placement: staging-capable nodes vs not.
condor_q -af ClusterId JobStatus RemoteHost
```

## Symptom → cause → fix

| Symptom | Root cause | Fix |
|---|---|---|
| Tasks die in ~2s, ExitCode 1, 0 memory, no output; `.command.begin` absent | Landed on a node without `/staging`; symlinked binary/inputs dangle; first command (often `chmod +x`) fails under `set -e` | Use a real `requirements = ... (Target.HasCHTCStaging == true)` expression, not a bare `HasCHTCStaging=true` |
| Run hangs for days; `condor_q` empty but Nextflow shows tasks `SUBMITTED` | Jobs left the queue but `.exitcode` never got written to `/staging` (node couldn't write there), so Nextflow's poller never sees completion | Fix the staging `requirements` (above), kill the hung run, relaunch with `-resume` |
| "Input file not found" on the node | `/staging` stage-in symlink points at the canonical cephfs path the node can't resolve | Set `pathMappings = ['<readlink -f /staging output>': '/staging']` |
| `chmod: cannot access './binary'` / binary not executable | `autoStageDirectories` copies with a plain copy that drops the exec bit | `chmod +x ./binary` at the top of the script (or the file lives under `/home`, invisible to nodes — must be auto-staged) |
| Huge transfers into `/home`, home quota fills | Default HTCondor `ON_EXIT` output transfer copying `/staging` outputs back to the submit dir | Add `transfer_output_files = ""` (safe only with the staging `requirements` in place) |
| Held jobs (`H`), HoldReason mentions disk/memory | `disk`/`memory` request too low for real input sizes | Raise `disk`/`memory`; note `/staging` inputs are symlinked so they don't count against scratch `disk`, but temp files + outputs do |
| `outdir` path contains a literal `${...}` | Single-quoted string in the config — Groovy does not interpolate single quotes | Use double quotes: `outdir = "/staging/.../${params.experiment}/..."` |
| "HTCondor cannot submit from /staging" / submit errors | `submitFileDir` or launch dir is on `/staging` | Put `submitFileDir` under `/home`; launch the run from `/home` |

## First-run setup checklist

1. Point Nextflow at the plugin release, e.g. `export NXF_PLUGINS_TEST_REPOSITORY="https://github.com/nrminor/nf-ospool/releases/download/<ver>/nf-ospool-<ver>-meta.json"` and add `plugins { id 'nf-ospool@<ver>' }`.
2. Verify the `pathMappings` key: `readlink -f /staging` → use that as the key.
3. `workDir` on `/staging`; `submitFileDir` on `/home`; launch from `/home`.
4. `requirements` expression with `Target.HasCHTCStaging == true` (parenthesized) + `+AccountingGroup` + `transfer_output_files = ""`.
5. `errorStrategy 'retry'`, `maxRetries 2` (OSPool preempts nodes).
6. Set `disk`/`memory` from *real* input sizes, not the smallest test sample.
7. After launch, immediately confirm health: `condor_q` shows jobs, and `.command.begin` appears in a work dir within a minute.

## References

- **Plugin source (public):** https://github.com/nrminor/nf-ospool — the design rationale lives in the source comments. Most useful files: `OspoolExecutor.groovy` (`isAccessibleFromComputeNodes`, staging-mode decision, config validation), `OspoolFileCopyStrategy.groovy` (symlink + path normalization), `OspoolWrapperBuilder.groovy` (container bind-mount building). The README lists the four OSPool constraints the plugin exists to solve.
- **Known-working config:** the `nvd` pipeline's `chtc_htc` profile (`~/.nvd/.../conf/chtc-template.config` or a generated `user.config`) is battle-tested on CHTC: `sharedFilesystem = false`, a real `requirements` expression, `transfer_output_files = ""`, `+AccountingGroup`, HTCondor-native `container_image`, and generous `disk`. Read it when in doubt about a directive.
