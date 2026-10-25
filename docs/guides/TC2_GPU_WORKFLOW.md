# TC2 GPU workflow

This is the current entry-point guide for **TC2 GPU Experiment Protocol** (`tc2_gpu`). Commands are run from the repository root. The scientific specification is in the [protocol guide](TC2_GPU_PROTOCOL.md); the original implementation sequence is in the [implementation history](../experiment_history/IMPLEMENTATION_HISTORY.md).

## Current readiness

The earlier TC2 allocation has been reclaimed. [setup.json](../../configs/tc2_gpu/setup.json) records unavailable deployment, with connection, remote root and environment fields unset. The current source manifest describes this checkout separately from the archived accepted source. Historical job IDs, completion files and old environment exports do not authorize current formal execution.

The following commands inspect the frozen matrix and verify project-contained historical ZIPs. They do not create output directories, import models, extract caches, connect to TC2 or submit jobs:

```powershell
python -I -B scripts/tc2_gpu/workflow/run_workflow.py plan
python -I -B scripts/tc2_gpu/workflow/verify_archive.py
```

Use direct script invocation with `-I -B`: isolated mode excludes the current directory from Python's automatic import path, and the entry points locate this repository explicitly. The scripts do not require an installed Python package. These commands do not install dependencies or restore data.

## Fitting and dependency order

The backbone is a frozen, pretrained ResNet18. Here, "training" means extracting fixed features, fitting PaDiM's normal-feature statistics or building PatchCore's memory bank. It does not mean optimizing the backbone over training epochs.

The lifecycle is:

1. Establish a newly approved deployment, environment and current-source acceptance, then verify the eight frozen input manifests and pretrained weights.
2. Validate metric definitions, algorithm behavior and workflow/cache integration against that source and environment.
3. Extract immutable FP32 category caches and run the two bottle pilot fits. Verify results and unchanged reuse behavior.
4. Execute the twelve formal stages in their configured order, checking each required predecessor before progressing. Collect and independently verify each returned stage.
5. Analyze saved predictions and saved scores, then revise figure layout if required. Verify returned data and rendering before accepting that analysis identity.

The preserved matrix contains 66 fits: 62 MVTec AD and four LOCO fits. The original execution reused two accepted pilot fits and produced 64 new fits. That historical reuse is not automatic permission to reuse them for current source. I1/I2 operate on saved scores; result analysis and figure revision introduce no additional fits. The [ledger](../experiment_history/EXPERIMENT_LEDGER.md) records what actually ran.

The stage order is `B0`, `H1`, `H2`, `C1`, `I1_seed17`, `R0`, `C1R`, `C2`, `F1`, `I1_all_seeds`, `I2`, `B0_LOCO`. [experiments.json](../../configs/tc2_gpu/experiments.json) specifies stage dependencies and resources; descriptive numbering in history is not an execution command.

## Entry points and responsibilities

All paths in the next tables are relative to `scripts/tc2_gpu/`. Core model, metric, cache and provenance logic remains in [src/](../../src/); entry scripts coordinate that logic. The `plot_results.py` module is a rendering library imported by the analysis drivers.

| Entry | Input and responsibility | Output or writes | Intended execution and prerequisites |
| --- | --- | --- | --- |
| [setup/prepare_environment.sh](../../scripts/tc2_gpu/setup/prepare_environment.sh) | Approved environment specification, module and installation pins | Creates or prepares the specified environment and preparation records | Approved TC2 preparation context; new deployment design required |
| [setup/prepare_inputs.py](../../scripts/tc2_gpu/setup/prepare_inputs.py) | Pinned archive sources, license acceptance, frozen input identities | Transfer packages or extracted data/weights in configured locations | Approved local transfer or TC2 preparation context; not a read-only check |
| [setup/check_setup.py](../../scripts/tc2_gpu/setup/check_setup.py) | Current setup, raw data, weights and allocated runtime | Environment/input audits under `run/setup_tc2_gpu/` | Accepted current setup and the required compute allocation |
| [workflow/run_workflow.py](../../scripts/tc2_gpu/workflow/run_workflow.py) | `plan` displays the matrix; `extract`, `run`, `verify` coordinate cache, one fit and result verification | `plan` is read only; formal actions use current output namespaces | Local inspection for `plan`; fitting/extraction require current acceptance and a Linux SLURM GPU compute job |
| [workflow/verify_archive.py](../../scripts/tc2_gpu/workflow/verify_archive.py) | Archive index, ZIP and member fingerprints | Console verification only; no extraction | Local Python; independent of the remote deployment |
| [pilot/run_pilot.py](../../scripts/tc2_gpu/pilot/run_pilot.py) | Pilot configuration, accepted workflow and two bottle run keys | Pilot execution/verification and publication records | Newly accepted current workflow; real fits run in the allocated GPU job |
| [experiments/run_stages.py](../../scripts/tc2_gpu/experiments/run_stages.py) | Stage configuration and verified predecessor records | Stage records; delegates fitting or saved-score analysis | Current phase acceptance; GPU for fitting, CPU for saved-score stages |
| [experiments/analyze_scores.py](../../scripts/tc2_gpu/experiments/analyze_scores.py) | Saved result records and I1/I2 score rules | Identity-bound tables/records under `run/tc2_gpu/summaries/<stage>/` | Stage controller after source-result verification; no model fitting |
| [analysis/analyze_results.py](../../scripts/tc2_gpu/analysis/analyze_results.py) | Verified collected results and input registry | Statistics, resource tables, cases, source data and figures under the analysis identity | Current analysis acceptance and complete source collections; CPU |
| [analysis/plot_results.py](../../scripts/tc2_gpu/analysis/plot_results.py) | Validated analysis data and plotting policy | PNG/PDF figures and plotted source-data records | Imported by analysis drivers; no independent training entry point |
| [analysis/revise_figures.py](../../scripts/tc2_gpu/analysis/revise_figures.py) | Pinned accepted analysis, revision policy and protected-source fingerprints | Separate figure-revision identity; original analysis retained | Current revision acceptance; CPU; layout/export changes only |

Collectors export bounded snapshots on the compute/remote side and verify downloaded snapshots locally. A transfer completing successfully is not sufficient for scientific acceptance: expected membership, fingerprints, phase status and result-specific rules must also pass.

| Collector | Required source | Output and limits |
| --- | --- | --- |
| [collect/collect_pilot.py](../../scripts/tc2_gpu/collect/collect_pilot.py) | Pilot job snapshot and two results | Selected complete results and cache metadata; feature arrays remain remote |
| [collect/collect_experiments.py](../../scripts/tc2_gpu/collect/collect_experiments.py) | One formal AD stage and its source fingerprints | Pinned index and bounded whole-result pages |
| [collect/collect_experiments_loco.py](../../scripts/tc2_gpu/collect/collect_experiments_loco.py) | LOCO stage with logical/structural groups and all five image rules | Dataset-aware verification of the same formal result format and bounded pages |
| [collect/collect_analysis.py](../../scripts/tc2_gpu/collect/collect_analysis.py) | Analysis snapshot and protected sources | Pinned index, paged tables, figures, cases and provenance |
| [collect/collect_figure_revision.py](../../scripts/tc2_gpu/collect/collect_figure_revision.py) | Revised figure identity and pinned source analysis | One verified archive, up to 512 MiB compressed/decompressed and 512 members |

Experiment pages contain at most four whole results and are limited to 512 MiB compressed and decompressed. The analysis collector also enforces 512 MiB page bounds. Collectors reject unsafe or duplicate paths, links, changed fingerprints and mixed snapshots. They do not download full datasets or FP32 feature arrays.

## SLURM wrappers and client

The wrappers below run inside approved Linux SLURM compute allocations. Historical partition, node and resource observations are recorded in the [ledger](../experiment_history/EXPERIMENT_LEDGER.md); those observations do not establish a future account's resource limits.

| Wrapper under `slurm/` | Responsibility |
| --- | --- |
| [probe_hardware.sh](../../scripts/tc2_gpu/slurm/probe_hardware.sh) | Record the allocated hardware/runtime |
| [prepare_setup.sh](../../scripts/tc2_gpu/slurm/prepare_setup.sh) | Run the selected environment or input preparation |
| [check_setup.sh](../../scripts/tc2_gpu/slurm/check_setup.sh) | Verify environment and inputs |
| [check_metrics.sh](../../scripts/tc2_gpu/slurm/check_metrics.sh) | Run full metric reference checks on CPU |
| [check_algorithms.sh](../../scripts/tc2_gpu/slurm/check_algorithms.sh) | Run CPU/GPU synthetic algorithm checks |
| [check_workflow.sh](../../scripts/tc2_gpu/slurm/check_workflow.sh) | Run synthetic cache, runner and reuse checks |
| [run_pilot.sh](../../scripts/tc2_gpu/slurm/run_pilot.sh) | Run the real-data pilot |
| [run_stages.sh](../../scripts/tc2_gpu/slurm/run_stages.sh) | Run one selected fitting or saved-score stage |
| [run_analysis.sh](../../scripts/tc2_gpu/slurm/run_analysis.sh) | Analyze the verified result collections on CPU |
| [run_figure_revision.sh](../../scripts/tc2_gpu/slurm/run_figure_revision.sh) | Render and verify the independent figure revision on CPU |

The Windows client is [client/tc2_gpu.ps1](../../scripts/tc2_gpu/client/tc2_gpu.ps1). `CodeRoot` defaults to the repository containing that script. `PythonExecutable` defaults to `python` resolved from PATH. `OutputRoot` defaults to `<repository>/run/setup_tc2_gpu/client`; a real action creates a fresh return directory there. The external course-output helper is a thin compatibility wrapper that forwards its existing parameters and passes its own directory as `OutputRoot`.

`ValidateOnly` is a switch. It checks the current plan and source fingerprints and returns before creating output directories or using network tools:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tc2_gpu\client\tc2_gpu.ps1 -Action Probe -ValidateOnly -PythonExecutable python
```

The execution-policy option applies to this process. `Probe` in this example selects an action label; `ValidateOnly` prevents the remote probe from running.

Legacy maintenance actions, including repair/publication operations, retain their historical implementation. Real actions are blocked by the current unavailable-deployment and acceptance gate. A future deployment requires a new design and acceptance for current source and environment; this directory reorganization does not validate remote publication, SSH, SLURM or maintenance behavior on a new system.

## Storage and configuration

| Location | Role |
| --- | --- |
| [configs/tc2_gpu/](../../configs/tc2_gpu/) | Current protocol, workflow, setup, runtime, pilot, experiment, analysis and revision policies; independent `source_manifest.json` |
| [manifests/](../../manifests/) | Frozen category splits, image/mask fingerprints and fitting subsets |
| [datasets/](../../datasets/) | Raw images outside Git; current deployment must establish actual locations |
| `run/tc2_gpu/{feature_cache,results,logs,summaries,resources}/` | Current formal namespaces; output identity binds protocol and source bytes |
| `run/setup_tc2_gpu/`, `run/validation_tc2_gpu/` | New setup and local validation records; short fixture paths avoid Windows path limits |
| [archive/](../../archive/) | Immutable original sources and acceptance evidence; verify without expanding the full history |
| [tools/data/make_manifests.py](../../tools/data/make_manifests.py) | Separate data-manifest creation utility; not part of the fitting sequence and not permission to regenerate frozen manifests |

The environment template, bootstrap constraints and historical observed-version lock remain separate files at the repository root. No dependency installation is part of this restructuring. See the [naming guide](TC2_GPU_NAMING.md) for exact-byte source identity and the [archive guide](TC2_GPU_ARCHIVE.md) for historical recovery.
