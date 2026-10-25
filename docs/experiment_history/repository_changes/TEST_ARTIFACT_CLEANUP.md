# Temporary test artifact cleanup

> Historical repository-change record. Paths and status in the account below describe that accepted batch. Use the [current workflow guide](../../guides/TC2_GPU_WORKFLOW.md) for current entry points and the [archive guide](../../guides/TC2_GPU_ARCHIVE.md) for original bytes.

## Scope and outcome

On 2026-10-25, the approved cleanup removed 18 temporary offline-fixture and simulated-transport directories after a complete, verified ZIP backup. The removed workspaces contain 1,383 files totaling 68,235,216 bytes (about 65.1 MiB). They are not the real TC2 GPU experiment results.

The purpose is to resolve long physical worktree paths. Before cleanup, two file paths were 260 characters long and 143 paths were at least 240 characters long. Removing the approved workspaces reduces the longest remaining original worktree path to 239 characters under the current repository root. The path check excludes `.git/`, `.idea/` and external historical backups.

## Exact deletion whitelist

All paths below are relative to `run/validation_tc2_gpu/`. Parent directories and their outer reports remain in place. No other temporary directories are selected by wildcard.

| ID | Removed directory |
| --- | --- |
| 01 | `step4_20261019/submission_lf_20261019_095451/transport_validation_38364a3f` |
| 02 | `step6_20261019/offline_tests_03/archive_6390120ec2` |
| 03 | `step6_20261019/offline_tests_03/archive_6ad3815ac8` |
| 04 | `step6_20261019/offline_tests_03/archive_f834d73e3e` |
| 05 | `step6_20261019/offline_tests_04/archive_2beafc3d99` |
| 06 | `step6_20261019/offline_tests_04/archive_e63c7a8252` |
| 07 | `step6_20261019/offline_tests_04/archive_ead27cad01` |
| 08 | `step7_20261019/collector_extra_ee291be9` |
| 09 | `step7_20261019/collector_fixture_9f08b94430` |
| 10 | `step7_20261019/loco_collection_supplement_20261019/experiments_transport_d7ac157d` |
| 11 | `step7_20261019/loco_collection_supplement_20261019/transport_validation_0042369a` |
| 12 | `step7_20261019/offline_01/analysis_0a8fe47f` |
| 13 | `step7_20261019/offline_02/analysis_169ba77c` |
| 14 | `step7_20261019/offline_03/analysis_0933ee3b` |
| 15 | `step7_20261019/offline_04/analysis_b12bfbe5` |
| 16 | `step7_20261019/offline_final/analysis_f107c4b0` |
| 17 | `step7_20261019/scheduling_tc2n01_20261019/experiments_transport_75726d7b` |
| 18 | `structure_batch1_1025_83b82ab8/w/c10` |

The last workspace contains a negative-test fixture from the successful workflow core suite. Removing its generated cache files does not remove or change the outer 16-test result.

## Preserved evidence

Outer `offline_tests.txt`, `core_tests.txt`, `setup_status.json`, final verification reports, independent reviews and real `accepted_job_*` directories remain at their original locations with unchanged bytes. Formal results, scientific code, tests, configurations, frozen protocol, manifests, dependency locks and the Git index are also unchanged.

The deleted workspaces include 47 simulated `terminal.txt` files, 17 simulated `setup_status.json` files, 21 simulated `page_verification.json` files and six negative-test `FAILED.json` files. These inner files are preserved in the external backup with their original names and contents; they are no longer live worktree files. A simulated status or completion marker is not evidence of a real TC2 job.

The original root-migration backup and acceptance record remain unchanged. This cleanup has its own manifest and verification record, which describe the later worktree state.

## Backup and recovery

The external course-output record is:

```text
output/tc2_gpu_cleanup_20261025_154510_33c37e36/
```

Its archive is `test_artifacts.zip`, with SHA256:

```text
BAE0018EEC589EBC715C296F5AD2AD1C508A37F65F34AE7DD3B6FE3AC48F926C
```

The [cleanup manifest](../../../archive/index.json) (archived path: `run/validation_tc2_gpu/path_cleanup_01/cleanup_manifest.json`) lists every removed repository-relative path, ZIP member, byte size and SHA256. ZIP members use the original repository-relative paths. All 1,383 file members were read back and verified before deletion; no physical extraction was needed.

For inspection, locate a member using the manifest and read it directly from the ZIP. For recovery, extract the selected workspace into a shallow staging directory and verify its files against the manifest. Restoring the original deep layout under the current project root would recreate its long-path issue.

The archive stays outside the repository and is not automatically staged or committed. No replacement `fixtures/f001` storage layout is introduced.

## Verification boundary

The [cleanup verification](../../../archive/index.json) (archived path: `run/validation_tc2_gpu/path_cleanup_01/verification.json`) records the exact deleted set, protected-file integrity, remaining path lengths, source fingerprints, unchanged 66-fit experiment plan and Git state.

The original metric and workflow core reports retain their nine and 16 passing tests. This cleanup checks those report bytes and source bindings; it does not claim a new test run. No fixtures, feature extraction, model fits, downloads, SSH connections or SLURM submissions are generated by this operation.

For future local checks, choose a fresh, short validation-directory identifier and check the projected full path length before generating nested fixtures. This is an operating convention; existing scientific code and tests were not modified.

