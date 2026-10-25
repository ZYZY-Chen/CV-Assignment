# Step 8: analysis of the TC2 GPU Experiment Protocol

> **Current profile and historical-record boundary (2026-10-25)**
>
> The retained design and acceptance account below describes the earlier implementation. Its job IDs, source hashes, remote paths, command blocks and completion flags are historical. Exact original bytes are in the [archive index](../archive/index.json); they do not certify this refactored checkout.
>
> Current configurations are under configs/tc2_gpu/, and independent fingerprints are in configs/tc2_gpu/source_manifest.json. The current deployment is unavailable. Formal actions refuse execution without new source/environment acceptance. Historical SSH and submission examples below are not current connection instructions.
>
> Use the [current protocol](TC2_GPU_PROTOCOL.md), [naming rules](TC2_GPU_NAMING.md) and [archive guide](TC2_GPU_ARCHIVE.md) for current paths. Local read-only commands from the repository root are python -B scripts/run_tc2_gpu.py plan and python -B scripts/verify_archive_tc2_gpu.py.

## Historical design and acceptance account


This is the user-approved result-analysis design. It consumes the twelve accepted experiment collections, 66 unique fits (64 new and two pilot results reused), and 108 saved-score analysis rows. It does not fit a model, modify a threshold, choose a new scoring rule, change the frozen protocol, or write report chapters. Existing scientific sources, seven experiment sources, environment locks, manifests, results and historical records remain unchanged.

## Inputs and provenance

The local `plan` command reads the completed step-7 acceptance ledger and its twelve records. It validates their hashes, raw stage records, exact frozen fit coverage, result identities, and file fingerprints. It creates a portable input registry with remote relative paths and expected hashes. It does not discover inputs by recursively scanning SUCCESS markers. Historical results, synthetic fixtures, partial attempts and repeated downloads cannot add observations.

The remote analysis rechecks the registry against the actual formal files, protected source hashes and completed dependency chain. All 66 results and three saved-score analyses must match. The I1 seed-17 checkpoint contributes 18 audit rows but overlaps I1_all_seeds; the canonical PatchCore score analysis has 90 unique run/rule pairs, not 108 independent observations.

## Statistical contract

- Main comparison: 36 baseline fits, six MVTec AD categories, two methods and seeds 17, 29 and 43. First calculate an equally weighted six-category macro for each seed; then report the mean and sample standard deviation of the three seed macros with `ddof=1`. Retain per-category and per-seed values.
- Compare each method's native rule and the common max and top_0.01 rules with explicit labels. PaDiM native equals the final-map maximum; PatchCore native is its independent weighted score.
- PatchCore top_0.01 is the frozen primary improvement. Report matched category/seed changes against both native and max, including negative changes. Other q values are sensitivity analyses; do not select a new rule using test results.
- H1, H2, C2 and F1 are single-seed exploratory scans. Their standard deviation is absent, not zero. Include corresponding frozen baselines. C2 changes both selected layers and grid resolution; it does not isolate only layer count.
- C1 plus C1R supports three-seed paired random-versus-coreset comparisons on cable and screw. Label its two-category macro separately from the six-category main macro.
- LOCO logical and structural results are separate formal groups for each category and method. Pooled LOCO values are auxiliary and never enter the AD macro. LOCO has one seed and no seed standard deviation.
- Image rules reuse pixel metrics. Store pixel values once per fit/scope rather than treating repeated rule references as independent measurements. Thresholds remain per category, method, seed and rule; do not average thresholds across incompatible score scales.

Tables retain full precision. Rounding is for display only. CSV and JSON must describe the same numerical records.

## Resource contract

Reuse accepted A40/FP32 timing evidence with batch size one, twenty warmups and CUDA synchronization. Extraction is shared and counted once per cache. Fitting, feature reads/transfers, prediction, readback, CPU evaluation, saving and verification remain separate.

`predict_seconds` covers development plus test images. Cached prediction milliseconds per image therefore use `1000 * predict_seconds / (n_dev + n_test)`. This excludes backbone forward, image loading, feature reads/transfers and readback. A separately labelled cached pipeline sum may include feature reads/transfers and readback. Neither is end-to-end image inference. Existing totals do not establish median or P95 latency or isolated aggregation-rule overhead.

GPU allocated/reserved peaks cover fit feature transfer, fitting, warmup and prediction, excluding extraction. SLURM MaxRSS is a job-level CPU/evaluation measurement, not a per-method memory result. Model-state storage is derived from recorded shapes: PaDiM position means/inverse covariance and dimension indices, or PatchCore retained FP32 bank. Mark this as a tensor-storage estimate excluding the shared backbone, caches, allocator and Python overhead; it is not checkpoint-file size.

## Figures and case integrity

Use Python/Matplotlib in the existing locked TC2 environment. The local bundled runtime has NumPy and Pillow but no Matplotlib; no local plotting substitute or package installation is part of this workflow. Export English-labelled 300-dpi PNG previews and editable-text PDF figures with consistent method colours and source data. Record final rendered panel bounds and alignment checks.

The main comparison and LOCO figures accompany the handbook priorities:

- F1: the shared frozen backbone and the distinct PaDiM/ PatchCore model and score paths.
- F2: original image, ground-truth mask, PaDiM and PatchCore side by side.
- F3: parameter, component, sampling and few-shot comparisons with the correct baseline and seed scope.
- F4: score distributions, all frozen q values, and small/large-defect groups.
- F5: accuracy versus cached prediction cost, GPU memory and retained-bank storage.

Compute ground-truth anomaly area using the union of every original mask listed for that image. Small/large groups are the lowest/highest category-specific quarters ranked by anomaly area fraction with path tie-breaking. They are post-hoc explanatory groups and never select thresholds or configurations.

Select at most sixteen images by the fixed configuration: two per AD category and logical/structural representatives for each LOCO category. Preserve all candidates, selection reasons, image/mask hashes, result identities, scores and thresholds. Include at least two actual failures when available, prioritizing normal false positives and small-defect difficult examples. If an error type is absent, label the fallback honestly rather than manufacturing a failure.

Heatmap limits come from normal development maps and remain fixed across images for each method/category. Any clipping or pseudo-colour affects display only. The native and top_0.01 rules use identical anomaly maps; display their distinct image scores/decisions without claiming a localization change. Selected raw assets and small derived maps may be returned; full datasets and feature-cache NPY arrays remain on TC2.

## Sources, operation and outputs

The seven new files are `configs/analysis_tc2_gpu.json`, `scripts/analyze_results_tc2_gpu.py`, `scripts/plot_results_tc2_gpu.py`, `scripts/collect_analysis_tc2_gpu.py`, `scripts/slurm/analysis_tc2_gpu.sh`, `tests/test_analysis_tc2_gpu.py`, and this document. Only README and the external PowerShell helper change among existing implementation files. New validation evidence is stored under `run/validation_tc2_gpu/step8_20261019/` and fresh job/output directories. Preserve the Git index.

The external helper provides RunAnalysis, CollectAnalysis and RunAnalysis -ValidateOnly. Packaging validates inputs before any connection. Publication verifies the complete source/input archive and refuses conflicting existing bytes. Submission enters and verifies the project directory and passes it to sbatch with one node, one task, two CPUs, 8 GiB, fifteen minutes, MGPU-TC2/normal and no GPU request. It submits exactly one CPU job. Do not retry or increase resources automatically.

The CPU wrapper hides CUDA, runs the full tests and then generates the analysis. It imports no Torch and does not call model fit/predict APIs. New immutable outputs are under `run/tc2_gpu/summaries/analysis/<identity>/`; job evidence is under `run/validation_tc2_gpu/step8_job_<job>/`. Identities and output manifests bind configurations, source/input fingerprints and runtime evidence. Only fully verified outputs publish SUCCESS. Failed or partial outputs remain available for diagnosis and cannot qualify as completion.

Collection uses a pinned index and checked sequential pages. Compressed and decompressed page size remain at most 512 MiB; at most 32 pages and 512 members per page are permitted. Reject links, reparse points, traversal, duplicates, mixed snapshots, missing files and fingerprint mismatches. No whole dataset, cache or unrelated project directory is exported. Downloads use the existing terminal/password pattern and save a fresh local terminal.txt.

## Acceptance boundary

Local checks cover complete category/seed coverage, duplicate rejection, macro order, sample standard deviation, paired differences, checkpoint overlap, single-seed absence of standard deviation, LOCO separation, pixel invariance, mask union, case selection and hash/path corruption. Remote full mode additionally renders synthetic plot fixtures and then the accepted real inputs. Missing dependencies or skipped required checks fail full mode.

A completed CPU job, all returned pages, independent table/statistic validation, source/output fingerprint checks and visual review are required before local `step_8_complete=true`. Local implementation or a partial collection alone does not establish completion. Report writing, independent reproduction/delivery and any later numbered step remain outside this operation.
