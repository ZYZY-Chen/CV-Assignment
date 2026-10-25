"""Adversarial tar, analysis-page and final dependency evidence checks."""
from pathlib import Path
import copy
import io
import json
import shutil
import sys
import tarfile
import uuid

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as c
previous = c._json((AUDIT / "collector_validation.json").read_bytes())
fixture = c._extended(previous["fixture_directory"])
original = fixture / "complete/tmp/experiments-79001-complete/index.json"
index = c._json(original.read_bytes())
work = c._extended(AUDIT / ("collector_extra_" + uuid.uuid4().hex[:8])); work.mkdir()
checks = []


def raises(fn):
    try:
        fn()
    except (ValueError, FileNotFoundError, FileExistsError, OSError, KeyError):
        return
    raise AssertionError("Expected rejection")


def check(name, fn):
    fn(); checks.append(name)


def put(root, name, data):
    target = c._inside(root, name); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data if isinstance(data, bytes) else c._encode(data))
    return target


def unsafe(name, members, format=tarfile.USTAR_FORMAT):
    path = work / (name + ".tar.gz")
    with tarfile.open(path, "w:gz", format=format) as package:
        for member, content in members:
            item = tarfile.TarInfo(member); item.size = len(content)
            package.addfile(item, io.BytesIO(content))
    changed = copy.deepcopy(index)
    changed["pages"][0].update(sha256=c._sha(path), bytes=path.stat().st_size)
    idx = put(work, name + "-index.json", changed)
    return lambda: c.verify_archive(path, c._sha(path), "79001", work / (name + "-out"), idx)


check("traversal tar member rejected", lambda: raises(unsafe("traversal", [("../escape", b"x")])))
check("absolute tar member rejected", lambda: raises(unsafe("absolute", [("/escape", b"x")])))
check("duplicate tar member rejected", lambda: raises(unsafe("duplicate", [(c.MANIFEST, b"{}"), (c.MANIFEST, b"{}")])) )
check("case aliased tar member rejected", lambda: raises(unsafe("alias", [(c.CONFIG, b"{}"), (c.CONFIG.upper(), b"{}")])) )
check("PAX extension rejected before tar interpretation", lambda: raises(unsafe("pax", [("x" * 160, b"x")], tarfile.PAX_FORMAT)))
symlink = work / "symlink.tar.gz"
with tarfile.open(symlink, "w:gz", format=tarfile.USTAR_FORMAT) as package:
    member = tarfile.TarInfo(c.CONFIG); member.type = tarfile.SYMTYPE; member.linkname = "../escape"; package.addfile(member)
changed = copy.deepcopy(index); changed["pages"][0].update(sha256=c._sha(symlink), bytes=symlink.stat().st_size)
idx = put(work, "symlink-index.json", changed)
check("symlink tar member rejected", lambda: raises(lambda: c.verify_archive(symlink, c._sha(symlink), "79001", work / "symlink-out", idx)))

design = c._json((ROOT / c.CONFIG).read_bytes())
root = work / "analysis"; root.mkdir(); (root / "tmp").mkdir()
put(root, c.CONFIG, (ROOT / c.CONFIG).read_bytes())
for name in c.MANIFESTS:
    put(root, name, (ROOT / name).read_bytes())
source = c._extended(AUDIT / "score_858481/run/tc2_gpu/summaries/I1_seed17/E1576CC10C9BECFCBE355F08C6466D2BB37F20E59EC8364BC464D876217C2763")
analysis = c._json((source / "analysis.json").read_bytes())
evidence = c._json((source / "evidence.json").read_bytes())
relative = "run/tc2_gpu/summaries/I1_seed17/" + analysis["identity_sha256"]
for name in c.ANALYSIS_FILES:
    put(root, relative + "/" + name, (source / name).read_bytes())
status = {"mode": "formal_experiment_stage", "stage_id": "I1_seed17", "job_id": "79010", "status": "passed",
          "stage_complete": True, "step_7_complete": False, "design_sha256": c._sha(ROOT / c.CONFIG),
          "experiment_sources": {name: c._bytes_sha(name.encode()) for name in c.EXPERIMENT_SOURCES},
          "runtime": {"device": "cpu"}, "caches": [], "results": [], "phases": [],
          "analyses": [{"stage_id": "I1_seed17", "path": relative, "identity_sha256": analysis["identity_sha256"], "rows": 18, "status": "passed"}]}
status["experiment_sources"]["scripts/analyze_scores_tc2_gpu.py"] = evidence["identity"]["analysis_sources"]["scripts/analyze_scores_tc2_gpu.py"]
put(root, "run/validation_tc2_gpu/step7_job_79010/setup_status.json", status)
export = c.export_pages(root, "79010", root / "tmp/experiments-79010-analysis")
local = work / "analysis_local"; local.mkdir()
c.verify_archive(Path(export["directory"]) / export["pages"][0]["name"], export["pages"][0]["sha256"], "79010", local / "page_001", export["index_path"])
check("five-file analysis roundtrip validates CSV and row/source identities", lambda: (_ for _ in ()).throw(AssertionError()) if not c.verify_collection(export["index_path"], local, "79010")["stage_complete"] else None)

chain = []
lookup = {row["run_key"]: row["configuration"] for row in design["fits"]}
for number, stage in enumerate(design["stages"], 1):
    rows = []
    for key in stage["run_keys"]:
        cfg = lookup[key]; identity = c._digest(key)
        rows.append({"run_key": key, "path": "run/tc2_gpu/results/" + identity, "identity_sha256": identity,
                     **{name: cfg[name] for name in ("method", "dataset", "category", "run_seed", "normal_train_n")}, "verified": True, "run_status": "completed"})
    analyses = [{"stage_id": stage["stage_id"], "status": "passed", "rows": stage["expected_rows"], "identity_sha256": c._digest(stage["stage_id"]),
                 "path": "run/tc2_gpu/summaries/" + stage["stage_id"] + "/" + c._digest(stage["stage_id"])}] if stage["kind"] == "analysis" else []
    entry = {"stage_id": stage["stage_id"], "job_id": str(79100 + number), "status": "passed", "stage_complete": True,
             "design_sha256": c._sha(ROOT / c.CONFIG), "results": rows, "analyses": analyses}
    if number != 12:
        entry["status_sha256"] = "F" * 64
    chain.append(entry)
final = {**chain[-1], "mode": "formal_experiment_stage", "step_7_complete": True, "caches": [],
         "completed_stages": chain, "checkpoints": [{**row, "complete": True} for row in design["checkpoints"]]}
check("final completion requires exact ordered twelve-stage 66-fit evidence", lambda: c._status(final, final["job_id"], design))
bad = copy.deepcopy(final); bad["completed_stages"].pop(3)
check("final incomplete predecessor chain rejected", lambda: raises(lambda: c._status(bad, bad["job_id"], design)))
bad = copy.deepcopy(final); bad["completed_stages"][0]["results"][0]["verified"] = False
check("final unverified predecessor result rejected", lambda: raises(lambda: c._status(bad, bad["job_id"], design)))
bad = copy.deepcopy(final); bad["checkpoints"][1]["complete"] = False
check("final incomplete checkpoint rejected", lambda: raises(lambda: c._status(bad, bad["job_id"], design)))
report = {"status": "passed", "check_count": len(checks), "checks": checks, "collector_sha256": c._sha(ROOT / "scripts/collect_experiments_tc2_gpu.py"),
          "fixture": c._plain(work), "scope": "Offline adversarial transport and mocked analysis-source metadata; no model, SSH or SLURM"}
(AUDIT / "collector_additional_validation.json").write_bytes(c._encode(report))
print(json.dumps(report, indent=2))
