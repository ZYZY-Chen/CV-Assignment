# CA6129 Industrial Anomaly Detection Group Project

## Current workflow

The repository root is the code root. The canonical workflow is `tc2_gpu`, displayed as **TC2 GPU Experiment Protocol**: `tc2` identifies the remote TC2 cluster, and `gpu` identifies the requirement for formal fitting. Lifecycle entry points live under `scripts/tc2_gpu/`.

The previous TC2 allocation has been reclaimed; current deployment is **unavailable**. Historical steps 1-8 were accepted for their recorded source and environment. This reorganized checkout requires its own acceptance before formal execution. Step 9 and report writing remain deferred.

These local operations are read only and require no model or GPU:

```powershell
python -I -B scripts/tc2_gpu/workflow/run_workflow.py plan
python -I -B scripts/tc2_gpu/workflow/verify_archive.py
```

The current configurations and independent source manifest are in [configs/tc2_gpu/](configs/tc2_gpu/). [environment-tc2_gpu.yml](environment-tc2_gpu.yml) is a portable template, [requirements-tc2_gpu-bootstrap.txt](requirements-tc2_gpu-bootstrap.txt) constrains installation, and [requirements-tc2_gpu-lock.txt](requirements-tc2_gpu-lock.txt) retains historical observed versions. These files do not establish a newly installed or accepted environment.

## Navigation and evidence

| Need | Start here |
| --- | --- |
| Current lifecycle, script responsibilities and prerequisites | [Workflow guide](docs/guides/TC2_GPU_WORKFLOW.md) |
| Preserved scientific matrix and configuration roles | [Protocol](docs/guides/TC2_GPU_PROTOCOL.md) |
| Current, corrected historical and pre-correction identities | [Naming and source identity](docs/guides/TC2_GPU_NAMING.md) |
| ZIP verification and historical artifact lookup | [Archive guide](docs/guides/TC2_GPU_ARCHIVE.md) and [archive index](archive/index.json) |
| Original steps 1-8, prior commands and CPU notes | [Implementation history](docs/experiment_history/IMPLEMENTATION_HISTORY.md) |
| Actual jobs, collections, final acceptance and repairs | [Experiment ledger](docs/experiment_history/EXPERIMENT_LEDGER.md) |
| Earlier repository-root migration and fixture cleanup | [Layout migration](docs/experiment_history/repository_changes/REPOSITORY_LAYOUT_MIGRATION.md) and [cleanup](docs/experiment_history/repository_changes/TEST_ARTIFACT_CLEANUP.md) |

The archive keeps original bytes and paths. Readable historical Markdown copies are navigational records; their old commands, pending flags and remote locations are not current operating instructions. Formal scientific returns remain in their original external collections.

## Datasets

The project uses bottle, cable, capsule, screw, tile and wood from MVTec AD, and juice_bottle and screw_bag from MVTec LOCO. Both datasets are licensed under CC BY-NC-SA 4.0 for noncommercial use.

Official download pages:

- MVTec AD: https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads
- MVTec LOCO: https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads

Current input preparation is described in the [workflow guide](docs/guides/TC2_GPU_WORKFLOW.md); the earlier local downloader and CPU examples are retained in the [implementation history](docs/experiment_history/IMPLEMENTATION_HISTORY.md).
