---
name: chtc-oconnor-jobs
description: Use when running batch compute on CHTC HTCondor execute nodes with the OConnor accounting group — writing a .sub file, using condor_submit, building one-job-per-sample fan-outs, working under /staging/groups/oconnor_group, packaging a runtime for execute nodes, copying inputs to scratch, or planning canary, smoke, and full-campaign submissions.
license: MIT
compatibility: Requires access to a UW-Madison CHTC access point, the HTCondor command-line tools, and permission to use the OConnor accounting group and staging directory.
---

# Running CHTC / OConnor execute-node jobs

Use this pattern for batch campaigns submitted through the OConnor accounting group. Keep large data in an experiment-numbered staging directory, transfer each job's working inputs to the execute node, return only small results to the access point, and prove the workflow with a canary before scaling out.

## 1. Accounting group and where jobs land

- Submit under the OConnor accounting group: `+AccountingGroup = "Pathology_OConnor"`. This gives the campaign access to the OConnor group's dedicated capacity when compatible slots are available.
- OConnor nodes have a **72 h walltime cap**. Design each job to finish well under it or add checkpointing.
- Request only what a job needs. These fan-outs are often download- or IO-bound, so a small `request_cpus` value (1–2) matches more slots than 8. Match memory and disk to the measured working set plus headroom.

## 2. Data layout: `/staging` for big, access point for small

- Put **large inputs and outputs** in `/staging/groups/oconnor_group/<EXPERIMENT#>/`, using the same experiment number as the run. Do not scatter large files across unrelated staging paths.
- Keep orchestration and **small results** on the access point: submit files, queue TSVs, workers, per-job `status.tsv` or JSON files, and small diagnostic outputs. Submit jobs there and transfer their small products back there.
- Read staging usage from Ceph attributes rather than `df`:

  ```bash
  getfattr -n ceph.dir.rbytes /staging/groups/oconnor_group/<EXPERIMENT#>
  ```

## 3. Copy inputs to the execute node

Copy each input into `$_CONDOR_SCRATCH_DIR`, either with `transfer_input_files` or with an explicit copy at the beginning of the worker, and operate on the local copy. Streaming a large file from `/staging` throughout a job puts avoidable load on Ceph and makes the job more fragile. Transfer references, indexes, and runtimes before reading them.

## 4. Package the runtime as a self-contained tarball

Execute nodes may not have the required tools. Bundle the real binary and its shared libraries in a `.tar.gz`, transfer it, extract it into scratch, and invoke it with its own `LD_LIBRARY_PATH`. Assert the expected version on the execute node before doing real work:

```bash
actual_version="$($bin --version)"
[[ "$actual_version" == "$expected_version" ]] || exit 1
```

Set `bin` and `expected_version` explicitly in the worker. Watch for launcher stubs such as Pixi or Conda trampolines. Bundle the actual dynamically linked binary rather than a wrapper that expects the original environment.

## 5. Canary → smoke → full campaign

1. **Canary:** submit one representative job. Let it finish end to end and confirm it recorded `status=success` and produced a structurally valid output, such as the expected size or record count and a passing `gzip -t`.
2. **Smoke:** optionally submit a small handful of jobs to check concurrency, transfers, and external-service behavior under light parallelism.
3. **Full campaign:** submit the remainder only after the canary and smoke checks pass. Use late materialization to place a coarse upper bound on simultaneously materialized jobs, but do not mistake it for a precise external-service rate limit. Enforce strict request rates in the workload itself. Prefer patient retries over aggressive retry loops.

Make the preparer resumable: skip any sample whose status record already says success so rerunning the preparer queues only unfinished or failed work.

## 6. Return only small files to the access point

Use `transfer_output_remaps` to send small per-job products, such as status TSVs, summary JSON, or diagnostic FASTAs, to a results directory on the access point. Keep large per-job outputs in the experiment's staging directory.

Typical submit skeleton:

```text
universe = vanilla
executable = input/worker.sh
arguments = "$(sample) $(index_archive) $(runtime_archive)"
+AccountingGroup = "Pathology_OConnor"
requirements = (HasCHTCStaging == True)          # only if the job needs /staging
request_cpus = 2
request_memory = 4GB
request_disk = $(disk_kib)KB
log = logs/$(ClusterId).log
output = logs/$(ClusterId).$(ProcId).out
error = logs/$(ClusterId).$(ProcId).err
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_input_files = input/$(index_archive),input/$(runtime_archive)
transfer_output_files = $(sample).status.tsv,$(sample).summary.json
transfer_output_remaps = "$(sample).status.tsv=results/$(sample).status.tsv;$(sample).summary.json=results/$(sample).summary.json"
max_materialize = 10
notification = Never
queue sample,index_archive,runtime_archive,disk_kib from samples.queue.tsv
```

Create the `logs/` and `results/` directories before submission, and keep stdout and stderr bounded. Because the submit file transfers both products, have the worker always write `status.tsv` and `summary.json` on success and failure; failure records should include the reason. A landed result set is then self-describing and the campaign can resume without rerunning successful samples. The HTCondor event log and captured stderr still cover failures that occur before the worker can write its own status.

## 7. Verify, then delete regenerable intermediates

After verifying the outputs, remove large intermediates that can be regenerated from `/staging`, such as downloaded FASTQs, decompressed references, and scratch products. Keep what is expensive to recreate or serves as the provenance of record: status records, manifests, and intentionally retained diagnostic outputs.

Only delete data after confirming the retained outputs are valid and the inputs or build process are reproducible.

## Preflight checklist

- [ ] `+AccountingGroup = "Pathology_OConnor"` is set and resource requests are modest.
- [ ] Large data lives under `/staging/groups/oconnor_group/<EXPERIMENT#>/`; small results return to the access point.
- [ ] Inputs are copied to `$_CONDOR_SCRATCH_DIR` instead of streamed from `/staging` during execution.
- [ ] The runtime includes its libraries and its version is asserted on the execute node.
- [ ] A canary succeeded end to end before the full `condor_submit`.
- [ ] Late materialization is bounded, any strict external-service rate limit is enforced by the workload, retries are patient, and the preparer skips successful samples.
- [ ] HTCondor event logs, stdout, and stderr have bounded destinations on the access point.
- [ ] The worker creates every declared transfer output on both success and failure, with an explicit status and failure reason.
- [ ] Regenerable intermediates are deleted only after retained outputs are verified.
