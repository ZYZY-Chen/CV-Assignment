# Implementation history

This is a readable history of the original steps 1-8 and earlier local usage. Its sequential accounts retain the wording and status visible at each implementation stage; statements such as "pending" or "no real-data fitting" describe that stage's snapshot. The [experiment ledger](EXPERIMENT_LEDGER.md) identifies final accepted jobs and later repairs. This document is not the current operating guide.

The exact original source, configuration, documents and receipts are retained through the [archive index](../../archive/index.json). Archive locators below identify ZIP members, not live worktree paths. Current operation and source identity are documented in the [workflow guide](../guides/TC2_GPU_WORKFLOW.md). Historical jobs do not establish acceptance of this checkout.

## Implementation documents

| Original step | Readable historical working copy |
| --- | --- |
| 1: frozen experiment specification | [Protocol history](../../archive/index.json), archived `docs/EXPERIMENT_PROTOCOL_V2.md` and `configs/protocol_v2.json` |
| 2: environment and inputs | [STEP_02_SETUP.md](implementation/STEP_02_SETUP.md) |
| 3: metrics | [STEP_03_METRICS.md](implementation/STEP_03_METRICS.md) |
| 4: algorithms | [STEP_04_ALGORITHMS.md](implementation/STEP_04_ALGORITHMS.md) |
| 5: workflow and FP32 cache | [STEP_05_WORKFLOW.md](implementation/STEP_05_WORKFLOW.md) |
| 6: real-data pilot | [STEP_06_PILOT.md](implementation/STEP_06_PILOT.md) |
| 7: formal stages and LOCO collection | [STEP_07_EXPERIMENTS.md](implementation/STEP_07_EXPERIMENTS.md) |
| 8: analysis | [STEP_08_ANALYSIS.md](implementation/STEP_08_ANALYSIS.md) |
| 8 supplement: figure revision | [STEP_08_FIGURE_REVISION.md](implementation/STEP_08_FIGURE_REVISION.md) |

## Source and operation boundaries

The corrected historical run set and the earlier pre-correction 66-run set have separate identities. The current `tc2_gpu` profile preserves the scientific matrix while binding its own protocol, paths and source manifest. Current cache/result identity must not be inferred from an old run key or job ID.

The TC2 allocation has been reclaimed. Legacy maintenance actions remain historical implementations behind the current deployment and acceptance gate. A future deployment requires a new design and acceptance for current source and environment; reorganizing their files does not validate them on a new remote system. No new remote validation is claimed here.

## Retained README account

比较 PaDiM 和 PatchCore。实验代码在这个目录，图片不放进 Git 仓库。

## TC2 GPU Experiment Protocol and historical results

The workflow name is `tc2_gpu`: `tc2` identifies the remote TC2 cluster and `gpu` specifies GPU execution for formal experiments. Its display name is **TC2 GPU Experiment Protocol**. The frozen [protocol_v2.json](../../archive/index.json) (archived path: `configs/protocol_v2.json`), its original identifiers, and the filename [EXPERIMENT_PROTOCOL_V2.md](../../archive/index.json) (archived path: `docs/EXPERIMENT_PROTOCOL_V2.md`) remain unchanged. [tc2_gpu.json](../../archive/index.json) (archived path: `configs/tc2_gpu.json`) maps those frozen names to current entry points and future output paths; [TC2_GPU_NAMING.md](../../archive/index.json) (archived path: `docs/TC2_GPU_NAMING.md`) defines compatibility and preservation rules.

The corrected experiment protocol is frozen as TC2 GPU. See [EXPERIMENT_PROTOCOL_V2.md](../../archive/index.json) (archived path: `docs/EXPERIMENT_PROTOCOL_V2.md`) for its explanation and [protocol_v2.json](../../archive/index.json) (archived path: `configs/protocol_v2.json`) for the machine-readable configuration. The 66 existing runs are registered as pre-correction historical results, with file fingerprints in [legacy_v1_inventory.json](../../archive/index.json) (archived path: `run/legacy_v1_inventory.json`).

Subsequent formal experiments use the TC2 GPU cluster, with TC2 GPU outputs under `run/tc2_gpu/`. The dedicated workflow integrates the frozen protocol, FP32 caches, and saved-result validation; synthetic integration acceptance completed in step 5 and real-data bottle pilot acceptance completed in step 6. Remaining frozen-matrix runs follow their separately approved execution steps. Independent acceptance of metric corrections and algorithm corrections was completed in steps 3 and 4. pre-correction results and SUCCESS markers do not establish TC2 GPU completion.

## TC2 GPU environment and input acceptance

See [TC2_GPU_SETUP.md](../../archive/index.json) (archived path: `docs/TC2_GPU_SETUP.md`) for step-2 preparation and acceptance, and [tc2_setup.json](../../archive/index.json) (archived path: `configs/tc2_setup.json`) for verified settings and status. Current checks use [check_tc2_gpu_setup.py](../../archive/index.json) (archived path: `scripts/check_tc2_gpu_setup.py`) and its [SLURM entry point](../../archive/index.json) (archived path: `scripts/slurm/check_tc2_gpu_setup.sh`), saving new records in `run/setup_tc2_gpu/`. Completed records remain in `run/setup_v2/`.

GPU checks must run within compute-node jobs. The acceptance tool checks prepared inputs and environments only. The actual cluster environment passed checks and was exported as [environment-tc2.yml](../../archive/index.json) (archived path: `environment-tc2.yml`) and [requirements-tc2-lock.txt](../../archive/index.json) (archived path: `requirements-tc2-lock.txt`). Rebuild using those exports together with the official cu128 package source and installation order in the preparation instructions. Existing Windows/CUDA dependency files remain historical records.

Step 2 completed on 2026-10-19: final combined acceptance job 43950 on TC2N01 finished as COMPLETED / 0:0 with `step_2_complete=true`. All frozen hashes for 3650 images and 1019 masks matched, and checks of the specified weights, CUDA FP32 operations, and three ResNet18 feature layers passed. The actual environment uses NVIDIA A40, driver 570.148.08, glibc 2.34, Python 3.10.22, and torch 2.11.0+cu128 / torchvision 0.26.0+cu128. See the [step-2 acceptance record](../../archive/index.json) (archived path: `run/setup_v2/step2_20261019_060542/setup_status.json`) for complete status.

The user-approved preparation workflow uses separate [environment preparation](../../archive/index.json) (archived path: `scripts/prepare_tc2_gpu_environment.sh`), [input preparation](../../archive/index.json) (archived path: `scripts/prepare_tc2_gpu_inputs.py`), [short hardware job](../../archive/index.json) (archived path: `scripts/slurm/probe_tc2_gpu_hardware.sh`), and [preparation job entry point](../../archive/index.json) (archived path: `scripts/slurm/prepare_tc2_gpu.sh`) scripts. AD uses the specified complete Hugging Face package at a fixed revision and hash, extracting only six categories. The two LOCO categories and weights retain official sources. See sections 6.4 and 6.7 of the preparation instructions for local operation and log retrieval. Submit SLURM jobs from the verified preparation directory.

## TC2 GPU metric corrections and step-3 acceptance

The user-approved step-3 design is documented in [TC2_GPU_METRICS.md](../../archive/index.json) (archived path: `docs/TC2_GPU_METRICS.md`). [metric_core.py](../../archive/index.json) (archived path: `src/metric_core.py`) implements exact AUROC/AP with tied scores grouped by threshold. [evaluate.py](../../archive/index.json) (archived path: `src/evaluate.py`) adds normal-development thresholds, input validation, and LOCO groups while preserving existing result fields and adding `metric_policy.version=tc2_gpu_tie_grouped`. Evaluation accepts the original four image scores and a subsequently supplied native score; model score generation remains in later steps.

Step 3 completed on 2026-10-19. All nine local NumPy core checks passed. CPU acceptance job 43956 on TC2N01 finished as COMPLETED / 0:0, with all 24 full tests passing and `step_3_complete=true`. Across 81 scikit-learn comparisons, maximum AUROC/AP absolute errors were 1.11e-16 / 2.22e-16, below the 1e-12 limit. The returned archive's 100 files, five source fingerprints, and change scope were independently verified. See the [step-3 acceptance record](../../archive/index.json) (archived path: `run/validation_v2/step3_20261019_081534/setup_status.json`) for final status and the metric document for the complete design, commands, and evidence. No acceptance-job resubmission is required.

## TC2 GPU algorithm corrections and step-4 acceptance

The approved step-4 design is recorded in [TC2_GPU_ALGORITHMS.md](../../archive/index.json) (archived path: `docs/TC2_GPU_ALGORITHMS.md`). PaDiM now aligns selected layers to their highest resolution and uses square-root Mahalanobis distance. PatchCore pools both layers, retains the layer2 grid, and separates one-neighbor pixel distances from its weighted native image score. Sampling preserves distinct indices, including duplicate feature vectors.

[predict_padim](../../archive/index.json) (archived path: `src/padim_adapter.py`) and [predict_patchcore](../../archive/index.json) (archived path: `src/patchcore_adapter.py`) return final FP32 256x256 anomaly maps and five image scores. [Shared postprocessing](../../archive/index.json) (archived path: `src/anomaly_postprocess.py`) applies bilinear resizing followed once by the fixed Gaussian filter. The legacy four-rule scoring default and map-only interfaces remain available; the unchanged legacy runner is not the formal TC2 GPU entry point.

Step 4 completed on 2026-10-19. Current-naming metric regression job 43968 passed all 24 tests. Algorithm acceptance job 43970 on TC2N01 (NVIDIA A40) finished as COMPLETED / 0:0: all 19 CPU tests and two GPU tests passed, with full-mode `step_4_complete=true`. The [algorithm tests](../../archive/index.json) (archived path: `tests/test_algorithms_tc2_gpu.py`) cover independent references and actual ResNet18 feature shapes generated synthetically. All eleven source fingerprints and 163 returned files were verified. See the [step-4 acceptance record](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step4_20261019/setup_status.json`) and [GPU acceptance entry point](../../archive/index.json) (archived path: `scripts/slurm/check_tc2_gpu_algorithms.sh`). No real-data fitting, cache generation, or formal experiment has been run.

## TC2 GPU workflow and step-5 acceptance

The approved [workflow design](../../archive/index.json) (archived path: `docs/TC2_GPU_WORKFLOW.md`) adds the dedicated [run_tc2_gpu.py](../../archive/index.json) (archived path: `scripts/run_tc2_gpu.py`) entry point with plan, extract, run, and verify actions. It derives all 66 fits from the frozen matrix, binds both method seeds to the run seed, and uses immutable FP32 NPY caches with ordered reads. Scientific settings and historical entry points remain unchanged. [runtime_tc2_gpu.json](../../archive/index.json) (archived path: `configs/runtime_tc2_gpu.json`) holds execution settings only.

Formal outputs use run/tc2_gpu/. Predictions retain FP32 maps and all five scores. Runs publish SUCCESS only after saved-array checks and metric reproduction; reuse requires matching identities and intact artifacts. The new cache directory is excluded from Git. Planning is read-only; real-data extraction and pilot acceptance are documented in step 6 below.

Step 5 completed on 2026-10-19. The [synthetic workflow acceptance job](../../archive/index.json) (archived path: `scripts/slurm/check_tc2_gpu_workflow.sh`), job 44012 on TC2N02 (NVIDIA A40), finished as COMPLETED / 0:0 with full-mode `step_5_complete=true`. All 65 tests passed: 24 metric tests, 19 CPU/two GPU algorithm tests, and the [workflow tests](../../archive/index.json) (archived path: `tests/test_workflow_tc2_gpu.py`)' 16 core/four GPU tests. Independent verification checked 421 returned files, 31 scientific source fingerprints, all 32 submitted files, and saved prediction/metric consistency. The previous 163 acceptance files were preserved. See the [final step-5 record](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step5_20261019/setup_status.json`) and [returned-artifact verification](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step5_20261019/accepted_job_44012/verification.json`). No resubmission is required. All cache and result fixtures are synthetic; real-data extraction and pilots remain step 6.

## TC2 GPU real-data pilot and step-6 acceptance

The approved [pilot design](../../archive/index.json) (archived path: `docs/TC2_GPU_PILOT.md`) uses the bottle category and the two existing B0 seed-17/N100 entries. [pilot_tc2_gpu.json](../../archive/index.json) (archived path: `configs/pilot_tc2_gpu.json`) fixes the exact run keys, counts, accepted source hashes, and resource request. The [pilot driver](../../archive/index.json) (archived path: `scripts/pilot_tc2_gpu.py`) calls the accepted cache/run/verify entry points sequentially, then checks both runs skip without changing saved artifacts. These two fits count within the frozen 66-fit matrix.

The [SLURM wrapper](../../archive/index.json) (archived path: `scripts/slurm/pilot_tc2_gpu.sh`) requests one GPU, two CPUs, 24 GiB, and two hours in MGPU-TC2/normal. RunPilot enters, checks, and logs the verified project directory in the submission SSH session and explicitly passes that directory to sbatch. The helper's RunPilot/CollectPilot actions use the [dedicated collector](../../archive/index.json) (archived path: `scripts/collect_tc2_gpu_pilot.py`) to return full selected results and cache metadata through a checked SCP archive; FP32 NPY arrays remain on TC2. Existing helper operations and scientific sources are preserved. The [pilot design](../../archive/index.json) (archived path: `docs/TC2_GPU_PILOT.md`) remains the original submitted snapshot; current completion is recorded below and in the acceptance record.

Step 6 completed on 2026-10-19. Job 44024 on TC2N01 (NVIDIA A40) finished as COMPLETED / 0:0 in 00:02:33, with `step_6_complete=true`. All 292 bottle images have a verified three-layer FP32 cache. Both B0 seed-17/N100 runs completed, passed full saved-result metric reproduction on TC2 within absolute 1e-12, and returned skipped on reuse without artifact changes. Independent local checks verified all 41 returned payload files plus their export manifest, all 31 scientific source fingerprints, and all six submitted pilot files. Saved maps, five scores, labels and sample order passed validation; independent image-metric reproduction had maximum absolute error 1.55e-15 for both methods. Original-mask pixel metrics and full cache-array verification ran on TC2; the local download includes cache metadata and fingerprints rather than NPY arrays. See the [final step-6 acceptance record](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step6_20261019/setup_status.json`) and [independent returned-artifact verification](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step6_20261019/accepted_job_44024/verification.json`). The [28 offline checks](../../archive/index.json) (archived path: `tests/test_pilot_tc2_gpu.py`) remain supporting validation. These two results count within the frozen 66-fit matrix; no pilot resubmission is required.

## TC2 GPU formal experiments and step-7 execution

The approved [formal-stage design](../../archive/index.json) (archived path: `docs/TC2_GPU_EXPERIMENTS.md`) adds twelve explicit stages to complete the frozen 66-fit matrix, reusing the two accepted bottle results and planning 64 new fits. [experiments_tc2_gpu.json](../../archive/index.json) (archived path: `configs/experiments_tc2_gpu.json`) fixes the order, dependencies and resource requests. The [stage controller](../../archive/index.json) (archived path: `scripts/experiments_tc2_gpu.py`) calls the accepted scientific entry points, and the [saved-score analysis](../../archive/index.json) (archived path: `scripts/analyze_scores_tc2_gpu.py`) produces I1/I2 results without fitting.

The sequence is B0, H1, H2, C1, I1_seed17, R0, C1R, C2, F1, I1_all_seeds, I2 and B0_LOCO. Fitting stages request TC2N01 with one GPU, two CPUs, 24 GiB and two hours; analysis stages use partition scheduling with no GPU, two CPUs, 8 GiB and fifteen minutes. Actual fitting hardware must match NVIDIA A40, driver 570.148.08 and CUDA build 12.8. Each stage requires the latest preceding stages to have passed. The external helper's RunExperiments/CollectExperiments actions submit one stage at a time and use the [bounded collector](../../archive/index.json) (archived path: `scripts/collect_experiments_tc2_gpu.py`) to verify all pages before collection acceptance. Each page contains at most four whole results and is limited to 512 MiB both compressed and decompressed. NPY caches remain on TC2.

Step 7 completed on 2026-10-19: all twelve stages passed independent local acceptance, covering 66 fits (64 new fits and two accepted pilot results reused) and 108 saved-score analysis rows. The core, standard and full checkpoints are complete. Final B0_LOCO job 44235 on TC2N01 finished as COMPLETED / 0:0 in 00:45:10; both returned pages, all four results, saved arrays and pooled/logical/structural image metrics passed verification. See the [final step-7 record](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step7_20261019/setup_status.json`) and [LOCO acceptance](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step7_20261019/accepted_job_44235/verification.json`). Original-mask pixel metrics were reproduced on TC2; local verification uses saved arrays, image scores and hash-bound cache metadata. The controller never submits a subsequent stage automatically. The [offline tests](../../archive/index.json) (archived path: `tests/test_experiments_tc2_gpu.py`) support local verification; they do not establish completion of the formal experiments. See the stage design for commands, storage gates, immutable-source rules and the 22/62/66-fit checkpoints. Resource comparisons, aggregated statistics, figures, failure-case presentation and report writing remain later work.

LOCO collection uses the separate [LOCO compatibility collector](../../archive/index.json) (archived path: `scripts/collect_experiments_loco_tc2_gpu.py`) and its [offline tests](../../archive/index.json) (archived path: `tests/test_collect_experiments_loco_tc2_gpu.py`). The original collector accepts only the three MVTec AD metric fields, whereas the accepted LOCO evaluator also writes `groups` and `pixel_note`. The compatibility collector strictly verifies both logical and structural groups, their sample and original-resolution pixel counts, all five image rules, and the original metric policy. Archive hashes, path protections, immutable source fingerprints and the 512 MiB page bounds remain enforced. The seven frozen experiment files, existing results and historical logs retain their original bytes.

The accepted LOCO collection used the external helper with `-Action CollectExperiments -JobId 44235 -LocoCollection`. Job 44235 needs no resubmission or further collection. This explicit switch is restricted to collection of B0_LOCO; it uploads only the independent collector to a new hash-named remote script and records both its SHA256 and the frozen base collector SHA256. Remote export and every local verification step use the same compatibility collector. No fit or new SLURM job is submitted. Return the newly generated `terminal.txt` for review; a queued, running or partial snapshot does not complete step 7.

## TC2 GPU result analysis and step-8 execution

The approved [analysis design](../../archive/index.json) (archived path: `docs/TC2_GPU_ANALYSIS.md`) consumes the twelve accepted collections and all 66 fits. The [analysis entry point](../../archive/index.json) (archived path: `scripts/analyze_results_tc2_gpu.py`) creates a portable input registry, validates the existing formal outputs, and produces statistics, resource tables, mask-area groups and deterministic cases. The [plotting module](../../archive/index.json) (archived path: `scripts/plot_results_tc2_gpu.py`) creates the main comparison and F1-F5 figure groups with English labels, source data, fixed development-derived heatmap limits and explicit uncertainty definitions. The [analysis configuration](../../archive/index.json) (archived path: `configs/analysis_tc2_gpu.json`) fixes these reporting choices without changing scientific settings.

Main AD statistics use six-category macros per seed, followed by the mean and sample standard deviation across seeds 17, 29 and 43 (`ddof=1`). Single-seed scans have no invented standard deviation; LOCO logical and structural groups remain separate. The 18-row I1_seed17 checkpoint is overlapping audit evidence rather than additional observations. Cached prediction costs use development plus test image counts and are labelled with their actual timing scope, not end-to-end latency.

Use the external helper's RunAnalysis action to package the seven new files and validated input registry, then submit one CPU job through the [analysis wrapper](../../archive/index.json) (archived path: `scripts/slurm/analysis_tc2_gpu.sh`): two CPUs, 8 GiB, fifteen minutes, MGPU-TC2/normal and no GPU. Existing models are not fitted or called. The locked TC2 environment already contains Matplotlib; this step does not install local plotting dependencies or change environment exports. RunAnalysis -ValidateOnly performs local packaging only. CollectAnalysis -JobId returns the current snapshot of the existing job and never resubmits it.

The [bounded analysis collector](../../archive/index.json) (archived path: `scripts/collect_analysis_tc2_gpu.py`) downloads a pinned index and every verified page, preserving the 512 MiB compressed/decompressed bounds and rejecting unsafe paths, links, duplicates and mixed snapshots. New tables, PNG/PDF figures, selected cases and provenance records use `run/tc2_gpu/summaries/analysis/<identity>/`; feature caches and full datasets remain on TC2. The [analysis tests](../../archive/index.json) (archived path: `tests/test_analysis_tc2_gpu.py`), completed CPU job, full collection, independent statistics and visual review are all required for step-8 acceptance. Local implementation alone is not completion. Report chapters remain later work.

Step 8 completed on 2026-10-19. Analysis job 44284 finished as COMPLETED / 0:0 in 00:02:01 with all 29 full tests passing; its tables, selected cases and descriptive distributions passed independent verification. Figure revision job 44303 on TC2N07 then finished as COMPLETED / 0:0 in 00:01:05, using two CPUs, 8 GiB and zero GPUs. All 22 full revision tests passed, including actual synthetic rendering of fifteen figure groups. The complete collection returned 174 payload files with verified fingerprints.

The approved [figure revision supplement](../../archive/index.json) (archived path: `docs/TC2_GPU_FIGURE_REVISION.md`) uses the independent [CPU revision driver](../../archive/index.json) (archived path: `scripts/revise_figures_tc2_gpu.py`), [configuration](../../archive/index.json) (archived path: `configs/figure_revision_tc2_gpu.json`), [collector](../../archive/index.json) (archived path: `scripts/collect_figure_revision_tc2_gpu.py`), [wrapper](../../archive/index.json) (archived path: `scripts/slurm/figure_revision_tc2_gpu.sh`) and [tests](../../archive/index.json) (archived path: `tests/test_figure_revision_tc2_gpu.py`). It imports the frozen plotting module and overrides only shared layout/export and the methods diagram. Independent checks confirmed exact equality of all 6,896 ordered source-data rows across fifteen groups, byte-identical tables and case registries, and all 90 assets for the unchanged sixteen selected cases. All 51 protected source files and six pinned revision files matched their fingerprints; original analysis outputs and historical logs remain unchanged. No new fit, model prediction or scientific analysis was introduced.

All fifteen original 300 dpi PNGs and independently rendered PDF pages passed visual review. Actual PDF text is selectable and uses embedded TrueType-backed fonts; the smallest glyph is 7.5 pt. Measured page-footer separation, axes alignment, methods-diagram text containment and both output routes passed. Supplemental PDF geometry checks used an explicitly documented pdfplumber adapter because PyMuPDF was unavailable; the record does not claim a standard fitz CLI pass. Existing-case display rounding remains documented and does not change full-precision decisions.

Accepted revised figures use `run/tc2_gpu/summaries/figure_revision/F8FBEF088CF879DE093C89009081CAD00B4698BB99BC3A6A080C748AFA4AA636/`. See the [final step-8 status](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step8_figure_revision_20261019/setup_status.json`) and [independent acceptance](../../archive/index.json) (archived path: `run/validation_tc2_gpu/step8_figure_revision_20261019/accepted_job_44303/verification.json`). The original analysis namespace is retained. The helper's RunFigureRevision/CollectFigureRevision actions preserve the bounded single-archive workflow; accepted job 44303 requires no resubmission or further collection. Report writing and step 9 have not started.

## Historical dataset download example

The pre-correction downloader example below is historical; its script is now archived. It uses legacy official direct links, some of which now return 404. Follow the TC2 instructions above for TC2 GPU input preparation; accepted data is in the remote preparation directory's `datasets/`. The old command extracts into the local parent directory's `datasets/` by default:

```powershell
python scripts/download_datasets.py --accept-license
```

本机已经有图片时会跳过。下载完成后的目录是：

```
datasets/
├── mvtec_ad/<category>/
└── mvtec_loco/<category>/
```

## pre-correction historical usage: reproduce B0 on the local CPU

The retained legacy example below writes to the pre-correction results directory; use the separately approved cluster workflow for TC2 GPU execution.

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"
python run.py --config configs/b0_patchcore.yaml --dataset mvtec_ad --category bottle --device cpu
```

这台笔记本的独显在大块距离计算时蓝屏过，实验请加 `--device cpu`，并把 `CUDA_VISIBLE_DEVICES` 设为 `-1`。进展、已知问题和计时见 `run/HANDOFF_续作说明.md`。

## Temporary test artifact cleanup (2026-10-25)

The approved long-path cleanup removed 18 temporary fixture and simulated-transport directories after complete ZIP backup and member-by-member SHA256 verification. Original outer test reports, final acceptance records, formal results and scientific sources remain in place. See [Test artifact cleanup](repository_changes/TEST_ARTIFACT_CLEANUP.md) and the [cleanup manifest](../../archive/index.json) (archived path: `run/validation_tc2_gpu/path_cleanup_01/cleanup_manifest.json`). Earlier paths inside removed test workspaces are now archive-member references, rather than live worktree paths.
