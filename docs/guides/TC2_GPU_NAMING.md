# TC2 GPU naming and source identity

The canonical name is tc2_gpu; the display name is **TC2 GPU Experiment Protocol**. TC2 records the cluster used for historical formal experiments. GPU expresses the formal-fitting requirement; offline checks may use CPU.

## Current paths

Current configuration roles are configs/tc2_gpu/{protocol,workflow,setup,runtime,pilot,experiments,analysis,figure_revision}.json. The separate configs/tc2_gpu/source_manifest.json records the independent current-source baseline. Current protocol metadata uses ca6129_industrial_ad_tc2_gpu.

Current formal outputs retain run/tc2_gpu/{results,logs,summaries,resources,feature_cache}/. New administrative records use run/setup_tc2_gpu/ and run/validation_tc2_gpu/. Current lifecycle scripts are grouped under scripts/tc2_gpu/{setup,workflow,pilot,experiments,analysis,collect,slurm,client}; tools/data/make_manifests.py is the separate data-manifest utility. See the [workflow guide](TC2_GPU_WORKFLOW.md) for responsibilities and execution prerequisites.

Environment files are environment-tc2_gpu.yml, requirements-tc2_gpu-bootstrap.txt and requirements-tc2_gpu-lock.txt. Their roles are portable template, installation constraints and byte-preserved historical distribution lock. No new installation or GPU acceptance is implied.

## Historical identity and current identity

The [current protocol](TC2_GPU_PROTOCOL.md) preserves scientific parameters and all 66 fit configurations/run keys. Its renamed metadata has a new file identity. Complete cache/result identities also bind protocol/source bytes; old results are not automatically reusable current-profile results.

Original protocol filenames, identifiers, source files, hashes, jobs and result identities remain unchanged inside the [archive](TC2_GPU_ARCHIVE.md). The original frozen protocol SHA256 is:

    3098B6A86DBA64EE439BFE61C7A4FCFFCD082371D5A80FFBC7940997ED6A1ED1

The former legacy_v1 label means **pre-correction historical results**, the old 66-run set separate from corrected TC2 GPU results. Its original inventory is archived unchanged.

Current readiness does not fall back to old physical setup_v2 or validation_v2 paths. The provenance adapter explicitly resolves historical paths through archive/index.json, checking ZIP and member fingerprints. Current formal acceptance requires a matching current-profile full receipt and configured deployment.

The reclaimed deployment remains unavailable. Personal connection/root/environment paths are unset, with no inherited authentication or installation proof. Jobs 43950, 44012 and 44024 remain historical evidence only.

## Legitimate version identifiers

- ResNet18_Weights.IMAGENET1K_V1 is the Torchvision weight identity.
- Anomalib v2.0.0 and fixed reference URLs identify the algorithmic reference.
- Dataset versions and JSON schema/protocol format versions retain their meanings.
- Archived labels, environment prefixes, metric tags and filenames retain their original spelling.
- Old names in archive aliases or explicitly historical design accounts identify provenance, not current operational paths.

## Exact-byte fingerprint policy

Fingerprints describe exact local working-tree bytes, including line endings. The archive captured those bytes; original Git blobs may have different line endings.

A checkout that changes bytes must fail the corresponding source check. The repository restructuring does not modify .gitattributes, normalize old receipts or automatically refresh expected hashes to silence a mismatch. Compare with the recorded snapshot; intentional source changes require a separately approved current baseline.

All new text is English. Existing Chinese historical text is preserved. Raw logs and acceptance JSON are not rewritten.

The repository client scripts/tc2_gpu/client/tc2_gpu.ps1 and its external compatibility wrapper check current deployment/source acceptance before creating output or accessing the network. ValidateOnly performs read-only plan/source verification and returns before historical operator actions. CodeRoot is derived from the repository client location by default; PythonExecutable defaults to python from PATH. OutputRoot defaults to run/setup_tc2_gpu/client under the repository, while the external wrapper passes its own output directory. Legacy maintenance implementations remain gated; a future deployment requires a new design and current-source/environment acceptance, with no new remote validation implied. Read [TC2_GPU_ARCHIVE.md](TC2_GPU_ARCHIVE.md) for archive verification and recovery.
