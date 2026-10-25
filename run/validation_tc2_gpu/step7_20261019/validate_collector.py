"""Offline synthetic byte fixtures; no model, data extraction, SSH or SLURM."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import uuid

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as c

BASE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_135738_92cb31b0\remote")
base_status = c._json(c._extended(BASE / "run/validation_tc2_gpu/step6_job_44024/setup_status.json").read_bytes())
base_meta = c._json(c._extended(BASE / base_status["cache"]["path"] / "metadata.json").read_bytes())
base_runtime = base_status["runtime"]
design_bytes = (ROOT / c.CONFIG).read_bytes()
design = c._json(design_bytes)
work = c._extended(AUDIT / ("collector_fixture_" + uuid.uuid4().hex[:10]))
work.mkdir(parents=True)


def put(root, name, value):
    path = c._inside(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else c._encode(value))
    return path


def raises(fn):
    try:
        fn()
    except (ValueError, FileNotFoundError, FileExistsError, OSError, KeyError):
        return
    raise AssertionError("Expected rejection")


def fixture(name, stage_id, passed=True):
    root = work / name; root.mkdir(); (root / "tmp").mkdir()
    put(root, c.CONFIG, design_bytes)
    for filename in c.MANIFESTS:
        put(root, filename, (ROOT / filename).read_bytes())
    job = "79001"
    runtime = copy.deepcopy(base_runtime); runtime["slurm_job_id"] = job
    stage = next(row for row in design["stages"] if row["stage_id"] == stage_id)
    state = {"mode": "formal_experiment_stage", "stage_id": stage_id, "job_id": job,
             "status": "passed" if passed else "running", "stage_complete": passed,
             "step_7_complete": False, "design_sha256": c._bytes_sha(design_bytes),
             "experiment_sources": {name: c._bytes_sha(name.encode()) for name in c.EXPERIMENT_SOURCES},
             "runtime": runtime, "caches": [], "results": [], "analyses": [], "phases": []}
    lookup = {row["run_key"]: row["configuration"] for row in design["fits"]}
    caches = {}
    for key in stage["run_keys"]:
        cfg = lookup[key]; category = (cfg["dataset"], cfg["category"])
        if category not in caches:
            dataset, category_name = category
            frozen_path = "manifests/manifest_" + dataset + "_" + category_name + ".json"
            frozen = c._json((ROOT / frozen_path).read_bytes())
            images = [{"path": row["path"], "sha256": row["sha256"]} for row in frozen["dev"] + frozen["fit_pool"] + frozen["test"]["good"] + frozen["test"]["anomalies"]]
            identity = copy.deepcopy(base_meta["identity"])
            identity.update(dataset=dataset, category=category_name, images=images,
                            manifest_sha256=design["scientific_source_hashes"][frozen_path], split_hash=frozen["split_hash"])
            identifier = c._digest(identity); directory = "run/tc2_gpu/feature_cache/" + dataset + "/" + category_name + "/" + identifier
            count = len(images)
            meta = {"identity": identity, "cache_id": identifier,
                    "index": [{**row, "orig_hw": [1, 1]} for row in images],
                    "layers": {layer: {"dtype": "float32", "shape": shape, "sha256": "A" * 64}
                               for layer, shape in {"layer1": [count, 64, 64, 64], "layer2": [count, 128, 32, 32], "layer3": [count, 256, 16, 16]}.items()}}
            meta_file = put(root, directory + "/metadata.json", meta)
            put(root, directory + "/COMPLETE", {"status": "complete", "cache_id": identifier, "metadata_sha256": c._sha(meta_file)})
            fingerprint = {"cache_id": identifier, "metadata_sha256": c._sha(meta_file), "layer_hashes": {name: row["sha256"] for name, row in meta["layers"].items()}}
            state["caches"].append({"path": directory, "identity": identity, **{name: fingerprint[name] for name in ("metadata_sha256", "layer_hashes")}})
            caches[category] = (identity, fingerprint, frozen)
        cache_identity, fingerprint, frozen = caches[category]
        groups = c._expected_samples(frozen, cfg)
        for group in groups.values():
            for row in group:
                row["orig_hw"] = [1, 1]
        identity = {"namespace": "formal", "protocol_sha256": c.PROTOCOL_SHA256, "configuration": cfg,
                    "manifest_sha256": cache_identity["manifest_sha256"], "split_hash": frozen["split_hash"],
                    "raw_inputs_sha256": c._digest({"images": cache_identity["images"], "masks": [mask for row in frozen["test"]["anomalies"] for mask in row["masks"]]}),
                    "samples_sha256": c._digest(groups), "cache": fingerprint,
                    "sources": {name: design["scientific_source_hashes"][name] for name in c.SCIENCE_SOURCES},
                    "software": runtime["software"], "hardware": design["expected_hardware"]}
        identifier = c._digest(identity); directory = "run/tc2_gpu/results/" + identifier
        artifacts = {"config.yaml": cfg, "samples.json": groups, "predictions.npz": b"SYNTHETIC BYTES ONLY; NOT A MODEL RESULT\n",
                     "metrics.json": {"image": {name: {} for name in c.RULES}, "pixel": {"pixel_auroc": 0.5, "pixel_ap": 0.5, "n_pixels": len(groups["test"]), "n_positive_pixels": len(frozen["test"]["anomalies"])}, "metric_policy": c.METRIC_POLICY},
                     "evidence.json": {"identity": identity, "cache_identity": cache_identity, "runtime": runtime},
                     "validation.json": {"status": "passed", "identity_sha256": identifier, "metric_abs_tolerance": 1e-12, "prediction_dtype": "float32", "saved_metric_reproduction": True}}
        for filename, value in artifacts.items():
            put(root, directory + "/" + filename, value)
        manifest = "".join(c._sha(root / directory / filename) + "  " + filename + "\n" for filename in c.ARTIFACTS).encode()
        put(root, directory + "/artifacts.sha256", manifest)
        put(root, directory + "/SUCCESS", {"status": "passed", "namespace": "formal", "identity_sha256": identifier, "artifacts_sha256": c._bytes_sha(manifest)})
        state["results"].append({"run_key": key, "path": directory, "identity_sha256": identifier,
                                 **{name: cfg[name] for name in ("method", "dataset", "category", "run_seed", "normal_train_n")},
                                 "verified": True, "run_status": "completed"})
    put(root, "run/validation_tc2_gpu/step7_job_" + job + "/setup_status.json", state)
    return root, state


checks = []
def check(name, fn):
    fn(); checks.append(name)


root, state = fixture("complete", "R0")
export = c.export_pages(root, state["job_id"], root / "tmp/experiments-79001-complete")
index_path = Path(export["index_path"])
check("six category pages with four complete results each", lambda: (_ for _ in ()).throw(AssertionError()) if len(export["pages"]) != 6 or any(len(row["result_ids"]) != 4 for row in export["pages"]) else None)
check("index checksum verification", lambda: c.verify_index(index_path, export["index_sha256"], "79001"))
local = work / "verified"; local.mkdir()
for row in export["pages"]:
    c.verify_archive(Path(export["directory"]) / row["name"], row["sha256"], "79001", local / ("page_%03d" % row["page_number"]), index_path)
check("all pages verified before stage completion", lambda: (_ for _ in ()).throw(AssertionError()) if not c.verify_collection(index_path, local, "79001")["stage_complete"] else None)
check("missing page receipt rejected", lambda: raises(lambda: c.verify_collection(index_path, work, "79001")))
first = local / "page_001"
target = first / state["results"][0]["path"] / "metrics.json"
original = target.read_bytes(); target.write_bytes(original + b" ")
check("modified extracted result rejected", lambda: raises(lambda: c.verify_collection(index_path, local, "79001")))
target.write_bytes(original)
check("wrong index checksum rejected", lambda: raises(lambda: c.verify_index(index_path, "0" * 64, "79001")))
check("foreign index job rejected", lambda: raises(lambda: c.verify_index(index_path, export["index_sha256"], "79002")))
index = c._json(index_path.read_bytes())
bad = copy.deepcopy(index); bad["pages"][0]["name"] = "../page_001.tar.gz"
check("index path traversal rejected", lambda: raises(lambda: c._validate_index(bad, "79001")))
bad = copy.deepcopy(index); bad["pages"][0]["bytes"] = c.LIMIT + 1
check("compressed page bound rejected", lambda: raises(lambda: c._validate_index(bad, "79001")))
bad = copy.deepcopy(index); bad["pages"][0]["result_ids"] *= 2
check("more than four results rejected", lambda: raises(lambda: c._validate_index(bad, "79001")))
bad = copy.deepcopy(index); bad["pages"][1]["result_ids"] = bad["pages"][0]["result_ids"]
check("repeated global result rejected", lambda: raises(lambda: c._validate_index(bad, "79001")))
check("fresh extraction required", lambda: raises(lambda: c.verify_archive(Path(export["directory"]) / export["pages"][0]["name"], export["pages"][0]["sha256"], "79001", first, index_path)))
queued = work / "queued"; queued.mkdir(); (queued / "tmp").mkdir(); put(queued, c.CONFIG, design_bytes)
q = c.export_pages(queued, "79003", queued / "tmp/experiments-79003-queued", "B0")
q_local = work / "queued_local"; q_local.mkdir()
c.verify_archive(Path(q["directory"]) / q["pages"][0]["name"], q["pages"][0]["sha256"], "79003", q_local / "page_001", q["index_path"])
check("queued collection remains partial", lambda: (_ for _ in ()).throw(AssertionError()) if c.verify_collection(q["index_path"], q_local, "79003")["stage_complete"] else None)
check("raw images outside whitelist", lambda: raises(lambda: c._role("datasets/mvtec_ad/bottle/train/good/000.png", "79001")))
check("feature arrays outside whitelist", lambda: raises(lambda: c._role("run/tc2_gpu/feature_cache/mvtec_ad/bottle/" + "A" * 64 + "/layer1.npy", "79001")))
check("partial directories outside whitelist", lambda: raises(lambda: c._role("run/tc2_gpu/results/." + "A" * 64 + ".partial/config.yaml", "79001")))
bad_state = copy.deepcopy(state); bad_state["step_7_complete"] = True
check("nonfinal stage cannot complete step seven", lambda: raises(lambda: c._status(bad_state, "79001", design)))
bad_state = copy.deepcopy(state); bad_state["results"].pop()
check("passed stage cannot omit a configured fit", lambda: raises(lambda: c._status(bad_state, "79001", design)))
bad_state = copy.deepcopy(state); bad_state["results"][0]["verified"] = False
check("passed stage cannot contain an unverified fit", lambda: raises(lambda: c._status(bad_state, "79001", design)))
check("export destination stays in approved tmp subtree", lambda: raises(lambda: c.export_pages(root, "79001", work / "outside")))
check("strict duplicate JSON keys", lambda: raises(lambda: c._json(b'{"a":1,"a":2}')))
report = {"status": "passed", "checks": checks, "check_count": len(checks), "fixture_directory": c._plain(work),
          "collector_sha256": c._sha(ROOT / "scripts/collect_experiments_tc2_gpu.py"),
          "runtime": "Offline synthetic bytes only; no NumPy, torch, models, SSH or SLURM", "pages": len(export["pages"]), "results": len(state["results"])}
(AUDIT / "collector_validation.json").write_bytes(c._encode(report))
print(json.dumps(report, indent=2))
