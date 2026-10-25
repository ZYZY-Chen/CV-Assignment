# TC2 GPU Experiment Protocol: step-8 figure revision

> **Current profile and historical-record boundary (2026-10-25)**
>
> The retained design and acceptance account below describes the earlier implementation. Its job IDs, source hashes, remote paths, command blocks and completion flags are historical. Exact original bytes are in the [archive index](../../../archive/index.json); they do not certify this refactored checkout.
>
> Current configurations are under configs/tc2_gpu/, and independent fingerprints are in configs/tc2_gpu/source_manifest.json. The current deployment is unavailable. Formal actions refuse execution without new source/environment acceptance. Historical SSH and submission examples below are not current connection instructions.
>
> Use the [current workflow guide](../../guides/TC2_GPU_WORKFLOW.md), [protocol](../../guides/TC2_GPU_PROTOCOL.md), [naming rules](../../guides/TC2_GPU_NAMING.md) and [archive guide](../../guides/TC2_GPU_ARCHIVE.md) for current paths. The [experiment ledger](../EXPERIMENT_LEDGER.md) records final historical completion; pending flags below retain their snapshot meaning.

## Historical design and acceptance account


This approved supplement changes figure layout and export only. Analysis job 44284 completed successfully and its tables, selected cases and descriptive distribution points passed independent verification. Its fifteen original figure groups need layout corrections before step 8 can be accepted. Original results, logs, sources and figures remain immutable.

The input analysis identity is `6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C`. Its `artifacts.sha256` fingerprint is `1B5326EE8EB707E75BCD3F043B3479DCD8C6472ECB78FA770F0B2C618D5C33DA`. The [revision configuration](../../../archive/index.json) (archived path: `configs/figure_revision_tc2_gpu.json`) pins the accepted input and the rendering policy. No fit, model prediction, new statistical calculation, dataset scan or feature-cache access is part of this supplement.

## Rendering and preservation

The [revision driver](../../../archive/index.json) (archived path: `scripts/revise_figures_tc2_gpu.py`) imports the frozen original plotting module and temporarily overrides only its shared `_save` routine and `_methods` diagram routine. Original numerical plotting functions remain unchanged. The shared layout reserves measured bands for axes, legends and notes. The methods diagram fits text within measured boxes and connects both methods to their anomaly-map and image-score outputs. Logarithmic ticks use plain numeric text where necessary to keep actual PDF glyphs at least 7 pt.

The driver reads accepted `tables.json`, `cases.json` and the existing descriptive CDF source data. It copies only the already selected case assets, byte for byte. Every revised source-data row must equal the corresponding original row, including order and full numerical precision. The tables and case registry retain their original bytes. All seven original analysis sources and 44 scientific, pilot and experiment sources must match their frozen SHA256 values before and after rendering.

New outputs use `run/tc2_gpu/summaries/figure_revision/<identity>/`; the identity binds the six revision sources, configuration and accepted input. Job records use `run/validation_tc2_gpu/step8_figure_revision_job_<job>/`. An existing output namespace is never overwritten. The original `analysis/<identity>/` directory is read only. The original plot module's two function bindings are restored after rendering, including on failure.

The six published revision files are the configuration, driver, dedicated collector, SLURM wrapper, tests and this document. The external helper and README are the only existing files modified by this supplement. Frozen `v2` identifiers and historical archive names retain their original spelling.

## Local packaging and user terminal operation

Run these commands in a local PowerShell terminal. The helper prompts through OpenSSH for credentials and saves a fresh `terminal.txt`; it does not store passwords. The assistant does not run remote commands or submit jobs.

```powershell
& 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1' -Action RunFigureRevision -ValidateOnly
```

This validates the accepted local input, portable plan and source bundle without a TC2 connection or job submission. By default it reads the accepted job-44284 collection in `output/tc2_gpu_setup_20261019_220347_4dc4d911/remote/page_001/`. If that collection was relocated, supply `-InputDirectory` with the complete accepted analysis directory. That physical location is excluded from the portable plan identity.

After local checks pass, submit the single approved CPU job:

```powershell
& 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1' -Action RunFigureRevision
```

The helper packages and publishes only the six pinned new files, refusing conflicting remote bytes. It validates the accepted input and 51 frozen sources before submission. The [wrapper](../../../archive/index.json) (archived path: `scripts/slurm/figure_revision_tc2_gpu.sh`) runs the full synthetic tests and actual fifteen-figure render in the existing locked TC2 environment. Resources are MGPU-TC2/normal, one node, one task, two CPUs, 8 GiB, fifteen minutes and zero GPUs, with no node pin. No software installation or environment export change is performed.

Submission records an exclusive claim before calling the scheduler. A second `RunFigureRevision` refuses to submit another job, including after an ambiguous connection or a failed submission. A pending claim requires investigation of the existing submission record; it is never cleared automatically. A failed job is evidence for review, not permission for an automatic retry or larger resource request.

Collect the same job again if the first snapshot is queued, running or incomplete:

```powershell
& 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1' -Action CollectFigureRevision -JobId <job-id>
```

Replace `<job-id>` with the numeric ID printed by the submission. Collection never fits a model, redraws figures or submits a job. Return the fresh local `terminal.txt` for verification.

## Collection and acceptance

The [dedicated collector](../../../archive/index.json) (archived path: `scripts/collect_figure_revision_tc2_gpu.py`) exports one snapshot with a fingerprint-pinned index and one archive. Limits are 512 MiB compressed, 512 MiB decompressed and 512 members. Verification rejects linked or reparse paths, hard links, traversal, duplicate or case-aliased members, unexpected files, changed sources and mixed snapshots. It verifies the complete archive before extracting into a new destination. Queued, running and failed snapshots remain explicitly incomplete.

Acceptance requires all of the following:

- A completed CPU job and all full tests, including actual fifteen-figure synthetic rendering.
- Exact source-data equality for all fifteen figures, unchanged selected-case assets, tables and cases, and preserved source fingerprints.
- Final rendered axes alignment; measured legend, label and tick clearance; diagram text containment; and an actual PDF font scan with a 7 pt minimum.
- Reopening and visually reviewing every revised PNG and PDF, including all four case plates. PNG exports are 300 dpi and PDFs retain editable text.
- A complete, verified collection with matching artifact and index hashes.

Automated rendering success leaves `step_8_complete=false` and requests post-download visual review. The frozen analysis tables do not need to be recomputed. Report writing and step 9 remain separate, unstarted work.

## Tests

```powershell
python -I -B tests/test_figure_revision_tc2_gpu.py --output-dir <fresh-local-directory>
```

Local mode runs font-scanner, immutable-input, data-invariance, measured-geometry and archive-safety checks, and explicitly records that actual fifteen-figure rendering was not executed. The cluster wrapper uses `--full`, which requires Matplotlib and permits no missing-render skip. Local checks alone do not establish figure acceptance.
