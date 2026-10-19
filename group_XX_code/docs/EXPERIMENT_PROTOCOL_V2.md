# TC2 GPU Experiment Protocol

The canonical workflow name is `tc2_gpu`: `tc2` means execution on the remote TC2 cluster; `gpu` means that formal experiments use GPU execution. CPU validation remains allowed. This display name aliases the frozen `ca6129_industrial_ad_v2` / `2.0.0` protocol. Preserve [protocol_v2.json](../configs/protocol_v2.json), its exact bytes and SHA-256, and this document's filename. The [naming map](../configs/tc2_gpu.json) and [naming design](TC2_GPU_NAMING.md) translate the frozen `run/v2/` output convention to `run/tc2_gpu/` for future execution, without changing experimental settings. Existing logs and acceptance archives retain their original names.

This protocol freezes the corrected industrial anomaly detection evaluation plan and separates future TC2 GPU experiments from the existing V1 historical results. The user approved the step-1 design on 19 October 2026, Singapore time; the protocol version is `2.0.0`.

The machine-readable specification in [protocol_v2.json](../configs/protocol_v2.json) is authoritative. This document explains its definitions and implementation dependencies. At protocol freeze, decisions were fixed and implementation was scheduled for validation in steps 2 through 6; the existing runner did not yet read this protocol, and the models, metrics, and GPU environment had not passed TC2 GPU acceptance.

## 1 Scope and fixed inputs

- The main experiment uses six categories from the original MVTec AD dataset: bottle, cable, capsule, screw, tile, and wood, requiring 62 fits.
- The LOCO extension uses juice_bottle and screw_bag, requiring four fits. Logical and structural anomalies are evaluated separately.
- Preserve the contents, SHA-256 values, and `split_hash` values of the eight existing category manifests. Their exact fingerprints are stored in the JSON protocol. Do not regenerate the development, fit-pool, or test splits.
- The split seed is `20261017`, and the run seeds are `17, 29, 43`. For each run seed, take the nested training lists of `20, 50, 100` images directly from the manifest. Both methods use the same lists.
- MVTec AD uses the existing approximately 20% holdout of normal training images as its development set; LOCO uses the existing official `validation/good` lists. Fit on normal images only and retain all official test images and masks.
- Convert inputs to RGB and resize the entire image to `256x256` using Pillow bilinear interpolation. Apply the ImageNet mean `[0.485, 0.456, 0.406]` and standard deviation `[0.229, 0.224, 0.225]`. Use neither center cropping nor random augmentation.
- Use a frozen ResNet18 backbone in eval mode with `torchvision.ResNet18_Weights.IMAGENET1K_V1`. Verify the actual weight-file hash in step 2 and record it in subsequent cache and run evidence.
- Use FP32 for feature extraction, feature-cache storage, fitting, scoring, and saved continuous predictions. Disable mixed precision and TF32. Evaluation counts and metric accumulation may use integers or float64 for numerical accuracy.

The project follows the handbook's lightweight backbone, inputs, and sample counts while retaining its own implementation. Its results must not be described as reproducing the original papers' best scores. TC2 GPU corrects implementation issues identified after inspecting V1 outputs; it must not be presented as a new blind evaluation conducted without prior observation of test results.

## 2 PaDiM definition

The baseline uses `layer1, layer2, layer3`, with ResNet18 feature shapes `64x64x64, 128x32x32, 256x16x16`, respectively, in channel, height, width order.

Align each selected layer to the highest spatial resolution among the selected layers using nearest-neighbor interpolation, then concatenate channels. The three-layer baseline has a `64x64` spatial grid; C2 uses `32x32` for `layer2+layer3` and `16x16` for `layer3` alone. C2 therefore studies the overall effect of the layer configuration, including its spatial-resolution change.

Select 100 dimensions from the concatenated channels for the baseline, with 50 and 200 dimensions as the additional H1 settings. The dimension seed equals the run seed: use a seeded CPU `torch.randperm`, take its first d indices, then sort and save them. At each spatial location, compute the sample mean and sample covariance with denominator `N-1`, and add `0.01 I` regularization.

Define the patch anomaly score as:

`sqrt(max((x - mu)^T inverse_covariance (x - mu), 0))`

This is the Mahalanobis distance with a square root. PaDiM's native image score is the maximum of the final `256x256` anomaly map defined in section 4. Each run records the actual layer names, feature shapes, selected dimension indices, dimension seed, regularization, and modeling grid.

## 3 PatchCore definition

The baseline uses `layer2, layer3`. Apply `3x3` local average pooling to each layer with stride 1 and padding 1, including padded values in the average. Bilinearly upsample layer3 to layer2's `32x32` grid with `align_corners=False`, then concatenate the results into 384-dimensional patch features.

The baseline memory-bank ratio is `0.05`. For a training feature pool containing M patches, retain `min(M, max(1, round(ratio * M)))` entries, using Python's definition of round. Keep greedy k-center selection in the original feature space without random projection. Use the run seed for the initial point, select distinct indices, and record the actual count, indices, and sampling seed.

C1/C1R sample the same number of entries uniformly without replacement from exactly the same feature pool. The sampled entries directly form the memory bank, without a further coreset operation. Both groups use the same nearest-neighbor query and postprocessing.

The pixel patch score is the Euclidean distance to the single nearest memory-bank entry. Compute the native image score separately:

1. Find the test patch with the largest nearest-neighbor distance and denote that distance by `d_star`.
2. Find that patch's nearest memory-bank entry, `m_star`.
3. Use the nine nearest memory-bank neighbors of `m_star`, including `m_star`, as the support set. If fewer entries exist, use the actual bank size.
4. Compute the distances from the selected test patch to all support entries and apply a numerically stable softmax to those distances.
5. Set the weight to `1 - softmax_distance[position_of_m_star]` and the native score to `weight * d_star`.

This score is independent of the final anomaly map. The parameter `9` specifies the number of support neighbors for the image score; it does not mean averaging nine nearest-neighbor distances for each test patch. Query distances in chunks and record the chunk size. Changes to execution parameters require output-equivalence validation under an approved design.

## 4 Anomaly maps and image scoring

For both methods, first bilinearly resize patch scores to `256x256` with `align_corners=False`, then apply fixed Gaussian smoothing: `sigma=4`, a `33x33` unit-sum kernel, reflect boundaries, and padding 16 on each side. The order is fixed: interpolate, then smooth.

Save the final continuous anomaly map as FP32. For pixel evaluation, bilinearly resize it to each original image's dimensions with `align_corners=False` and compare it with the original binary mask. Any required mask resizing uses nearest-neighbor interpolation only. Normal images have zero masks; use the union for anomalous images with multiple masks.

Save five image scores: `native, max, top_0.001, top_0.01, top_0.05`. The native score follows each method's definition; the other four use the same final `256x256` map. For top-q, let `K=max(1, ceil(q*H*W))` and take the arithmetic mean of the largest K pixels.

The prespecified main improvement is `top_0.01`; `top_0.001, top_0.05` are sensitivity analyses only. PatchCore is the required subject of I1/I2. Changing the image aggregation rule leaves the anomaly map unchanged, so pixel metrics must also remain identical. Heatmap normalization for display must not enter scoring or evaluation.

## 5 Thresholds and evaluation

For each method, category, run, and scoring rule, calibrate the threshold at the 95th percentile of the corresponding normal development scores, using linear percentile interpolation. Classify a test score as anomalous only when it is strictly greater than the threshold. Report the normal false-positive rate, anomaly recall, and recall by defect type. Do not search for an optimal threshold on the test set.

Report AUROC and AP for images and pixels. Pixel evaluation includes the zero masks of normal test images and uses every pixel at each category's original image resolutions. Group equal scores by threshold: tied positive-negative pairs receive half credit in AUROC, and AP follows the standard definition with equal scores grouped together.

Compute each of the six MVTec AD categories separately, then take an equally weighted macro average for each seed. Report the mean and sample standard deviation across the three seed-level macro averages, with `ddof=1`. Label single-seed parameter or component sweeps as exploratory; do not invent standard deviations. Evaluate LOCO normal versus logical anomalies and normal versus structural anomalies separately, outside the six-category main macro average. AUPRO remains optional; this step adds no implementation commitment for it.

## 6 Experiment matrix and order

Count a shared baseline fit only once when multiple analyses reuse it. Use the baseline settings above except for the factor being varied.

| Stage | Categories and methods | Variation | Additional fits |
|---|---|---|---:|
| B0 | Six categories, both methods, seed 17 | N=100 baseline | 12 |
| H1 | PaDiM on cable and screw, seed 17 | 50 and 200 dimensions; reuse B0 for 100 | 4 |
| H2 | PatchCore on cable and screw, seed 17 | Coreset 1% and 10%; reuse B0 for 5% | 4 |
| C1 | PatchCore on cable and screw, seed 17 | Random memory bank of equal size | 2 |
| R0 | Six categories, both methods | Add baseline seeds 29 and 43 | 24 |
| C1R | PatchCore on cable and screw | Add random-bank seeds 29 and 43 | 4 |
| C2 | PaDiM on cable and screw, seed 17 | layer2+3 and layer3 alone; 100 dimensions each | 4 |
| F1 | cable and screw, both methods, seed 17 | N=20 and 50; reuse B0 for N=100 | 8 |
| LOCO B0 | Two categories, both methods, seed 17 | N=100 extension | 4 |

The execution order is `B0 -> H1 -> H2 -> C1 -> I1(seed 17) -> R0 -> C1R -> C2 -> F1 -> I1(three seeds) -> I2 -> LOCO B0`. The first four groups form the minimum version with 22 fits. The standard six-category version has 62 fits, or 66 with LOCO.

I1 compares native, max, and top 1% on available baseline runs. I2 evaluates top 0.1% and top 5% on the six-category, three-seed PatchCore baselines. Both score saved predictions and require no additional fitting.

## 7 GPU environment and cache dependencies

Run formal computation on CCDS GPU Cluster TC2, allocating compute nodes through sbatch. Use the head node for account and resource queries, file management, and job submission; do not run experiments or GPU probes there. Verify the actual partition, QoS, GPU, driver, dependencies, and resource limits for the account in step 2 instead of copying historical examples from the user guide.

Formal GPU jobs respect the devices exposed by SLURM. A requested GPU job must fail explicitly if CUDA is unavailable. Use CPU for local metric validation, aggregation, and plotting; record a separate CPU evaluation phase independently. Resource comparisons separately record feature extraction, fitting, prediction, and evaluation, including the scope of I/O and preprocessing. Compare the same GPU model under the same protocol, with prediction batch size 1, 20 warm-up iterations, and CUDA synchronization.

Step 2 prepares the environment, raw data, and weights and audits old caches. Step 5 implements TC2 GPU cache support; step 6 generates and validates the FP32 caches needed for pilots, and subsequent formal extraction follows that process. Existing FP16 caches are historical inputs and do not satisfy the TC2 GPU cache-storage precision requirement.

Cache and run evidence records the actual weight hash, preprocessing, layer configuration, data lists, precision, and corresponding code, together with the actual software, driver, hardware, seeds, phase timings, memory-statistics scope, and SLURM job ID. Every TC2 GPU run also records the SHA-256 of the protocol JSON's exact bytes and its effective configuration.

## 8 Historical results and TC2 GPU outputs

[legacy_v1_inventory.json](../run/legacy_v1_inventory.json) indexes the historical results relative to the repository root. The baseline commit is `0828b30ebd030bcf55002d3efb4a69f73ccb930c`. The 66 existing runs contain 337 files within experiment directories, plus nine run-level summaries or logs, for 346 historical files in total. The inventory stores paths, sizes, and SHA-256 values and records the eight category manifests and the old source baseline.

Keep historical files in place. The inventory is neither a separate backup nor proof of scientific correctness. Old SUCCESS markers do not establish TC2 GPU acceptance. Preserve the original state of the seven runs marked as having recomputed image scores. Address inconsistencies between historical metrics and score columns in the later unified workflow; do not relabel V1 files as TC2 GPU.

Resolve TC2 GPU paths relative to `group_XX_code`:

| Content | Required path |
|---|---|
| Historical results | `run/results/` |
| TC2 GPU root | `run/tc2_gpu/` |
| Experiment results | `run/tc2_gpu/results/` |
| Logs | `run/tc2_gpu/logs/` |
| Summaries | `run/tc2_gpu/summaries/` |
| Resource measurements | `run/tc2_gpu/resources/` |
| FP32 feature caches | `run/tc2_gpu/feature_cache/` |

This step establishes path conventions only; step 5 implements directory switching and skip rules. Skip only validated TC2 GPU runs whose protocol, effective configuration, and input fingerprints all match. A V1 completion marker must not cause a TC2 GPU run to be skipped.

Metrics and saved scores must come from the same arrays. Before declaring success, verify prediction counts, path order, labels, finite values, and metric reproducibility. Generate SUCCESS only after these checks pass.

## 9 Step-1 changes and acceptance scope

This step adds this document, `configs/protocol_v2.json`, and `run/legacy_v1_inventory.json`, with limited README updates explaining version status. Preserve all other source, existing experiment configurations, manifests, dependency files, historical results, and caches. Retain the user's pre-existing `.gitignore` modification as it was.

Acceptance checks JSON parsing, agreement between the documentation and configuration, complete indexing of all 66 historical runs, and unchanged before/after hashes for protected files. The full directory fingerprint comparison permits only the three additions above and README changes. Version-control internals and IDE state directories are excluded from the content inventory.

Environment installation, data downloads, source fixes, cluster jobs, TC2 GPU output activation, cache extraction, and experiments follow the separately approved designs of later steps. Completion of step 1 does not establish completion of those tasks.

## 10 Change control and references

Describe every modification in the corresponding step's design and execute it after discussion and user confirmation. Changes affecting this protocol require a new version and separation of affected results; do not silently change parameters based on test performance. If resource validation or pilots reveal a necessary adjustment, revise the design before execution.

Use the following fixed references when checking methods:

- [PaDiM paper](https://arxiv.org/abs/2011.08785)
- [PatchCore paper](https://arxiv.org/abs/2106.08265)
- [Anomalib v2.0.0 PaDiM](https://raw.githubusercontent.com/openvinotoolkit/anomalib/v2.0.0/src/anomalib/models/image/padim/torch_model.py)
- [Anomalib v2.0.0 PatchCore](https://raw.githubusercontent.com/openvinotoolkit/anomalib/v2.0.0/src/anomalib/models/image/patchcore/torch_model.py)
- [Anomalib v2.0.0 PatchCore anomaly map](https://raw.githubusercontent.com/openvinotoolkit/anomalib/v2.0.0/src/anomalib/models/image/patchcore/anomaly_map.py)

Anomalib is a fixed algorithmic reference for this protocol. It does not require installing the package in this step or replacing every model implementation.
