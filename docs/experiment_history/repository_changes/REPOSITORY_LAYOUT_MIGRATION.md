# Repository layout migration

> Historical repository-change record. Paths and status in the account below describe that accepted batch. Use the [current workflow guide](../../guides/TC2_GPU_WORKFLOW.md) for current entry points and the [archive guide](../../guides/TC2_GPU_ARCHIVE.md) for original bytes.

## Current layout

On 2026-10-25, the contents of the former `group_XX_code/` directory were moved directly into the repository root. The root now contains `configs/`, `docs/`, `manifests/`, `run/`, `scripts/`, `src/` and `tests/`, together with the existing entry point, dependency files, notices and course PDF. The existing root-level `datasets/` directory stays in place.

Run commands from the repository root. For read-only planning:

```powershell
python -B scripts/run_tc2_gpu.py plan
```

The [formal workflow entry point](../../../archive/index.json) (archived path: `scripts/run_tc2_gpu.py`) keeps its existing actions and names. The [legacy entry point](../../../archive/index.json) (archived path: `run.py`) remains a historical workflow; correcting its data path does not make its old results formal TC2 GPU results.

## Path mapping

The mapping for every migrated file is:

```text
group_XX_code/<relative-path> -> <relative-path>
```

For example, the former `group_XX_code/scripts/run_tc2_gpu.py` is now `scripts/run_tc2_gpu.py`. The former local absolute code-root prefix maps to this repository root.

Earlier `cd group_XX_code` instructions, including those in the unchanged [dataset notes](../../../datasets/README.md), refer to the old layout. Historical examples in script docstrings also remain as originally written. Use the repository root for current commands; the data directory is now `<repository-root>/datasets`.

Original paths inside historical JSON, logs, handoff notes and source snapshots describe their recorded execution context. Locate those files using the migration map; do not rewrite historical paths or recorded SHA256 values. The mapping does not imply that old cluster paths still exist.

## Approved content changes

Only the following existing files received content changes:

- `.gitignore`: remove the old wrapper prefix from the download-script comment and two cache rules.
- `run.py`, `scripts/download_datasets.py`, `scripts/extract_features.py`: point the default data path at the root-level `datasets/`.
- `scripts/make_manifests.py`: correct the same default and only the corresponding path token in its argument help. Its earlier docstring example remains historical.
- `README.md`: prepend an English migration notice, retaining all original bytes.
- The external `output/tc2_gpu_setup.ps1`: change only its default local code root to the repository root.

This guide is the only new project document in this batch. The external helper remains in its original location.

## Preserved materials

All original files were included, including files that Git did not track or ignored. The initial inventory contains 7,558 files totaling 612,998,588 bytes: 440 tracked files, 7,115 untracked files and three ignored files. The inventory includes long paths, the old feature cache and historical bytecode files.

The frozen [protocol](../../../archive/index.json) (archived path: `configs/protocol_v2.json`), [protocol explanation](../../../archive/index.json) (archived path: `docs/EXPERIMENT_PROTOCOL_V2.md`), manifests, environment locks, formal scientific sources, old results, logs and original acceptance records retain their bytes. The internal names and layout of `run/` also remain unchanged. Future test fixtures are written only to a fresh migration-specific validation directory.

No `v1/v2` names, scientific parameters, source-fingerprint maps or result identities were changed. The complete prior Git index and HEAD were preserved. Script regrouping, naming unification, historical archiving and broader documentation cleanup belong to subsequent batches.

## Evidence and local validation

The external course-output record is named:

```text
tc2_gpu_structure_batch1_20261025_150436_83b82ab8
```

It contains the complete verified pre-migration backup, `baseline.json`, `files_before.json`, `migration_map.json`, `files_after.json`, approved file differences, check output and final `verification.json`. The backup is outside the repository and is not automatically added to Git.

Validation covers complete file mapping and hashes, protected source fingerprints, default data paths, Python syntax, PowerShell parsing, identical 66-fit planning, and the existing metric/workflow core suites. Check outputs use a fresh `run/validation_tc2_gpu/structure_batch1_<timestamp_id>/` directory. They are local checks and do not overwrite earlier acceptance records.

The metric core suite passed all nine tests. The workflow core suite passed all 16 tests in `run/validation_tc2_gpu/structure_batch1_1025_83b82ab8/w/`, with no skipped tests. All 44 current Python files passed syntax compilation without generating bytecode, and all 70 path-keyed source-fingerprint checks in the unchanged configurations passed. The external PowerShell helper passed parsing and default-root checks without execution.

The first workflow-core attempt used the longer migration-record identifier for its fixture directory and encountered Windows path-length errors in seven cache tests. That failed snapshot is retained under `run/validation_tc2_gpu/structure_batch1_20261025_150436_83b82ab8/workflow_core/`. Only the fixture output path was shortened for the successful retry; project sources and tests were not changed.

The TC2 allocation has been reclaimed. No SSH connection, SLURM submission, dependency installation, feature extraction, model fit or new GPU acceptance is part of this migration. Historical GPU acceptance remains evidence for its recorded sources and environment.


## Supplement: temporary test artifact cleanup (2026-10-25)

After the root migration above, 18 explicitly approved temporary fixture and simulated-transport directories were removed to resolve the remaining long worktree paths. Their 1,383 files (68,235,216 bytes) were completely backed up and verified before deletion. This supplement changes the later worktree state; the original migration acceptance record remains unchanged.

The removed inner simulated logs, statuses and negative-test artifacts remain byte-identical in the external ZIP. Outer real test logs and final acceptance records remain in place, including the nine-test metric report and the 16-test workflow report above. Only the workflow report's temporary c10 fixture subtree was removed.

See [Test artifact cleanup](TEST_ARTIFACT_CLEANUP.md) for the deletion whitelist, backup identity, path budget and recovery method. The [cleanup manifest](../../../archive/index.json) (archived path: `run/validation_tc2_gpu/path_cleanup_01/cleanup_manifest.json`) maps every removed repository-relative file path to its unchanged ZIP member. No fixtures/f001 storage directories were introduced.
