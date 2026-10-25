# TC2 GPU historical archive

The [archive index](../../archive/index.json) connects original relative paths, ZIP members, source commits, purposes and exact SHA256 fingerprints. Historical bytes are not rewritten to appear to come from current source.

## Project-contained packages

There are 20 ZIP packages, each at most 32 MiB. Each file remains one whole member; packages are not fragments of a split ZIP.

| Package | Purpose |
| --- | --- |
| archive/pre_correction/artifacts.zip | Old 66-run results, summaries, logs and original inventory |
| archive/pre_correction/source_original.zip | 23 original baseline source files verified against the inventory |
| archive/pre_correction/source_at_refactor.zip | Twelve removed legacy entry/config files as captured at this refactor |
| archive/tc2_gpu/source.zip | Pre-refactor source, configuration, document and environment originals |
| archive/tc2_gpu/records_*.zip | 5,976 retained setup and validation records |

The snapshot baseline is commit 84c4ba4c42a8ea08aabd7e74af3d07185bbc509f. A file is described as historically accepted only when its bytes match the original accepted SHA. Legacy entry points at refactor time already included earlier changes and are not mislabeled as the earliest results' original source.

The inventory records 346 old files. Two missing HANDOFF files were recovered only into archive members from commit 0828b30ebd030bcf55002d3efb4a69f73ccb930c. Original Windows line endings, sizes and SHA values were matched to the inventory; no HANDOFF was restored as a live entry point. Original Git LF blobs alone do not satisfy those original worktree fingerprints.

## Read-only verification

From the repository root:

    python -I -B scripts/tc2_gpu/workflow/verify_archive.py

The verifier checks package hashes, exact member membership, sizes and member SHA256 without physical extraction or execution. Stored negative-test archives and simulated SUCCESS/status files are verified as recorded bytes, not promoted to real experiments.

Use the indexed original path or alias to find its archive, member and SHA. The index's roles mapping locates original workflow/configuration files. Old paths inside logs and JSON retain their spelling; they are historical locators, not current physical directories.

Current-source checks use configs/tc2_gpu/source_manifest.json independently. Old jobs do not authorize current formal execution; old receipts are never edited to contain current hashes.

## External artifacts and cleanup chain

Formal prediction, resource and figure returns remain in their original external output collections, unchanged. These source/acceptance packages do not replace external scientific returns or the reclaimed cluster's feature arrays. The former run/results contains pre-correction results only.

The external_records section preserves:

| Role | External record ID | Archive |
| --- | --- | --- |
| Removed temporary workspaces | tc2_gpu_cleanup_20261025_154510_33c37e36 | test_artifacts.zip |
| Old FP16 cache | tc2_gpu_naming_20261025_162634_415ea912 | legacy_fp16_cache.zip |

The previously removed 1,383 temporary files are not reintroduced. Their cleanup records are in the records packages. The old FP16 NPZ stays in its verified external ZIP, indexed by original path/SHA; it is neither committed as a large cache nor converted to a formal FP32 cache.

The naming-refactor record is output/tc2_gpu_naming_20261025_162634_415ea912/ in the external course directory. External artifacts are verified during migration and remain separate from the 20 project-contained packages; use their indexed identities to check available external copies.

## Inspection and recovery

Read members through the provenance adapter for inspection. For manual recovery, extract only the selected subset to a shallow staging directory and compare sizes/SHA with the index. Expanding every historical member into a deep project path would recreate the original long-path problem.

The current worktree retains a below-240-character path budget under its present root. ZIP member strings preserve old names without creating those deep physical directories.

Fingerprints use exact local bytes, including line endings. The repository restructuring does not modify .gitattributes, rewrite historical acceptance hashes or automatically bless changed checkouts. [TC2_GPU_NAMING.md](TC2_GPU_NAMING.md) explains current and historical identities.

The [implementation history](../experiment_history/IMPLEMENTATION_HISTORY.md) and [experiment ledger](../experiment_history/EXPERIMENT_LEDGER.md) are readable indexes into these preserved originals. They do not replace the immutable ZIP members or validate legacy maintenance actions against a future deployment.
