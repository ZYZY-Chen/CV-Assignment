# TC2 GPU Experiment Protocol

The machine-readable [current protocol](../../configs/tc2_gpu/protocol.json) uses identifier ca6129_industrial_ad_tc2_gpu. [workflow.json](../../configs/tc2_gpu/workflow.json) records its current SHA256, and the [source manifest](../../configs/tc2_gpu/source_manifest.json) binds current source bytes.

The original frozen protocol and explanation remain byte-identical in the [historical archive](TC2_GPU_ARCHIVE.md). Their accepted identity is not replaced by the current file identity.

## Preserved scientific specification

| Invariant | Specification |
| --- | --- |
| Main dataset | MVTec AD: bottle, cable, capsule, screw, tile, wood |
| Extension | MVTec LOCO AD: juice_bottle, screw_bag |
| Frozen inputs | Eight manifests, 3,650 images, 1,019 masks |
| Backbone | Frozen ResNet18 with IMAGENET1K_V1 weights |
| Input and precision | RGB 256 x 256, FP32, no autocast or TF32 |
| Run seeds | 17, 29, 43 |
| Fitting subsets | Nested N20, N50, N100 |
| Full matrix | 66 fits: 62 AD and four LOCO |
| Saved-score analysis | 108 source rows, 90 distinct observations after declared overlap |
| Stage order | B0, H1, H2, C1, I1_seed17, R0, C1R, C2, F1, I1_all_seeds, I2, B0_LOCO |

PaDiM/PatchCore parameters, layers, anomaly-map processing, image scores, development thresholds and metric definitions remain as specified. Naming/storage/source metadata changes do not change numerical algorithm or plotting implementations.

The 66 configurations and run keys remain equivalent. Cache/result identity also includes protocol and source fingerprints, so historical results are not automatic current-profile reuse candidates. The original 64-new-fit execution plan reflected two already accepted historical pilot results; that reuse does not authorize new source.

## Configuration roles

- [workflow.json](../../configs/tc2_gpu/workflow.json): identity, output locations, historical-source references.
- [runtime.json](../../configs/tc2_gpu/runtime.json): unchanged numerical execution settings.
- [setup.json](../../configs/tc2_gpu/setup.json): input specification and current deployment state.
- [pilot.json](../../configs/tc2_gpu/pilot.json): two bottle fit specifications.
- [experiments.json](../../configs/tc2_gpu/experiments.json): full matrix, dependencies and resources.
- [analysis.json](../../configs/tc2_gpu/analysis.json): statistical/reporting specification.
- [figure_revision.json](../../configs/tc2_gpu/figure_revision.json): figure-revision policy.

Historical steps 1-8 retain their original acceptance evidence. Current source is checked locally; the reclaimed TC2 deployment is unavailable. Formal actions require acceptance for the current source/environment, rather than an old job ID or SUCCESS marker.

## Local inspection

From the repository root:

    python -I -B scripts/tc2_gpu/workflow/run_workflow.py plan
    python -I -B scripts/tc2_gpu/workflow/verify_archive.py

These commands do not fit models, extract caches or submit jobs. Environment template environment-tc2_gpu.yml and requirements-tc2_gpu-bootstrap.txt were not installed by this migration. requirements-tc2_gpu-lock.txt retains historical observed-version provenance.

See [naming rules](TC2_GPU_NAMING.md) and the [archive guide](TC2_GPU_ARCHIVE.md). Scientific returns remain in their original external collections.

See the [current lifecycle guide](TC2_GPU_WORKFLOW.md) for entry points and the [experiment ledger](../experiment_history/EXPERIMENT_LEDGER.md) for actual historical jobs. Legacy maintenance actions retain historical implementations behind the unavailable-deployment gate; future remote deployment requires a new design and acceptance.
