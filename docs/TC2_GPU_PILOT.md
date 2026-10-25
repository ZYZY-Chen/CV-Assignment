# Step 6: TC2 GPU Real-Data Cache and Pilot

The user approved this design before implementation. It applies the frozen **TC2 GPU Experiment Protocol** to the MVTec AD bottle category and two existing B0 entries. All new comments, messages, documentation, and records use English. Existing Chinese, frozen inputs, environment locks, accepted scientific sources, historical records, and the Git index are preserved.

## Approved scope

The pilot uses seed 17 and exactly the 100 normal training images stored in the frozen manifest. PaDiM uses layer1/2/3, 100 dimensions, and regularization 0.01. PatchCore uses layer2/3, a 0.05 exact greedy coreset, and nine support neighbors. Dimension and sampling seeds equal the run seed. Both runs evaluate all 42 normal development images and all 83 test images. The cache includes all 292 manifest images: 167 normal fit-pool images, 42 development images, and 83 test images. Caching the fit pool does not permit fitting outside the selected N100 list.

The exact run keys are B0_mvtec_ad_bottle_padim_s17_n100_B7B86DBB2043 and B0_mvtec_ad_bottle_patchcore_s17_n100_BBC2B85C2FA8. These are two of the frozen 66 fits. Successful outputs can be reused later only when their complete scientific/input/software/hardware identities match. No additional matrix stage, category, seed, hyperparameter scan, report, environment modification, or package/data download belongs to this step.

Raw layer1/2/3 FP32 cache storage is approximately 0.499 GiB. The uncompressed prediction maps occupy about 31.25 MiB per method. Formal artifacts use run/tc2_gpu/ on TC2; pilot acceptance records use fresh run/validation_tc2_gpu/step6_job_JOB directories. All large cache arrays stay on TC2. Local downloads stay in fresh output/tc2_gpu_setup_TIMESTAMP_ID directories, separately from synthetic fixtures and local acceptance summaries.

## Authorized files

Add only configs/pilot_tc2_gpu.json, scripts/pilot_tc2_gpu.py, scripts/slurm/pilot_tc2_gpu.sh, scripts/collect_tc2_gpu_pilot.py, tests/test_pilot_tc2_gpu.py, and this document. Modify only README.md and the external output/tc2_gpu_setup.ps1. The helper adds RunPilot and CollectPilot while preserving all previous operations. New validation evidence belongs under run/validation_tc2_gpu/step6_20261019/ and fresh job directories. No accepted algorithm, metric, workflow implementation, manifest, naming map, setup configuration, or lock file is edited.

## Execution order and resources

1. Check the exact frozen configuration, full workflow acceptance job 44012, all 31 scientific source hashes, the accepted setup/metric/algorithm records, compatibility snapshot, environment exports, actual weights, sample counts, and storage. Query available quota information and record unavailable or unparsed personal quota information honestly. Require at least 4 GiB of filesystem free space; filesystem free space does not establish a personal quota.
2. Generate or fully validate the bottle cache through the accepted entry point. Check all three saved NPY arrays, ordered paths, shape, FP32 dtype, finite values, input/weight/source fingerprints, metadata, and completion record.
3. Run the exact PaDiM B0 entry. Verify the saved result, including CPU metric reproduction from saved continuous predictions.
4. Run and verify the exact PatchCore B0 entry in the same way.
5. Invoke both run keys again. Require skipped status, matching identities, and unchanged hashes for every result artifact.
6. Download the selected immutable results and cache evidence, independently verify the returned artifacts locally, and only then finalize local step-6 acceptance.

Each accepted CLI action runs in a separate process. The fixed job request is MGPU-TC2/normal, one node, one task, one GPU, two CPUs, 24 GiB host RAM, and two hours. The requested allocation remains within the previously verified account limits. Keep batch size one, twenty separate warmups, FP32, disabled autocast/TF32, two software threads, accepted chunk sizes, and CUDA synchronization. Record actual GPU/driver/software, phase logs, timings, per-method GPU allocation/reservation peaks, and child-process maximum RSS. Scheduler collection adds job state, exit code, node, elapsed time, and available accounting memory values; unavailable accounting values remain unknown.

GPU allocation must match the accepted NVIDIA A40, driver 570.148.08, and CUDA build 12.8 before extraction. Two hours is a fixed ceiling, not an estimated runtime: complete real-data greedy sampling has not yet been timed. CPU metric stages use all original-resolution pixels and are recorded separately. Test AUROC/AP values are outputs, never pass/fail thresholds or a basis for changing the frozen design.

## Preconditions, publication, and failure behavior

Local RunPilot validation packages exactly the six additions and their checksums. Head-node operations use standard-library checks, file management, and scheduler queries only. Remote publication validates the archive hash, member whitelist, duplicates and links before extracting to a fresh staging directory. It then checks previous acceptance and publishes only absent or identical pilot files. Accepted scientific sources and the historical remote step-5 design document are verified/read but never uploaded or replaced. Pilot orchestration sources have separate fingerprints; they do not alter scientific run/cache identities.

The new wrapper is submitted through a recorded LF copy, with both source and submitted hashes. The submission stage path is passed explicitly to the job and checked before real work. The driver preserves a running/failed status until all seven phases succeed. Abrupt scheduler termination can leave a running record with step_6_complete=false; it never establishes completion. A fresh submission must use a fresh job directory. Complete intact caches/results can be validated and reused, while corrupted/conflicting artifacts and unknown locks are preserved and refused.

On OOM, timeout, failed source/input checks, unexpected hardware, unsuccessful child execution, incomplete results, or failed reuse checks, stop and retain evidence. Do not automatically delete locks or partial attempts, overwrite conflicts, increase resources, change chunk sizes, change scientific settings, or submit another job. Any required adjustment needs an updated design and explicit user confirmation.

## Collection and verification

RunPilot and CollectPilot use a dedicated SHA256-verified SCP archive rather than the historical 64 MiB base64 collector. The dedicated collector caps both compressed and total decompressed archive sizes at 512 MiB, rejects unexpected paths, duplicate aliases, links, invalid size/hash manifests, and conflicting extraction destinations, and checks all bytes before extracting to a fresh local directory.

The archive contains the pilot configuration, available job records and phase logs, the selected job's SLURM logs, the cache metadata/COMPLETE pair and layer hashes, and each published result's eight files: config.yaml, samples.json, predictions.npz, metrics.json, evidence.json, validation.json, artifacts.sha256, and SUCCESS. It excludes NPY cache arrays, raw images, arbitrary paths, and live partial result directories. A queued, running, or failed job yields a partial snapshot and never establishes acceptance. Remote full cache-array checks are distinct from local verification of downloaded metadata and predictions.

The local verifier checks archive and member checksums, approved paths/configurations, formal namespace, expected sample counts, result identity, scientific fingerprints, artifact manifests, and completion markers without importing a GPU runtime. Final independent review also loads saved FP32 predictions, verifies order/labels/five scores, checks the frozen manifests and original-size metadata, and reconciles the GPU job's saved-metric reproduction records. Full original-data/cache metric reproduction runs on TC2 through each accepted verify action because local raw inputs and FP32 cache arrays are not downloaded.

## Operation

After local implementation validation, run the following in the local Windows terminal and enter SSH passwords only there:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action RunPilot
```

Return the new terminal.txt path. If its job is queued or running, collect that same job rather than submitting it again:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action CollectPilot -JobId <returned-id>
```

RunPilot -ValidateOnly builds and validates the local six-file package without connecting or submitting. Offline tests exercise orchestration, acceptance gates, failure stopping, reuse, and safe archive transport using isolated fixtures. They cannot mark the real-data pilot complete.

## Acceptance status

The approved implementation is complete locally. All 28 offline tests passed with zero failures, errors, or skips. They cover the fixed frozen entries, orchestration and failure stopping, rejection of incomplete/failed historical acceptance, unchanged reuse requirements, complete and partial result snapshots, and archive size/path/link/hash/completion checks. A local invocation of real-data mode was rejected by the Linux SLURM guard before importing a GPU runtime or creating formal outputs.

The original thirteen helper actions passed offline transport regression, producing nineteen remote command fixtures. The new helper passed six transport cases, packaging-only validation, PowerShell syntax checks, nine Bash syntax checks, and nine bootstrap publication cases. Invalid source archive/hash/member/link/manifest cases were refused before extraction; an existing destination was preserved. These are isolated offline fixtures, not TC2 acceptance. No model execution, TC2 connection, or SLURM submission was performed by the assistant.

Step 6 requires a COMPLETED/0:0 scheduler result, a complete FP32 cache, two verified formal results with all five scores and pixel metrics, saved metric reproduction within absolute 1e-12, both reuse calls skipped without artifact changes, and independent local verification. The current implementation/evidence status is recorded in [the local step-6 record](../run/validation_tc2_gpu/step6_20261019/setup_status.json). Real-data completion remains pending until returned TC2 records satisfy every condition.
