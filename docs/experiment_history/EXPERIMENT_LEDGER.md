# Experiment ledger

This ledger indexes the original TC2 execution and returned acceptance evidence. It distinguishes actual fitting, saved-score analysis, postprocessing and collection repair. It does not report new measurements or certify the current checkout. The current workflow is documented in the [workflow guide](../guides/TC2_GPU_WORKFLOW.md); implementation decisions and original command examples are in the [implementation history](IMPLEMENTATION_HISTORY.md).

## Evidence and final status

The [archive index](../../archive/index.json) maps each original locator below to an immutable ZIP member, size and SHA256. These are archive locators, not live repository directories. The twelve-stage authority is `run/validation_tc2_gpu/step7_20261019/setup_status.json`, specifically `accepted_step_7_stages`; its shorter `previous_attempts` list is not the complete execution ledger.

Final step-8 authority is `run/validation_tc2_gpu/step8_figure_revision_20261019/setup_status.json`: `status=accepted`, `step_8_complete=true`, analysis job 44284 and figure-revision job 44303. The earlier `step8_20261019/setup_status.json` retains a pending snapshot. Its pending value does not mean the later accepted step remains incomplete.

The original external return root is:

```text
C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output
```

Collection IDs below identify child directories of that root. Source/receipt ZIPs in this repository do not replace the external scientific payloads or the reclaimed cluster's feature arrays.

## Preparation and pilot prerequisites

| Activity | Job | Accepted outcome and evidence locator |
| --- | --- | --- |
| Environment, weights and eight-category input acceptance | 43950 | `COMPLETED / 0:0`; historical setup configuration `configs/tc2_setup.json` and [step-2 account](implementation/STEP_02_SETUP.md), section 6.9 |
| Original metric reference acceptance | 43956 | `COMPLETED / 0:0`; `run/validation_v2/step3_20261019_081534/setup_status.json` |
| Metric regression after naming/submission repair | 43968 | `COMPLETED / 0:0`; `run/validation_tc2_gpu/step4_20261019/metric_regression_job_43968/` |
| Synthetic CPU/GPU algorithm acceptance | 43970 | `COMPLETED / 0:0`; `run/validation_tc2_gpu/step4_20261019/setup_status.json` |
| Synthetic workflow and FP32 cache acceptance | 44012 | `COMPLETED / 0:0`; `run/validation_tc2_gpu/step5_20261019/accepted_job_44012/verification.json` |
| Real-data bottle pilot | 44024 | Two accepted B0 seed-17/N100 fits; `run/validation_tc2_gpu/step6_20261019/accepted_job_44024/verification.json` |

Pilot job 44024 completed on TC2N01 in 00:02:33. Its final collection is `tc2_gpu_setup_20261019_135738_92cb31b0`. The two pilot fits are counted once within the frozen 66-fit matrix and were reused by B0. Synthetic acceptance fixtures are not additional formal fits. The recorded submit-directory repair preceded final pilot acceptance; no unverified failed job ID is assigned to that repair.

## Twelve formal stages

All twelve jobs below reached `COMPLETED / 0:0`, and their returned stage collections passed independent verification. "Fits verified" includes the two reused pilot fits in B0. A saved-score row is not a fitted model.

| Order | Stage | Job | Fits verified | Saved-score rows | Final external collection ID |
| --- | --- | --- | ---: | ---: | --- |
| 1 | B0 | 44053 | 12 (2 reused, 10 new) | 0 | `tc2_gpu_setup_20261019_151040_d90ef21c` |
| 2 | H1 | 44075 | 4 | 0 | `tc2_gpu_setup_20261019_153315_e4e97a14` |
| 3 | H2 | 44086 | 4 | 0 | `tc2_gpu_setup_20261019_161703_e990a53d` |
| 4 | C1 | 44103 | 2 | 0 | `tc2_gpu_setup_20261019_164545_67ec5487` |
| 5 | I1_seed17 | 44116 | 0 | 18 | `tc2_gpu_setup_20261019_165134_fdee4ac2` |
| 6 | R0 | 44121 | 24 | 0 | `tc2_gpu_setup_20261019_181750_bde0104b` |
| 7 | C1R | 44183 | 4 | 0 | `tc2_gpu_setup_20261019_184341_3832ab67` |
| 8 | C2 | 44198 | 4 | 0 | `tc2_gpu_setup_20261019_192322_56c530e4` |
| 9 | F1 | 44217 | 8 | 0 | `tc2_gpu_setup_20261019_194921_ca2d69de` |
| 10 | I1_all_seeds | 44227 | 0 | 54 | `tc2_gpu_setup_20261019_195436_8b9162cf` |
| 11 | I2 | 44230 | 0 | 36 | `tc2_gpu_setup_20261019_200008_71b44954` |
| 12 | B0_LOCO | 44235 | 4 | 0 | `tc2_gpu_setup_20261019_205219_dee60b36` |

Each row's receipt locator is `run/validation_tc2_gpu/step7_20261019/accepted_job_<job>/verification.json`, substituting its job ID. The B0/H1 receipts are in `archive/tc2_gpu/records_009.zip`; the remaining ten receipts are in `archive/tc2_gpu/records_010.zip`. The final stage registry itself is in `archive/tc2_gpu/records_012.zip`. The index records exact member names and fingerprints.

The complete set is **66 fits: two reused pilot fits plus 64 new fits**. Saved-score stages contain **108 source rows and 90 distinct observations** after the declared overlap between I1_seed17 and I1_all_seeds. Do not add the pilot to 66 or treat 108 rows as 108 independent observations. The stage registry records core, standard and full checkpoints as complete.

Historical fitting stages used TC2N01; I1_seed17 used TC2N02, and I1_all_seeds/I2 used TC2N01 without GPU fitting. The accepted fitting runtime was NVIDIA A40, driver 570.148.08 and CUDA build 12.8. These are observations and acceptance requirements of the historical experiment, not discovery results for a new allocation.

## Analysis and figure acceptance

| Activity | Job | Final external collection ID | Acceptance meaning |
| --- | --- | --- | --- |
| Analyze the verified 66-fit results and saved-score rows | 44284 | `tc2_gpu_setup_20261019_220347_4dc4d911` | `COMPLETED / 0:0`; computation/data verified, figure-layout revision required |
| Revise figure layout and verify final rendering | 44303 | `tc2_gpu_setup_20261019_223751_f596114b` | `COMPLETED / 0:0`; final step-8 acceptance |

Analysis receipt: `run/validation_tc2_gpu/step8_20261019/accepted_job_44284/verification.json`. Revision receipt: `run/validation_tc2_gpu/step8_figure_revision_20261019/accepted_job_44303/verification.json`. Both are in `archive/tc2_gpu/records_013.zip`.

Job 44284 ran on CPU and passed all 29 full tests, but its receipt explicitly retained `step_8_complete=false` pending layout repair. Job 44303 used two CPUs, 8 GiB and zero GPUs on TC2N07; its 22 full tests and complete 174-file payload passed. Independent acceptance preserved all 6,896 ordered source-data rows across fifteen figure groups, byte-identical tables/case registries and all 90 assets for sixteen unchanged selected cases. These postprocessing jobs add no fits or model predictions. Their verification statistics describe preserved artifacts, not new model-performance claims.

The final revised identity is `F8FBEF088CF879DE093C89009081CAD00B4698BB99BC3A6A080C748AFA4AA636` under `run/tc2_gpu/summaries/figure_revision/` in the original returned collection. The original analysis identity and outputs remain separate.

## Recorded failures and repairs

| Event | Evidence and outcome |
| --- | --- |
| B0 job 44047 failed before extraction/fitting | `step7_20261019/failed_job_44047/verification.json` under `run/validation_tc2_gpu/` records `FAILED / 1:0`, TC2N03, zero new results and a GPU/driver/CUDA comparison failure. Actual runtime values were not retained; the mismatching field is unknown. A scheduling supplement pinned fitting stages to TC2N01, and job 44053 passed. |
| First LOCO collection rejected job 44235's output | `step7_20261019/collection_failed_job_44235/attempt_20261019_202644_348368ec/verification.json` records the collection failure. The computational job succeeded. A dedicated collector verified logical/structural groups and five image rules, accepting the same job 44235 in the final collection. No refit occurred. |
| Analysis job 44271 lacked a published dependency | `step8_dependency_repair_20261019/job_44271_failure_verification.json` records `FAILED / 1:0` and a missing canonical `collect_experiments_loco_tc2_gpu.py`. Synthetic tests passed, but no scientific results were created. Publishing the accepted dependency preceded successful job 44284. |
| Job 44284 required figure-layout repair | Its accepted computation/data receipt above did not declare final step-8 completion. The approved layout/export supplement ran as job 44303 and preserved the scientific arrays, tables and cases. |

The table's abbreviated failure locators all start with `run/validation_tc2_gpu/`. The [index](../../archive/index.json) resolves their exact ZIP membership. Repairs are recorded separately from the failed snapshots; historical JSON and logs retain their original bytes and status.

## Current-source boundary

The original corrected TC2 GPU records, pre-correction results and current profile remain distinct. The remote deployment is unavailable. Legacy maintenance actions retain historical implementations behind current deployment/source acceptance gates. Any future deployment requires a new design and acceptance for its source and environment; this ledger and the repository restructuring make no claim of new remote verification. Report writing and packaging remain subsequent work.
