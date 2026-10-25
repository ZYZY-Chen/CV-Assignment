"""Offline provenance regression: historical bytes, current isolation and rejection guards."""
from __future__ import annotations
import argparse,hashlib,io,json
from pathlib import Path
import sys,tempfile,unittest,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import tc2_gpu_provenance as v
import tc2_gpu_protocol as p
import tc2_gpu_cache as cache
OUTPUT=None
class ProvenanceTests(unittest.TestCase):
    def tiny(self):
        context=tempfile.TemporaryDirectory(prefix="pv_",dir=OUTPUT)
        self.addCleanup(context.cleanup)
        root=Path(context.name);(root/"archive").mkdir();(root/"configs/tc2_gpu").mkdir(parents=True)
        data=b"verified historical fixture\n";z=root/"archive/sample.zip"
        with zipfile.ZipFile(z,"w") as f:f.writestr("original/value.txt",data)
        index={"schema_version":"1.0","workflow_id":"tc2_gpu","archives":{"archive/sample.zip":{"sha256":hashlib.sha256(z.read_bytes()).hexdigest().upper(),"size":z.stat().st_size}},
          "entries":{"old/value.txt":{"archive":"archive/sample.zip","member":"original/value.txt","sha256":hashlib.sha256(data).hexdigest().upper(),"size":len(data)}},
          "aliases":{},"roles":{}}
        (root/"archive/index.json").write_text(json.dumps(index),encoding="utf-8")
        (root/"configs/tc2_gpu/setup.json").write_text(json.dumps({"deployment":{"status":"unavailable","acceptance_record":None}}),encoding="utf-8")
        return root,data
    def test_original_protocol_identity_is_preserved(self):
        self.assertEqual(v.historical_config_sha(ROOT,"protocol"),"3098B6A86DBA64EE439BFE61C7A4FCFFCD082371D5A80FFBC7940997ED6A1ED1")
        self.assertEqual(v.historical_config(ROOT,"protocol")["protocol_id"],"ca6129_industrial_ad_v2")
        self.assertEqual(v.read_current_config(ROOT,"protocol")["protocol_id"],"ca6129_industrial_ad_tc2_gpu")
        self.assertNotEqual(p.PROTOCOL_SHA256,v.historical_config_sha(ROOT,"protocol"))
    def test_old_pilot_acceptance_is_not_current_permission(self):
        historic=v.historical_config(ROOT,"experiments");current=v.read_current_config(ROOT,"experiments")
        self.assertEqual(historic["expected_new_fits"],64);self.assertEqual(current["expected_new_fits"],66)
        self.assertEqual(current["accepted_pilot_results"],[]);self.assertIsNone(current["accepted_pilot_job_id"])
        with self.assertRaisesRegex(RuntimeError,"unavailable|not configured"):v.require_current_acceptance(ROOT,"pilot")
    def test_formal_preflight_rejects_before_tensor_import(self):
        before="torch" in sys.modules
        with self.assertRaises(RuntimeError):p.prerequisites(ROOT)
        self.assertEqual("torch" in sys.modules,before)
    def test_legacy_cache_identity_is_rejected(self):
        ctx=p.context(ROOT)
        identity={"namespace":"formal","format":"tc2_gpu_fp32_npy_1","dtype":"float32","protocol_sha256":v.historical_config_sha(ROOT,"protocol")}
        with self.assertRaises(ValueError):cache.cache_directory(ctx,identity)
    def test_historical_roundtrip_checks_bytes(self):
        root,data=self.tiny()
        self.assertEqual(v.historical_bytes(root,"old/value.txt"),data)
        self.assertEqual(v.verify_archive(root)["members_verified"],1)
    def test_archive_tampering_is_rejected(self):
        root,data=self.tiny()
        self.assertEqual(v.historical_bytes(root,"old/value.txt"),data)
        with zipfile.ZipFile(root/"archive/sample.zip","w") as f:f.writestr("original/value.txt",b"tampered historical fixture\n")
        with self.assertRaises(ValueError):v.historical_bytes(root,"old/value.txt")
    def test_index_tampering_is_rejected_by_current_manifest(self):
        root,_=self.tiny();index=root/"archive/index.json"
        manifest={"schema_version":"1.0","workflow_id":"tc2_gpu","profile":"current","status":"sealed",
                  "archive_index_sha256":hashlib.sha256(index.read_bytes()).hexdigest().upper(),"files":{},"groups":{}}
        (root/"configs/tc2_gpu/source_manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        index.write_bytes(index.read_bytes()+b"\n")
        with self.assertRaises(ValueError):v.archive_index(root)
    def test_current_source_tampering_is_rejected(self):
        root,_=self.tiny();target=root/"source.txt";target.write_bytes(b"approved")
        manifest={"schema_version":"1.0","workflow_id":"tc2_gpu","profile":"current","status":"sealed",
                  "files":{"source.txt":hashlib.sha256(b"approved").hexdigest().upper()},"groups":{"workflow":["source.txt"]}}
        (root/"configs/tc2_gpu/source_manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        self.assertEqual(v.current_source_hashes(root)["source.txt"],hashlib.sha256(b"approved").hexdigest().upper())
        target.write_bytes(b"changed")
        with self.assertRaises(ValueError):v.current_source_hashes(root)
    def test_unsafe_and_unknown_historical_paths_are_rejected(self):
        for name in ("../outside","/absolute","a\\b","C:/outside","a/../b"):
            with self.subTest(name=name),self.assertRaises(ValueError):v.historical_bytes(ROOT,name)
        with self.assertRaises(FileNotFoundError):v.historical_bytes(ROOT,"unknown/file")
    def test_configured_without_current_receipt_still_rejects(self):
        root,_=self.tiny()
        (root/"configs/tc2_gpu/setup.json").write_text(json.dumps({"deployment":{"status":"configured","acceptance_record":None}}),encoding="utf-8")
        manifest={"schema_version":"1.0","workflow_id":"tc2_gpu","profile":"current","status":"sealed","files":{},"groups":{}}
        (root/"configs/tc2_gpu/source_manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError,"acceptance"):v.require_current_acceptance(root,"workflow")
def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output-dir",required=True,type=Path)
    args=parser.parse_args();OUTPUT=args.output_dir.resolve()
    allowed=(ROOT/"run/validation_tc2_gpu").resolve()
    if OUTPUT.exists() or OUTPUT==allowed or not OUTPUT.is_relative_to(allowed):parser.error("Use a fresh short validation directory")
    OUTPUT.mkdir(parents=True)
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProvenanceTests))
    (OUTPUT/"offline_tests.txt").write_text(stream.getvalue(),encoding="utf-8")
    status={"mode":"offline","status":"passed" if result.wasSuccessful() and not result.skipped else "failed","tests_run":result.testsRun,
            "failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),"new_gpu_acceptance":False}
    (OUTPUT/"setup_status.json").write_text(json.dumps(status,indent=2)+"\n",encoding="utf-8")
    print(stream.getvalue());print(json.dumps(status));return 0 if status["status"]=="passed" else 1
if __name__=="__main__":raise SystemExit(main())

