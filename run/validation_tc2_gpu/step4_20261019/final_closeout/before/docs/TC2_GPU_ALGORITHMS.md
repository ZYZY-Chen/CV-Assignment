# Step 4: TC2 GPU Algorithm Corrections and Acceptance

The user explicitly approved this design before implementation. It implements the **TC2 GPU Experiment Protocol** while preserving the exact frozen configs/protocol_v2.json, all manifests, dependency locks, existing logs, acceptance archives, and historical results. This step uses synthetic features only. Runner/cache integration belongs to step 5, and real-data pilots belong to step 6.

## Approved implementation

1. Validate nonempty, finite FP32 features, layer availability, dimensions, batch sizes, configurations, and fitted state. PaDiM requires at least two fitting images. GPU arithmetic uses disabled autocast and TF32. Invalid inputs fail explicitly.
2. Align PaDiM layers by nearest-neighbor interpolation to the highest selected resolution: 64x64 for the baseline, 32x32 for layer2+3, and 16x16 for layer3. Use CPU-seeded torch.randperm, sorted dimension indices, sample covariance with denominator N-1, fixed 0.01 identity regularization, FP32 inverses in position chunks of 256, and sqrt(clamp_min(Mahalanobis quadratic form, 0)). Do not add adaptive regularization or a pseudoinverse. Record actual shapes, indices, seeds, grid, and execution parameters.
3. Pool both PatchCore layers with 3x3 average pooling, stride 1, padding 1, count_include_pad=True. Bilinearly align layer3 to layer2 with align_corners=False. Pixel scores use one-neighbor Euclidean distance. Compute native image scores independently with the frozen nine-neighbor support/softmax formula, including the reference entry and capping support at bank size.
4. Preserve greedy k-center in the original feature space. Retain min(M, max(1, round(ratio*M))) entries using Python round. Uniform random sampling uses the same pool/count without replacement. Explicitly exclude selected indices even for identical features; resolve exact ties by global index. Save indices and seeds. Bound sampling temporaries with row chunks.
5. Query distances in FP32 with fixed direct torch.cdist computation, using query chunks of 1024 and bank chunks of 4096. Preserve the existing image chunk parameter. Compare chunk configurations, support small banks, and keep deterministic index tie-breaking. Record execution parameters rather than changing scientific settings.
6. Add shared postprocessing: bilinear interpolation to 256x256 with align_corners=False, followed once by sigma=4 Gaussian smoothing, a 33x33 unit-sum kernel, reflect padding 16, implemented as equivalent separable horizontal/vertical convolutions.
7. Add predict_padim and predict_patchcore returning anomaly_maps (N,256,256) and image_scores for native/max/top_0.001/top_0.01/top_0.05. PaDiM native equals the final-map maximum; PatchCore native is computed separately. Keep map-only compatibility wrappers and the existing four-rule scoring default. Five-rule aggregation requires an explicit native score.

## Files and limits

Modify only src/padim_adapter.py, src/patchcore_adapter.py, src/sampling.py, src/scoring.py, README.md, and the local output/tc2_gpu_setup.ps1 helper. Add src/anomaly_postprocess.py, tests/test_algorithms_tc2_gpu.py, scripts/slurm/check_tc2_gpu_algorithms.sh, and this document. Save implementation originals, fingerprints, local checks, and returned evidence under run/validation_tc2_gpu/step4_20261019/ and new job-specific validation directories.

Only comments made obsolete by these corrections are rewritten in English; unrelated existing Chinese is preserved. Do not modify run.py, feature_cache.py, data.py, metric_core.py, evaluate.py, existing metric tests, experimental configs, frozen inputs, installed dependencies, or old artifacts. No real-data fitting, feature extraction, formal outputs, benchmarks, or report writing occurs here.

## Acceptance order

1. Local syntax, import/contract checks where installed dependencies permit, transport rendering, strict upload lists, hash/path/conflict protections, and immutable-file verification. Do not install local dependencies.
2. Run the existing CheckMetrics CPU job first with 2 CPU, 4 GiB, 15 minutes, no GPU, requiring all 24 tests and the scikit-learn reference comparisons to pass under current naming. This deploys only its existing limited payload and retains prior evidence.
3. Add CheckAlgorithms. After the new metric acceptance passes, stage only the four corrected algorithm modules, shared postprocessing, algorithm tests, algorithm SLURM entry point, and the required read-only metric/evaluation/data/naming dependencies. Publish absent or identical files only; stop on unknown remote differences. Verify frozen protocol/manifests and actual environment exports. Submit one MGPU-TC2 / normal job, 1 GPU, 2 CPU, 8 GiB, 15 minutes, using the accepted dedicated environment. The job first checks CPU synthetic examples and then GPU computation. CUDA unavailability fails without CPU fallback.
4. Compare PaDiM means/covariances/distances with independent small references; test all frozen layer/dimension choices. Check exact full-matrix PatchCore nearest neighbors and native scoring, duplicate/tied features, support sizes, sampling uniqueness/count/seed, chunk equivalence, Gaussian constants/impulses/boundaries against independent NumPy convolution, five scores, FP32/finite outputs, unchanged inputs, and GPU real-feature-shape synthetic cases. Ordinary comparisons use atol=1e-5, rtol=1e-4; CPU/GPU comparisons use atol=rtol=1e-4. Indices, counts, shapes, and rule sets must match exactly where applicable. Do not silently loosen tolerances.
5. SSH passwords remain user-entered in the local terminal. Retrieve logs locally with the existing archive checks. Run one job at a time; Collect an unfinished job rather than resubmitting. Do not automatically increase resources or retry failures. Only passing metric regression and all CPU/GPU algorithm checks establish step_4_complete=true.

Historical acceptance remains valid for its recorded files; it does not imply that these changes or the unmodified legacy runner have passed new acceptance. Current implementation and acceptance status will be recorded after actual checks.

## Local implementation status and commands

The four algorithm modules, shared postprocessing, 19 CPU tests, two GPU tests, and the GPU entry point have been implemented. The helper's CheckAlgorithms payload contains exactly eleven files: the seven algorithm/test/SLURM files plus read-only metric_core.py, evaluate.py, data.py, and configs/tc2_gpu.json. It requires the latest current-naming full metric regression to pass, checks read-only source hashes against that record, and publishes only absent or identical files. It never broadens the earlier naming-only source replacement rules.

The local bundled Python has NumPy but no PyTorch. Local CPU algorithm execution therefore reports ModuleNotFoundError for torch rather than claiming a passed test; no dependency was installed. A separate local full-mode invocation was rejected by the Linux SLURM guard as expected. Syntax, independent NumPy reference sanity, and offline transport/publication checks are recorded separately and do not establish remote acceptance.

Run the first command in the local Windows terminal and return its terminal.txt path for verification:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action CheckMetrics
```

After that current metric regression has been verified as passed, use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1" -Action CheckAlgorithms
```

For an unfinished job, use the same entry point with `-Action Collect -JobId <returned-id>`. For packaging-only checks, add `-ValidateOnly` to CheckMetrics or CheckAlgorithms. Do not repeat a submission because the first snapshot is still queued or running.

Legacy YAML/runner settings, including the explicit old PatchCore sampling_seed=0, remain unchanged here. Step 5 must bind the scientific run seed into each method configuration and connect the new prediction API and FP32 cache contract. The synthetic tests use explicit seeds; they do not turn the legacy runner or old FP16 caches into accepted inputs.

## Recorded local verification

Local verification passed Python syntax checks for ten source/test files and five independent NumPy reference sanity cases. Offline helper validation rendered all twelve actions into seventeen remote shell commands, checked their Bash syntax and the new GPU wrapper, and passed output-archive round trips plus corrupt-hash and unexpected-path rejection. No SSH or SCP connection or SLURM submission occurred.

The actual rendered publication logic passed seven local fixtures: absent algorithm files, identical files, unknown existing files, missing metric acceptance, failed metric acceptance, changed read-only dependency hashes, and a corrupt bundle. Accepted fixtures staged exactly eleven files; rejected fixtures preserved existing file bytes and modification times. The wrapper requests one GPU, two CPU, 8 GiB, and fifteen minutes.

Packaging-only executions of both real helper actions also passed. Their local terminal records are output/tc2_gpu_setup_20261019_094832_7a78af8a/terminal.txt (CheckMetrics) and output/tc2_gpu_setup_20261019_094838_ae8ca7a9/terminal.txt (CheckAlgorithms). Both explicitly report validation only, without connection or submission.

See run/validation_tc2_gpu/step4_20261019/setup_status.json for the implementation fingerprint, scope audit, and separate verification results. The step remains incomplete until the current-naming metric regression and the full CPU/GPU algorithm job pass on TC2.

## Approved supplement: LF submission copies

The user explicitly approved this supplement after CheckMetrics attempt tc2_gpu_setup_20261019_095048_6b39e970. All frozen and payload hashes passed in that attempt, but sbatch rejected the metric wrapper's 24 CRLF lines before returning a job ID. No metric tests ran. The original terminal output remains unchanged and is copied byte-for-byte into the new step-4 audit record.

Change only the CheckMetrics and CheckAlgorithms submission blocks in output/tc2_gpu_setup.ps1. After existing staging and hash checks, create submission_lf.sh inside that attempt's newly created metrics_stage_<run-id> or algorithms_stage_<run-id> directory. Remove only carriage returns at line endings, validate the LF copy's shell syntax, record the original and submitted copy hashes in submission.sha256, and submit the LF copy with the existing sbatch options. Source scripts and upload bundles retain their exact bytes and hashes. These new submission records are included by the existing log collection mechanism.

Verify CRLF and LF inputs offline, confirm that conversion changes only line endings, preserve source bytes and modification times, compare resource directives and submission options with the approved values, and exercise file-conflict protections and failed submissions. Update only this design document, the two helper submission blocks, and new audit records. The algorithm and metric logic, frozen inputs, job resource limits, historical records, other helper actions, and existing acceptance entry-point files remain unchanged.

After local verification, retry CheckMetrics. Verify its returned full acceptance before proceeding to CheckAlgorithms. Only actual full CPU/GPU algorithm acceptance completes step 4.

The approved supplement is implemented and verified locally. Both helper blocks now create submission_lf.sh and submission.sha256 in their fresh attempt directories, preserve the verified original source, validate the copy before submission, and keep existing scheduler options. The actual rendered blocks passed sixteen offline fixtures across the two actions: LF, CRLF, existing copy, existing hash record, unsupported internal carriage return, invalid syntax, simulated submission failure, and invalid returned job ID. Failed cases preserved existing file bytes, modification times, and job pointers. Successful cases verified both fingerprints, the exact LF conversion, and unchanged resource directives.

All seventeen rendered commands passed Bash syntax checks. Output archive round trips and corrupt-hash/path rejection passed again. Real CheckMetrics and CheckAlgorithms packaging-only executions passed with five and eleven unchanged payload files, respectively, under local output records tc2_gpu_setup_20261019_095723_b437fb0d and tc2_gpu_setup_20261019_095724_f033567a. These checks made no network connection and submitted no actual job.

The supplement changed only the two authorized helper submission blocks and this document, plus new audit records. Both original SLURM wrappers, all algorithm/metric sources and tests, frozen files, dependency locks, prior terminal output, and the Git index were verified unchanged. New supplement evidence is recorded under run/validation_tc2_gpu/step4_20261019/submission_lf_20261019_095451/. Retry CheckMetrics using the command above; the previous rejected attempt provides no metric acceptance, and step_4_complete remains false.

## Current-naming metric regression accepted

After the approved LF submission repair, CheckMetrics job 43968 on TC2N01 completed as COMPLETED / 0:0 in sixteen seconds. All 24 tests passed with zero failures, errors, or skips, and full-mode step_3_complete=true. Across 81 scikit-learn references, maximum AUROC/AP absolute errors were 1.11e-16 / 2.22e-16, below 1e-12.

The returned archive SHA256 and all 150 extracted files were independently verified. All five accepted source hashes match the current checkout. The submitted LF wrapper differs from the original only by CRLF-to-LF conversion, both recorded fingerprints match, the current metric-job pointer identifies 43968, and the frozen manifests and actual environment locks remain unchanged. Evidence is retained under run/validation_tc2_gpu/step4_20261019/metric_regression_job_43968/. The prerequisite for CheckAlgorithms is satisfied. Step 4 remains incomplete pending its full 19-CPU-test and 2-GPU-test acceptance.
