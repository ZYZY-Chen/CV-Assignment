# TC2 GPU Experiment Protocol: Naming and Compatibility

The user approved this naming change on 2026-10-19. The canonical workflow name is `tc2_gpu`, and its display name is **TC2 GPU Experiment Protocol**. `tc2` identifies the remote TC2 cluster; `gpu` means that formal experiments use GPU execution. CPU metric validation and administrative preparation remain supported.

## Approved scope

1. Rename active setup, preparation, SLURM, and metric-test entry points to contain `tc2_gpu`. Rename the setup and metric guides to TC2_GPU_SETUP.md and TC2_GPU_METRICS.md. Update live documentation, comments, policy labels, imports, packaging lists, and commands consistently.
2. Preserve configs/protocol_v2.json byte for byte, including its protocol ID, version, hash, and stored output names. Preserve the filename docs/EXPERIMENT_PROTOCOL_V2.md and use the new display title inside it. Add configs/tc2_gpu.json as the naming map, without changing experimental parameters.
3. Use run/tc2_gpu/ for future formal results, logs, summaries, resource records, and FP32 feature caches. This establishes names only; runner integration and formal output activation remain in step 5. No formal experiment is started by this change.
4. Use run/setup_tc2_gpu/ and run/validation_tc2_gpu/ for future preparation and validation records. Existing run/setup_v2/, run/validation_v2/, local output snapshots, archives, and recorded source hashes retain their names and bytes. Readiness lookups prefer new records and fall back to accepted historical records only when a new record is absent.
5. Preserve the installed remote preparation directory and Conda prefix as actual compatibility addresses: /home/mcaai/huajie001/ca6129_v2_setup and its envs/ca6129-ad-v2. Do not move data, weights, or environments. configs/tc2_setup.json remains the verified discovery/acceptance configuration; the new naming map governs future names.
6. Rename the local helper to output/tc2_gpu_setup.ps1. New local output directories use tc2_gpu_setup_<timestamp_id>. Collection accepts both old and new record directories. Metric publication may replace only the two known accepted metric source hashes with their naming-only successors, backing up originals in the new validation stage record; unknown differences still stop. All other source publication remains absent-or-identical only.
7. Preserve numerical metric logic, dataset splits, locks, weights, V1 results, pre-existing Chinese, and external dependency version strings such as Anomalib v2.0.0. The metric policy label becomes tc2_gpu_tie_grouped; historical records retain v2_tie_grouped.
8. Keep the user's Git staging state untouched. Store the pre-change inventory, original files, naming map, and validation results in run/validation_tc2_gpu/naming_20261019/. This audit is separate from the preserved historical acceptance archives.

## Canonical entry points

| Purpose | Entry point |
|---|---|
| Setup checker | scripts/check_tc2_gpu_setup.py |
| Environment preparation | scripts/prepare_tc2_gpu_environment.sh |
| Input preparation | scripts/prepare_tc2_gpu_inputs.py |
| Setup SLURM job | scripts/slurm/check_tc2_gpu_setup.sh |
| Metrics SLURM job | scripts/slurm/check_tc2_gpu_metrics.sh |
| Hardware SLURM job | scripts/slurm/probe_tc2_gpu_hardware.sh |
| Preparation SLURM job | scripts/slurm/prepare_tc2_gpu.sh |
| Metric tests | tests/test_metrics_tc2_gpu.py |
| Local PowerShell helper | output/tc2_gpu_setup.ps1 |

## Validation and deployment boundary

Verify all preserved file hashes and historical evidence names; check links, imports, package manifests, PowerShell/Bash syntax, new output paths, and old/new readiness lookup. Run local NumPy core tests and offline transport/publication checks, including known-hash migration and unknown-conflict rejection. Do not install packages, access SSH, submit jobs, move remote directories, stage Git changes, or rerun formal experiments. Historical full acceptance remains evidence for the accepted implementation at its recorded hashes; local naming checks do not claim a new full remote acceptance.
