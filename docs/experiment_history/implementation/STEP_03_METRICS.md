# Step 3: Metric Corrections and Reference Acceptance

> **Current profile and historical-record boundary (2026-10-25)**
>
> The retained design and acceptance account below describes the earlier implementation. Its job IDs, source hashes, remote paths, command blocks and completion flags are historical. Exact original bytes are in the [archive index](../../../archive/index.json); they do not certify this refactored checkout.
>
> Current configurations are under configs/tc2_gpu/, and independent fingerprints are in configs/tc2_gpu/source_manifest.json. The current deployment is unavailable. Formal actions refuse execution without new source/environment acceptance. Historical SSH and submission examples below are not current connection instructions.
>
> Use the [current workflow guide](../../guides/TC2_GPU_WORKFLOW.md), [protocol](../../guides/TC2_GPU_PROTOCOL.md), [naming rules](../../guides/TC2_GPU_NAMING.md) and [archive guide](../../guides/TC2_GPU_ARCHIVE.md) for current paths. The [experiment ledger](../EXPERIMENT_LEDGER.md) records final historical completion; pending flags below retain their snapshot meaning.

## Historical design and acceptance account


This guide belongs to the **TC2 GPU Experiment Protocol**, workflow `tc2_gpu`; see [TC2_GPU_NAMING.md](../../../archive/index.json) (archived path: `docs/TC2_GPU_NAMING.md`). Current metric metadata uses `tc2_gpu_tie_grouped`. Job 43956 and its archived `v2_tie_grouped` metadata remain unchanged. Current entry points and future validation records use `tc2_gpu`; archived paths below retain their original names. The naming change preserves metric calculations and does not claim a new full remote acceptance; its local checks are recorded in `run/validation_tc2_gpu/naming_20261019/`.

The user explicitly approved the step-3 changes. This design implements the frozen protocol_v2.json without changing the protocol or splits. Step 3 was completed on 2026-10-19: local core checks and full reference acceptance in TC2 job 43956 passed, as did verification of returned files, source fingerprints, and change scope.

## 1 Approved corrections

1. Image and pixel AUROC give tied positive-negative pairs half credit. AP weights precision at each grouped score threshold by the recall increment; it does not use trapezoidal PR area. When all scores tie, AUROC=0.5 and AP equals the positive fraction, independently of input order.
2. Keep every original-resolution pixel and continuous FP32 score. Normal images use zero masks; combine multiple masks by union. Resize continuous maps bilinearly with align_corners=False and masks with nearest-neighbor interpolation only. The metric core performs one exact sort, counts tied groups in chunks, and correctly merges ties across chunk boundaries. It neither quantizes scores nor samples pixels, and creates no full-length float64 score or cumulative arrays. Counts use integers; metric accumulation uses float64.
3. Compute the threshold only from the corresponding normal development scores at the 95th percentile, explicitly using NumPy method=linear. A test prediction is anomalous when score > threshold. Verify that all development samples are normal, development and test paths are disjoint, and all score, label, and anomaly-map counts agree.
4. Raise explicit errors for empty inputs, invalid or missing classes, NaN/Inf, and dimension or size mismatches. Do not emit unexplained NaN or substitute values. Formal image and pixel binary evaluation requires both normal and anomalous samples. Anomalous entries must provide masks; normal entries must not carry anomaly masks.
5. Evaluate LOCO normal versus logical anomalies and normal versus structural anomalies separately. Once LOCO groups are detected, reject missing normal samples, either missing anomaly group, or any unexpected anomaly group. Retain top-level pooled results as auxiliary output; groups remain the formal evaluation units.
6. Preserve existing metric fields and add a metric_policy identifier. Accept exactly matching valid scoring-rule sets for development and test data, supporting the original four rules and a subsequently supplied native score. Score generation is outside this step.

## 2 Files and scope

- Add src/metric_core.py: a NumPy-only metric core and array validation.
- Modify src/evaluate.py: integrate the core, threshold, input, and group checks, and evaluation-policy metadata.
- Add tests/test_metrics_tc2_gpu.py: standalone core checks, scikit-learn comparisons, and synthetic image/mask tests using standard-library unittest, with no additional dependency installation.
- Add scripts/slurm/check_tc2_gpu_metrics.sh: the CPU acceptance entry point on TC2 compute nodes.
- Modify the local output/tc2_gpu_setup.ps1: add CheckMetrics, limiting uploads to the metric core, evaluator, tests, CPU entry point, and a read-only copy of existing data.py; Collect retrieves current run/validation_tc2_gpu logs and preserved run/validation_v2 logs through an explicit path allowlist.
- Use this document, README, and run/validation_tc2_gpu/step3_<id>/ for the design, evidence, and status. Pre-step-3 fingerprints and originals of the helper/evaluator are saved in step3_20261019_081534.

Preserve models, score generation, raw data, the frozen protocol, manifests, environment and dependency locks, pre-correction results, and old caches. Do not recompute old results, fit models, or start formal run/tc2_gpu experiments. Cross-category/seed aggregation and runner integration remain in their respective later steps.

## 3 Acceptance order and resources

1. Local NumPy core checks cover complete and partial ties, permutation invariance, ties across chunks, perfect/reversed rankings, imbalance, and invalid inputs. Small fixed examples use independent positive-negative pair and threshold enumeration as references.
2. Local offline transport checks cover PowerShell/Bash syntax, limited uploads, refusal of differing existing files, archive hashes and path protection, and continued rendering of existing actions. They do not connect to the cluster.
3. TC2 CheckMetrics reuses the accepted dedicated environment on MGPU-TC2 / normal with one node, one task, 2 CPU, 4 GiB, and 15 minutes, requesting no GPU. Run one preparation or acceptance job for this user at a time. Do not compute metrics on the head node.
4. Full acceptance compares identical arrays with scikit-learn 1.7.2, requiring AUROC/AP absolute errors <=1e-12. Synthetic tests cover the 95th percentile, equality to the threshold, development/test isolation, zero masks, mask union, nearest-neighbor resizing, rectangular originals, and LOCO groups. Check four/five-rule compatibility and that evaluation does not modify input arrays.
5. Remote execution requires the latest step-2 all-mode acceptance to have passed. First verify the frozen protocol and eight manifest hashes and confirm the environment/exports agree with step 2. Publish test source only when absent or hash-identical; stop on unknown differing files without overwriting. Store results and source hashes in run/validation_tc2_gpu/step3_job_<jobid>/. Only a fully passing full-mode run emits step_3_complete=true; passing core mode alone does not complete this step.

The user continues entering SSH passwords in the local terminal. CheckMetrics checks, uploads, and submits one CPU job, waiting up to approximately 40 seconds to retrieve a snapshot. If unfinished, use Collect for that same job ID without resubmitting. New records use run/validation_tc2_gpu/; existing run/setup_v2/ and run/validation_v2/ evidence remains intact.

## 4 References and implementation status

- [scikit-learn 1.7 AP](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.average_precision_score.html)
- [scikit-learn 1.7 AUROC](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.roc_auc_score.html)
- [NumPy 1.26 percentile](https://numpy.org/doc/1.26/reference/generated/numpy.percentile.html)

Local and remote acceptance have both passed. See sections 5 and 6 for results and evidence paths.

## 5 Completed local implementation and validation

The metric core and evaluation entry point implement the scope above. Image and pixel evaluation share the same grouping core and explicitly reject missing classes in formal binary evaluation. Input protection also covers duplicate paths, relative-path traversal, missing required metadata, masks attached to normal images, and absent masks for anomalous images. LOCO is recognized from group names or mvtec_loco paths, preventing it from being treated as ordinary AD when all group names are absent. Existing output fields remain compatible with the original four rules; the same entry point accepts five rules. Pixel results are independent of the image aggregation rule.

The final local core record is `run/validation_v2/step3_local_core_final_20261019/setup_status.json`. All nine tests passed, covering independent enumeration references, multiple chunk sizes, cross-chunk ties, permutation invariance, and adjacent FP32 values. They used the existing local Python 3.12.14 / NumPy 2.3.5 without installing dependencies; this does not replace full acceptance under TC2's fixed NumPy 1.26.4 / scikit-learn 1.7.2. A separate local full-mode invocation was rejected by the Linux SLURM guard as expected, recorded in step3_local_full_guard_20261019; it was not a remote test failure.

Offline transport validation covered the existing ten actions plus CheckMetrics: rendering and Bash syntax for 15 remote commands, retrieval from both log directories, and rejection of bad archive hashes and paths. The actual rendered publication code was also checked with four synthetic cases: an absent destination, identical files, unknown conflicts, and a damaged bundle. Only the five approved files were published, and data.py matched its pre-change contents. All these calls used local substitutes without connecting to or submitting jobs on the cluster.

The local acceptance entry point used was:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action CheckMetrics
```

Add `-ValidateOnly` to inspect packaging without connecting remotely. If a job is queued or running, use the same entry point with `-Action Collect -JobId <returned-id>` only. This job is already complete and requires no resubmission.

## 6 Full TC2 acceptance and step-3 completion

TC2 job 43956 completed on TC2N01 on 2026-10-19 with state COMPLETED / 0:0 in 19 seconds. It used the dedicated environment accepted in step 2, with 2 CPU, 4 GiB, and a 15-minute limit, to run synthetic tests. It requested no GPU and performed no model fitting or formal experiments. The recorded Python 3.10.22, NumPy 1.26.4, scikit-learn 1.7.2, torch 2.11.0+cu128, torchvision 0.26.0+cu128, and Pillow 12.3.0 matched the fixed environment.

All 24 full-mode tests passed, with zero failures, errors, or skips. Across 81 scikit-learn comparisons, the maximum absolute errors were 1.1102230246251565e-16 for AUROC and 2.220446049250313e-16 for AP, both below the agreed 1e-12 limit. Tests covered ties and chunk boundaries, all pixels at original resolution, zero masks and multiple-mask unions, development-threshold isolation, strict greater-than classification, four/five scoring rules, separate LOCO anomaly groups, and invalid-input rejection. The remote full-mode status is `step_3_complete=true`, and stderr is empty.

Independent local verification confirmed the returned archive SHA-256 as `E4D4112A233B39754EB10BC35E877F820379B00588BC525C3A8DBFCDF041515A`. All 100 regular files matched the downloaded contents byte for byte; member paths and types passed verification. At the recorded acceptance time, the five source files had identical hashes in local files, the upload payload, remote stage manifest, and test record. The frozen protocol, eight manifests, environment exports, dependency locks, and step-2 completion record were preserved. Of the 750 pre-step-3 files, only the approved evaluate.py and README changed; all 346 pre-correction files were preserved, and no formal run/tc2_gpu directory was created.

Evidence is stored in `run/validation_v2/step3_20261019_081534/`:

- `setup_status.json`: final step status and implementation fingerprints.
- `remote_job_43956/verification.json`: independent retrieval verification, source consistency, and scope checks.
- `remote_job_43956/snapshot_20261019_083700_13089bef/`: terminal record, complete archive, and expanded status/log files. All synthetic PNGs remain in the archive.

Completion of this step does not establish acceptance of the runner, model implementations, or formal TC2 GPU results. Continue under the user's design-and-confirmation process for each subsequent step.
