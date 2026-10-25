"""Core and TC2 GPU workflow acceptance; fixtures cannot qualify as formal results."""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import tc2_gpu_protocol as p
import tc2_gpu_cache as c
import tc2_gpu_runner as r

OUTPUT = None
CASE = 0
NEW_FILES = ["src/tc2_gpu_protocol.py", "src/tc2_gpu_cache.py", "src/tc2_gpu_runner.py",
             "scripts/run_tc2_gpu.py", "configs/runtime_tc2_gpu.json", "tests/test_workflow_tc2_gpu.py",
             "scripts/slurm/check_tc2_gpu_workflow.sh", "docs/TC2_GPU_WORKFLOW.md"]
OLD_FILES = ["src/padim_adapter.py", "src/patchcore_adapter.py", "src/sampling.py", "src/scoring.py",
             "src/anomaly_postprocess.py", "tests/test_algorithms_tc2_gpu.py", "scripts/slurm/check_tc2_gpu_algorithms.sh",
             "src/metric_core.py", "src/evaluate.py", "src/data.py", "configs/tc2_gpu.json",
             "tests/test_metrics_tc2_gpu.py", "scripts/slurm/check_tc2_gpu_metrics.sh"]


def payload_files():
    protocol = p.contract(ROOT)[0]
    return NEW_FILES + OLD_FILES + ["configs/protocol_v2.json", "environment-tc2.yml",
                                  "requirements-tc2-lock.txt"] + [item["path"] for item in protocol["data"]["frozen_manifests"]]


def fixture(sandbox, train_n=2, dev_n=1):
    ctx = p.context(ROOT, sandbox)
    rows = {}
    for role, count in [("train", train_n), ("dev", dev_n), ("test_good", 1), ("test_bad", 1)]:
        rows[role] = []
        for i in range(count):
            path = f"mvtec_ad/bottle/{role}/{i}.png"
            destination = p.inside(ctx.datasets, path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            y, x = np.indices((10, 12))
            offset = 50 if role == "test_bad" else 0
            image = np.stack(((x * 17 + i * 13 + offset) % 256, (y * 21 + i * 19) % 256, (x * 7 + y * 5 + i * 31) % 256), axis=-1).astype(np.uint8)
            Image.fromarray(image).save(destination)
            rows[role].append({"path": path, "sha256": p.sha(destination)})
    mask = p.inside(ctx.datasets, "mvtec_ad/bottle/masks/0.png")
    mask.parent.mkdir(parents=True)
    values = np.zeros((10, 12), dtype=np.uint8); values[2:7, 3:9] = 255
    Image.fromarray(values).save(mask)
    value = {"dataset": "mvtec_ad", "category": "bottle", "split_hash": "SYNTHETIC_VALIDATION_ONLY",
             "dev": rows["dev"], "fit_pool": rows["train"],
             "test": {"good": [{**rows["test_good"][0], "label": 0}],
                      "anomalies": [{**rows["test_bad"][0], "label": 1, "defect_type": "bad",
                                     "masks": [{"path": "mvtec_ad/bottle/masks/0.png", "sha256": p.sha(mask)}]}]},
             "runs": {str(seed): {str(train_n): [row["path"] for row in (rows["train"] if seed == 17 else rows["train"][::-1])]} for seed in (17, 29, 43)}}
    return ctx, value


def config(method="padim", seed=17, n=2):
    cfg = copy.deepcopy(next(item["configuration"] for item in p.build_plan(ROOT)["fits"] if item["configuration"]["stage"] == "B0" and item["configuration"]["category"] == "bottle" and item["configuration"]["method"] == method))
    cfg.update(run_seed=seed, normal_train_n=n)
    cfg[method]["dims_seed" if method == "padim" else "sampling_seed"] = seed
    return cfg


def arrays_for(value):
    count = len(p.image_entries(value))
    return {layer: np.full((count, *shape), (i + 1) / 7, dtype=np.float32) for i, (layer, shape) in enumerate(p.SHAPES.items())}


def batches(value, arrays):
    for i, row in enumerate(p.image_entries(value)):
        yield [row["path"]], {layer: values[i:i + 1] for layer, values in arrays.items()}


def reseal(directory, metadata):
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (directory / "COMPLETE").write_text(json.dumps({"status": "complete", "cache_id": metadata["cache_id"],
        "metadata_sha256": p.sha(directory / "metadata.json")}), encoding="utf-8")


class CoreTests(unittest.TestCase):
    def setUp(self):
        global CASE
        CASE += 1
        self.ctx, self.value = fixture(OUTPUT / ("c" + str(CASE)))
        self.identity = c.cache_identity(self.ctx, self.value, p.digest(self.value))
        self.index = c.input_index(self.ctx, self.value)

    def make_cache(self):
        values = arrays_for(self.value)
        result = c.write_cache(self.ctx, self.identity, self.index, batches(self.value, values))
        return Path(result["path"]), values

    def test_matrix_counts_order_and_seed_binding(self):
        plan = p.build_plan(ROOT)
        self.assertEqual(plan["stage_counts"], {"B0":12,"H1":4,"H2":4,"C1":2,"R0":24,"C1R":4,"C2":4,"F1":8,"B0_LOCO":4})
        self.assertEqual(len(plan["fits"]), 66)
        self.assertEqual(sum(item["configuration"]["dataset"] == "mvtec_ad" for item in plan["fits"]), 62)
        self.assertEqual([stage["stage_id"] for stage in plan["offline_stages"]], ["I1", "I2"])
        self.assertEqual(plan["execution_order"][4], "I1_seed17")
        for item in plan["fits"]:
            cfg = item["configuration"]
            p.select_spec(ROOT, item["run_key"])
            method = cfg["method"]
            self.assertEqual(cfg[method]["dims_seed" if method == "padim" else "sampling_seed"], cfg["run_seed"])

    def test_plan_cli_is_readonly_and_requires_explicit_action(self):
        before = (ROOT / "run/tc2_gpu").exists()
        completed = subprocess.run([sys.executable,"-B",str(ROOT/"scripts/run_tc2_gpu.py"),"plan"],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(len(json.loads(completed.stdout)["fits"]),66)
        self.assertEqual((ROOT / "run/tc2_gpu").exists(),before)
        no_action = subprocess.run([sys.executable,"-B",str(ROOT/"scripts/run_tc2_gpu.py")],capture_output=True,text=True)
        self.assertNotEqual(no_action.returncode,0)

    def test_paths_namespace_and_unknown_matrix_key(self):
        for bad in ("../outside","/outside","a\\b","C:/outside","a/../b"):
            with self.subTest(path=bad), self.assertRaises(ValueError): p.inside(self.ctx.storage,bad)
        with self.assertRaises(ValueError): p.context(ROOT,ROOT/"run/results")
        with self.assertRaises(ValueError): p.select_spec(ROOT,"legacy_SUCCESS")
        with self.assertRaises(ValueError): c.cache_directory(p.context(ROOT),self.identity)

    def test_config_rejects_legacy_seed_and_invalid_formal_run(self):
        cfg=config("patchcore");cfg["patchcore"]["sampling_seed"]=0
        with self.assertRaises(ValueError):r.validate_config(self.ctx,cfg)
        with self.assertRaises(ValueError):r.validate_config(p.context(ROOT),config())

    def test_actual_setup_evidence_and_failed_primary_do_not_fall_back(self):
        base=self.ctx.storage/"acceptance"
        old=base/"run/setup_v2";job=old/"job_43950_all"
        job.mkdir(parents=True)
        (old/"last_check_all_job.txt").write_text("43950\n")
        p.write_json(job/"setup_status.json",{"step_2_complete":True,"weights_ready":True,
            "environment_export":{"files":[{"path":"/record/environment-tc2.yml","sha256":"A"*64}]}})
        p.write_json(job/"weights_info.json",{"sha256":"B"*64})
        result=p.accepted_inputs(base)
        self.assertEqual(result["weights_sha256"],"B"*64)
        self.assertEqual(result["export_hashes"],{"environment-tc2.yml":"A"*64})
        primary=base/"run/setup_tc2_gpu";primary.mkdir()
        (primary/"last_check_all_job.txt").write_text("43951\n")
        failed=primary/"job_43951_all";failed.mkdir()
        p.write_json(failed/"setup_status.json",{"step_2_complete":False,"weights_ready":False})
        with self.assertRaises(RuntimeError):p.accepted_inputs(base,allow_local_summary=True)

    def test_roundtrip_exact_order_and_input_preservation(self):
        path,values=self.make_cache()
        fingerprints={name:p.sha(path/(name+".npy")) for name in p.SHAPES}
        requested=[self.index[-1]["path"],self.index[0]["path"]]
        with c.CacheReader(self.ctx,path,self.identity) as reader:
            got=reader.get(requested,("layer3","layer1"))
            np.testing.assert_array_equal(got["layer1"],values["layer1"][[len(self.index)-1,0]])
            self.assertEqual(got["layer3"].dtype,np.float32)
            got["layer1"][0]=99
            with self.assertRaises(ValueError):reader.get([requested[0]]*2,("layer1",))
            with self.assertRaises(ValueError):reader.get(["missing.png"],("layer1",))
        self.assertEqual(fingerprints,{name:p.sha(path/(name+".npy")) for name in p.SHAPES})
        repeat=c.write_cache(self.ctx,self.identity,self.index,iter(()))
        self.assertEqual(repeat["status"],"cached")

    def test_bad_precision_fails_without_publishing(self):
        values=arrays_for(self.value);values["layer1"]=values["layer1"].astype(np.float16)
        with self.assertRaises(ValueError):c.write_cache(self.ctx,self.identity,self.index,batches(self.value,values))
        target=c.cache_directory(self.ctx,self.identity)
        self.assertFalse(target.exists())
        failed=list(target.parent.glob(".*.partial.*/FAILED.json"))
        self.assertEqual(len(failed),1)

    def test_missing_batches_and_order_fail(self):
        values=arrays_for(self.value)
        first=next(batches(self.value,values))
        with self.assertRaises(ValueError):c.write_cache(self.ctx,self.identity,self.index,iter([first]))
        wrong=([self.index[-1]["path"]],first[1])
        with self.assertRaises(ValueError):c.write_cache(self.ctx,self.identity,self.index,iter([wrong]))

    def test_nonfinite_feature_rejected(self):
        values=arrays_for(self.value);values["layer2"][0,0,0,0]=np.nan
        with self.assertRaises(ValueError):c.write_cache(self.ctx,self.identity,self.index,batches(self.value,values))

    def test_cache_corruption_and_incomplete_record(self):
        path,_=self.make_cache()
        file=path/"layer3.npy"
        with file.open("r+b") as stream:stream.seek(-4,2);stream.write(b"bad!")
        with self.assertRaises(ValueError):c.CacheReader(self.ctx,path,self.identity)
        (path/"COMPLETE").unlink()
        with self.assertRaises(ValueError):c.CacheReader(self.ctx,path,self.identity)

    def test_fp16_data_rejected_even_with_resealed_metadata(self):
        path,values=self.make_cache()
        np.save(path/"layer3.npy",values["layer3"].astype(np.float16),allow_pickle=False)
        meta=p.read_json(path/"metadata.json");meta["layers"]["layer3"]["sha256"]=p.sha(path/"layer3.npy")
        reseal(path,meta)
        with self.assertRaises(ValueError):c.CacheReader(self.ctx,path,self.identity)

    def test_reordered_index_and_changed_identity_rejected(self):
        path,_=self.make_cache()
        meta=p.read_json(path/"metadata.json");meta["index"].reverse();reseal(path,meta)
        with self.assertRaises(ValueError):c.CacheReader(self.ctx,path,self.identity)
        other=copy.deepcopy(self.identity);other["weights_sha256"]="0"*64
        with self.assertRaises(ValueError):c.CacheReader(self.ctx,path,other)

    def test_raw_input_tampering_and_split_integrity(self):
        c.input_index(self.ctx,self.value,include_masks=True)
        path=p.inside(self.ctx.datasets,self.value["fit_pool"][0]["path"]);path.write_bytes(b"changed")
        with self.assertRaises(ValueError):c.input_index(self.ctx,self.value)
        value=copy.deepcopy(self.value);value["dev"][0]=value["fit_pool"][0]
        with self.assertRaises(ValueError):p.image_entries(value)

    def test_exclusive_lock_preserves_existing_owner(self):
        parent=self.ctx.storage/"locks"
        with p.exclusive(parent,"example"):
            lock=parent/".example.lock";before=lock.read_bytes()
            with self.assertRaises(RuntimeError):
                with p.exclusive(parent,"example"):pass
            self.assertEqual(lock.read_bytes(),before)
        self.assertFalse(lock.exists())
        with self.assertRaisesRegex(RuntimeError,"injected"):
            with p.exclusive(parent,"example"):raise RuntimeError("injected")
        self.assertFalse(lock.exists())

    def test_saved_predictions_precision_order_and_native(self):
        groups=p.samples(self.value,17,2);arrays={}
        for role in ("dev","test"):
            items=groups[role];maps=np.full((len(items),256,256),2,dtype=np.float32)
            arrays.update({role+"_maps":maps,role+"_paths":np.asarray([i["path"] for i in items]),
                role+"_labels":np.asarray([i["label"] for i in items],dtype=np.uint8),
                role+"_defect_types":np.asarray([i["defect_type"] for i in items],dtype=str)})
            arrays.update({role+"_score_"+rule:np.full(len(items),0.3 if rule=="native" else 2,dtype=np.float32) for rule in p.RULES})
        r.validate_predictions(groups,arrays,"patchcore")
        with self.assertRaises(ValueError):r.validate_predictions(groups,arrays,"padim")
        for key,value in [("test_maps",arrays["test_maps"].astype(np.float16)),("test_paths",arrays["test_paths"][::-1]),
                          ("dev_score_max",np.full(1,np.inf,dtype=np.float32)),("test_labels",arrays["test_labels"].astype(object))]:
            bad=dict(arrays);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_predictions(groups,bad,"patchcore")

    def test_metric_reproduction_tolerance_and_counts(self):
        r.compare_metrics({"x":0.5,"n":3},{"x":0.5+1e-13,"n":3})
        for bad in ({"x":0.5+1e-6,"n":3},{"x":0.5,"n":4},{"x":float("nan"),"n":3},{"n":3}):
            with self.assertRaises(ValueError):r.compare_metrics({"x":0.5,"n":3},bad)


class GPUTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx,cls.value=fixture(OUTPUT/"g",train_n=4,dev_n=2)
        cls.manifest_hash=p.digest(cls.value)
        cls.extracted=c.extract(cls.ctx,"mvtec_ad","bottle",value=cls.value,manifest_sha256=cls.manifest_hash)

    def execute(self,method="padim",seed=17):
        return r.execute(self.ctx,config(method,seed,4),value=self.value,manifest_sha256=self.manifest_hash)

    def test_01_actual_backbone_and_preprocessing(self):
        import torch
        from torchvision.models import resnet18
        from data import load_image
        self.assertEqual(self.extracted["status"],"extracted")
        path=p.inside(self.ctx.datasets,self.value["fit_pool"][0]["path"])
        with Image.open(path) as image:
            resized=np.asarray(image.convert("RGB").resize((256,256),Image.Resampling.BILINEAR),dtype=np.float32)/255
        reference=(resized.transpose(2,0,1)-np.asarray([0.485,0.456,0.406])[:,None,None])/np.asarray([0.229,0.224,0.225])[:,None,None]
        tensor=load_image(path)[0]
        np.testing.assert_allclose(tensor.numpy(),reference,atol=1e-6,rtol=1e-6)
        model=resnet18(weights=None)
        model.load_state_dict(torch.load(self.ctx.weights,map_location="cpu",weights_only=True),strict=True)
        model.eval().requires_grad_(False)
        with torch.inference_mode():
            x=model.maxpool(model.relu(model.bn1(model.conv1(tensor[None]))))
            expected={}
            for layer in p.SHAPES:x=getattr(model,layer)(x);expected[layer]=x.numpy()
        with c.CacheReader(self.ctx,Path(self.extracted["path"]),self.extracted["identity"]) as reader:
            got=reader.get([self.value["fit_pool"][0]["path"]],p.SHAPES)
            for layer in p.SHAPES:
                np.testing.assert_allclose(got[layer],expected[layer],atol=1e-4,rtol=1e-4)
        bad=OUTPUT/"bad_weights.pth";bad.write_bytes(b"invalid local weights")
        with self.assertRaises(ValueError):c.build_extractor(replace(self.ctx,weights=bad),"cuda")

    def test_02_both_methods_saved_metrics_and_skip(self):
        for method in ("padim","patchcore"):
            result=self.execute(method)
            self.assertEqual(result["status"],"completed")
            self.assertEqual(r.verify_result(self.ctx,Path(result["path"]))["status"],"passed")
            evidence=p.read_json(Path(result["path"])/"evidence.json")
            key="dims_seed" if method=="padim" else "sampling_seed"
            self.assertEqual(evidence["method_detail"][key],17)
            self.assertEqual(len(p.read_json(Path(result["path"])/"metrics.json")["image"]),5)
            with patch(method+"_adapter.fit_"+method,side_effect=AssertionError("Skip must not fit")):
                self.assertEqual(self.execute(method)["status"],"skipped")
            with self.assertRaises(ValueError):r.verify_result(p.context(ROOT),Path(result["path"]))

    def test_03_failure_then_recovery_and_corruption(self):
        with patch("padim_adapter.predict_padim",side_effect=RuntimeError("injected prediction failure")):
            with self.assertRaisesRegex(RuntimeError,"injected"):self.execute("padim",29)
        failures=list(self.ctx.output("results").glob(".*.partial.*/FAILED.json"))
        self.assertEqual(len(failures),1)
        self.assertFalse((failures[0].parent/"SUCCESS").exists())
        result=self.execute("padim",29)
        target=Path(result["path"]);(target/"metrics.json").write_text("{}",encoding="utf-8")
        before={path.name:p.sha(path) for path in target.iterdir()}
        with self.assertRaises(ValueError):self.execute("padim",29)
        self.assertEqual(before,{path.name:p.sha(path) for path in target.iterdir()})
        self.assertTrue(failures[0].exists())

    def test_04_other_run_seeds_and_incomplete_result(self):
        for method,seed in [("patchcore",29),("padim",43),("patchcore",43)]:
            result=self.execute(method,seed)
            evidence=p.read_json(Path(result["path"])/"evidence.json")
            key="dims_seed" if method=="padim" else "sampling_seed"
            self.assertEqual(evidence["method_detail"][key],seed)
            self.assertEqual(r.verify_result(self.ctx,Path(result["path"]))["status"],"passed")
        target=Path(result["path"]);(target/"SUCCESS").unlink()
        before={path.name:p.sha(path) for path in target.iterdir()}
        with self.assertRaises(ValueError):self.execute("patchcore",43)
        self.assertEqual(before,{path.name:p.sha(path) for path in target.iterdir()})


def suite(test_class, filename):
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(test_class))
    text=stream.getvalue();print(text)
    (OUTPUT/filename).write_text(text,encoding="utf-8")
    return {"tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),
            "passed":result.wasSuccessful() and not result.skipped,
            "failure_details":[{"test":test.id(),"traceback":trace} for test,trace in result.failures+result.errors]}


def regression(script, directory, flag):
    completed=subprocess.run([sys.executable,"-B",str(ROOT/script),"--mode","full","--output-dir",str(OUTPUT/directory)],capture_output=True,text=True)
    (OUTPUT/(directory+".txt")).write_text(completed.stdout+completed.stderr,encoding="utf-8")
    result=p.read_json(OUTPUT/directory/"setup_status.json")
    if completed.returncode or result.get(flag) is not True or result.get("status")!="passed":
        raise RuntimeError("Required unchanged regression failed: "+directory)
    return result


def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("core","full"),default="core")
    parser.add_argument("--output-dir",required=True,type=Path)
    args=parser.parse_args();OUTPUT=args.output_dir.absolute()
    allowed=(ROOT/"run/validation_tc2_gpu").resolve()
    if OUTPUT==allowed or not OUTPUT.resolve().is_relative_to(allowed) or OUTPUT.exists():parser.error("Use a fresh directory strictly under validation")
    p.inside(allowed,OUTPUT.relative_to(allowed).as_posix());OUTPUT.mkdir(parents=True)
    status={"mode":args.mode,"status":"failed","step_5_complete":False,"checked_at_utc":datetime.now(timezone.utc).isoformat()}
    try:
        p.contract(ROOT)
        if args.mode=="full":
            status["runtime"]=p.prepare_torch(p.context(ROOT,OUTPUT/"guard"))
            status["metric_regression"]=regression("tests/test_metrics_tc2_gpu.py","metric_regression","step_3_complete")
            status["algorithm_regression"]=regression("tests/test_algorithms_tc2_gpu.py","algorithm_regression","step_4_complete")
        status["core"]=suite(CoreTests,"core_tests.txt")
        if status["core"]["passed"] and args.mode=="full":status["gpu"]=suite(GPUTests,"gpu_tests.txt")
        passed=status["core"]["passed"] and (args.mode=="core" or status.get("gpu",{}).get("passed",False))
        status.update(status="passed" if passed else "failed",step_5_complete=passed and args.mode=="full")
    except Exception as error:
        import traceback
        status["error"]=type(error).__name__+": "+str(error);status["traceback"]=traceback.format_exc()
    status["source_hashes"]={name:p.sha(ROOT/name) for name in payload_files() if not name.startswith("docs/")}
    status["payload_hashes"]={name:p.sha(ROOT/name) for name in payload_files()}
    p.write_json(OUTPUT/"setup_status.json",status)
    print(json.dumps(status,indent=2,allow_nan=False))
    return 0 if status["status"]=="passed" else 1


if __name__=="__main__":raise SystemExit(main())
