# Formal stages of the TC2 GPU Experiment Protocol

> **Current profile and historical-record boundary (2026-10-25)**
>
> The retained design and acceptance account below describes the earlier implementation. Its job IDs, source hashes, remote paths, command blocks and completion flags are historical. Exact original bytes are in the [archive index](../archive/index.json); they do not certify this refactored checkout.
>
> Current configurations are under configs/tc2_gpu/, and independent fingerprints are in configs/tc2_gpu/source_manifest.json. The current deployment is unavailable. Formal actions refuse execution without new source/environment acceptance. Historical SSH and submission examples below are not current connection instructions.
>
> Use the [current protocol](TC2_GPU_PROTOCOL.md), [naming rules](TC2_GPU_NAMING.md) and [archive guide](TC2_GPU_ARCHIVE.md) for current paths. Local read-only commands from the repository root are python -B scripts/run_tc2_gpu.py plan and python -B scripts/verify_archive_tc2_gpu.py.

## Historical design and acceptance account


This is the approved step-7 implementation. It completes the frozen 66-fit matrix in twelve separate stages, reusing the two accepted bottle results from pilot job 44024. It therefore plans 64 new fits. The original protocol, manifests, accepted scientific implementations, environment locks, pilot files and historical artifacts remain unchanged. The frozen `protocol_v2.json` filename retains its original identity; `tc2_gpu` is the current workflow name.

## Stage order and dependencies

Each stage requires the latest job of every preceding stage to have passed with the same design and seven experiment source fingerprints. A failed latest job never falls back to an older successful job. Only one job runs at a time. Submission and collection are explicit; completion never submits the next stage automatically.

| Order | Stage | Fits in this stage | New fits planned | Cumulative fits | Saved-score rows |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | B0 | 12 | 10 | 12 | 0 |
| 2 | H1 | 4 | 4 | 16 | 0 |
| 3 | H2 | 4 | 4 | 20 | 0 |
| 4 | C1 | 2 | 2 | 22 | 0 |
| 5 | I1_seed17 | 0 | 0 | 22 | 18 |
| 6 | R0 | 24 | 24 | 46 | 0 |
| 7 | C1R | 4 | 4 | 50 | 0 |
| 8 | C2 | 4 | 4 | 54 | 0 |
| 9 | F1 | 8 | 8 | 62 | 0 |
| 10 | I1_all_seeds | 0 | 0 | 62 | 54 |
| 11 | I2 | 0 | 0 | 62 | 36 |
| 12 | B0_LOCO | 4 | 4 | 66 | 0 |

The core checkpoint requires the first 22 fits and the 18-row I1 analysis. The standard checkpoint requires 62 fits and all three analyses. Full completion additionally requires the four LOCO fits. `step_7_complete` stays false until the last stage and all dependencies pass. These are experiment-completion checkpoints; cross-category statistics, figures, failure-case presentation and report writing belong to subsequent steps.

## Resources and scientific execution

All stages use MGPU-TC2, normal QoS, one node, one task and two CPUs. Each of the nine fitting stages requests one GPU, 24 GiB host memory and at most two hours. Each of the three saved-score stages requests no GPU, 8 GiB and at most fifteen minutes. Submission passes these stage-specific allocations explicitly to the common wrapper. Jobs must use the accepted dedicated Conda environment and remote project directory.

Formal fitting requires NVIDIA A40, driver 570.148.08 and CUDA build 12.8, with the accepted software and weights. Scientific seeds, layer choices, FP32 precision, batch sizes, chunk sizes, sampling and scoring remain those in the frozen matrix and accepted execution configuration. There is no CPU fallback or automatic adjustment of parameters, resources or chunks. A failure preserves its artifacts and stops the stage for review.

At least 20 GiB of free remote space and 8 GiB of free local space are required before the relevant operations. The eight three-layer caches are approximately 6.238 GiB for 3650 images, and all 66 prediction-map arrays are approximately 3.194 GiB before compression and metadata. Free filesystem space does not establish a personal quota; an unavailable quota query is recorded explicitly. Raw data, weights, temporary archives and older results also consume storage.

Before LOCO fitting, the controller checks original image dimensions and masks, records total and test-set pixel counts, and compares a conservative host-memory estimate with the fixed request. Insufficient resources stop execution for review. Original-resolution pixel evaluation is preserved.

## Immutable inputs and results

The controller verifies the accepted full-workflow job 44012, pilot job 44024, all 31 scientific source fingerprints, all six pilot source fingerprints, actual weights, environment locks and the remote compatibility snapshot. Publication accepts only seven new files and refuses conflicting existing bytes. Keep these seven files unchanged across the stage sequence; a later code correction requires a separately reviewed supplement.

Each fitting stage extracts or validates each required category cache, then invokes the accepted run and full saved-result verification entry points sequentially. The two accepted bottle results are never sent to the fit action: they receive full verification and byte-preservation checks. Other intact results may be reused by the accepted runner; corrupt or partial results are refused. Cache arrays stay on TC2.

The new files are `configs/experiments_tc2_gpu.json`, `scripts/experiments_tc2_gpu.py`, `scripts/analyze_scores_tc2_gpu.py`, `scripts/slurm/experiments_tc2_gpu.sh`, `scripts/collect_experiments_tc2_gpu.py`, `tests/test_experiments_tc2_gpu.py` and this document. The existing README and external PowerShell helper are the only existing files changed for this step.

## Saved-score analysis

I1_seed17 compares native, max and top_0.01 for six baseline PatchCore results. I1_all_seeds compares the same rules for eighteen baseline PatchCore results. I2 compares top_0.001 and top_0.05 for those eighteen results. The analyses use saved development and test scores, validate source identities, ordered samples and cache metadata, and independently reproduce image metrics within absolute 1e-12. Normal thresholds use the development-set 95th percentile and strict score-greater-than-threshold decisions. The new analysis reproduces the accepted NumPy 1.26 linear-percentile arithmetic across local NumPy versions.

Analysis reads no feature arrays, anomaly-map arrays or raw masks, imports no Torch and performs no fitting. Pixel metrics are explicitly referenced from the already verified source results. Outputs are five immutable files in `run/tc2_gpu/summaries/<stage>/<identity>/`: `analysis.json`, `analysis.csv`, `evidence.json`, `analysis.sha256` and `SUCCESS`. Identities bind source results, scores, rules, ordered rows and analysis sources. Complete, intact results can be skipped; unknown locks or corruption stop execution.

## User terminal operation

Run the external helper from a local PowerShell terminal. Start with B0 only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action RunExperiments -Stage B0
```

The helper performs read-only head-node checks, uploads the seven files with checksums, publishes absent or identical files, and submits exactly one selected stage. In the submission SSH session it enters and verifies the remote root, logs that directory and also passes it through `sbatch --chdir`. It then waits briefly and collects the current snapshot. A pending or running job is returned as partial evidence, never as acceptance. Passwords are entered only in the terminal.

Return the new local `terminal.txt` for review. When the job is still running, collect it again using its printed job ID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action CollectExperiments -JobId JOB_ID
```

After the returned stage is verified, submit the next named stage in the table. There is no automatic retry, resubmission or next-stage dispatch. `RunExperiments -Stage B0 -ValidateOnly` performs local packaging checks without network access or job submission. The read-only Python `plan --root <code-root>` command prints the fixed matrix without creating formal outputs.

## Bounded collection and acceptance

The collector exports a checksummed index followed by named pages. Each page contains at most four whole result directories, and both compressed and decompressed page sizes are limited to 512 MiB. Larger groups split into smaller pages; a single result that exceeds the limit is refused. The limit is never increased automatically. Only published result files, the relevant cache metadata and completion markers, frozen manifest bytes, experiment configuration, analysis outputs and selected job evidence may be exported. Raw images, masks and NPY feature arrays remain remote.

The helper pins the index hash, downloads every listed page, validates archive paths, member types, sizes and hashes, and verifies each page before accepting the collection. Missing, duplicated, mixed or corrupt pages cannot complete a stage. A page receipt alone does not establish collection acceptance. All pages must agree on export identity, stage, job and selected result identities. The latest remote dependency chain is checked again before a full-completion export.

Job evidence uses `run/validation_tc2_gpu/step7_job_<job>/`, with pointers `last_experiments_<stage>_job.txt` in the same validation directory. Formal fits retain their existing identity directories under `run/tc2_gpu/results/`. The last-stage download proves the current stage and remote dependency evidence; local acceptance of all 66 fits additionally requires the verified collections from the earlier stages. Local audit records use `run/validation_tc2_gpu/step7_20261019/`.

## Current status

Local implementation and offline verification are recorded separately from remote acceptance. No step-7 formal stage has been accepted by this implementation record. The first submission is B0, and all twelve returned stage collections must be reviewed before step 7 is complete.
