"""Execute extracted publication/state code against fresh local fixtures only."""
from pathlib import Path
import copy
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import uuid

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
AUDIT = ROOT / "run/validation_tc2_gpu/step8_20261019"
HELPER = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
WORK = HELPER.parent / ("s8_publish_" + uuid.uuid4().hex[:8])
WORK.mkdir()
sha = lambda b: hashlib.sha256(b).hexdigest().upper()
registry_bytes = (AUDIT / "validated_inputs_final.json").read_bytes()
registry = json.loads(registry_bytes)
new_files = set(registry["analysis_sources"])
source = HELPER.read_text(encoding="utf-8-sig")
bootstrap = re.search(r"<<'ANALYSIS_BOOTSTRAP_PY'\n(.*?)\nANALYSIS_BOOTSTRAP_PY", source, re.S).group(1)
wrapper = (ROOT / "scripts/slurm/analysis_tc2_gpu.sh").read_text()
initial = re.search(r"<<'ANALYSIS_INITIAL_STATE_PY'\n(.*?)\nANALYSIS_INITIAL_STATE_PY", wrapper, re.S).group(1)
failed = re.search(r"<<'ANALYSIS_FAILED_STATE_PY'\n(.*?)\nANALYSIS_FAILED_STATE_PY", wrapper, re.S).group(1)

def fixture(name):
    root = WORK / name
    root.mkdir()
    for relative in registry["protected_sources"]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    last = root / "run/validation_tc2_gpu/step7_job_44235/setup_status.json"
    last.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "run/validation_tc2_gpu/step7_20261019/accepted_job_44235/remote_setup_status.json", last)
    (root / "_downloads").mkdir()
    return root

def bundle(root, run="20261019_230000_1234abcd", *, change=None, extra=None, duplicate=False, pax=False):
    values = {relative: (ROOT / relative).read_bytes() for relative in new_files}
    values["inputs.json"] = registry_bytes
    if change:
        values[change] += b"\n# Deliberate mismatched input fixture.\n"
    values["analysis.sha256"] = "".join(sha(b).lower()+"  "+name+"\n" for name,b in values.items()).encode()
    archive = root / ("_downloads/analysis-files-" + run + ".tar")
    with tarfile.open(archive, "w:") as stream:
        for name, data in values.items():
            member = tarfile.TarInfo(name)
            if pax:
                member.pax_headers = {"comment":"Disallowed archive extension"}
            member.size = len(data)
            stream.addfile(member, io.BytesIO(data))
        if extra:
            member = tarfile.TarInfo(extra)
            member.size = 1
            stream.addfile(member, io.BytesIO(b"x"))
        if duplicate:
            member = tarfile.TarInfo("inputs.json")
            member.size = len(registry_bytes)
            stream.addfile(member, io.BytesIO(registry_bytes))
    return run, sha(archive.read_bytes()).lower(), sha(registry_bytes)

def invoke(script, arguments):
    original = sys.argv
    try:
        sys.argv = ["offline-extracted-code", *map(str, arguments)]
        exec(compile(script, "offline-extracted-code", "exec"), {"__name__":"__main__"})
    finally:
        sys.argv = original

cases = []
for name in ("valid", "wrong_bundle_hash", "unsafe_path", "extra_file", "duplicate_member", "pax_headers", "changed_source", "protected_change", "target_conflict", "step7_incomplete", "existing_publication"):
    root = fixture(name)
    args = bundle(root, change="scripts/plot_results_tc2_gpu.py" if name == "changed_source" else None,
                  extra="../escaped.txt" if name == "unsafe_path" else "unexpected.txt" if name == "extra_file" else None,
                  duplicate=name == "duplicate_member",pax=name == "pax_headers")
    if name == "protected_change":
        target = root / next(iter(registry["protected_sources"]))
        target.write_bytes(target.read_bytes()+b"\n")
    if name == "target_conflict":
        target = root / "scripts/plot_results_tc2_gpu.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Do not overwrite this file.\n")
    if name == "step7_incomplete":
        target = root / "run/validation_tc2_gpu/step7_job_44235/setup_status.json"
        state = json.loads(target.read_bytes()); state["step_7_complete"] = False
        target.write_text(json.dumps(state))
    if name == "existing_publication":
        (root / ("run/validation_tc2_gpu/analysis_stage_"+args[0])).mkdir()
    before = {p: sha((root/p).read_bytes()) for p in registry["protected_sources"]}
    caught = None
    try:
        invoke(bootstrap, [root,args[0],"0"*64 if name == "wrong_bundle_hash" else args[1],args[2]])
    except Exception as error:
        caught = type(error).__name__+": "+str(error)
    assert (caught is None) == (name == "valid"), (name,caught)
    assert before == {p: sha((root/p).read_bytes()) for p in registry["protected_sources"]}, name
    if name == "valid":
        assert all(sha((root/p).read_bytes()) == value for p,value in registry["analysis_sources"].items())
        relative = "run/validation_tc2_gpu/analysis_inputs_"+args[0]+"/inputs.json"
        record = root / "run/validation_tc2_gpu/step8_job_90001"
        record.mkdir()
        stage_relative = "run/validation_tc2_gpu/analysis_stage_"+args[0]
        os.environ["TC2_ANALYSIS_STAGE_DIR"] = stage_relative
        invoke(initial, [root,record,relative,"90001",root/stage_relative/"submission_lf.sh"])
        state = json.loads((record/"setup_status.json").read_bytes())
        assert state["stage_id"] == "analysis" and state["status"] == "running" and not state["step_8_complete"] and state["publication"]["status"] == "published"
        invoke(failed, [record/"setup_status.json",2])
        state = json.loads((record/"setup_status.json").read_bytes())
        assert state["status"] == "failed" and not state["step_8_complete"]
        # A second run may reuse identical source bytes, without replacing any existing source.
        second = bundle(root,run="20261019_230001_1234abcd")
        invoke(bootstrap, [root,*second])
        assert before == {p: sha((root/p).read_bytes()) for p in registry["protected_sources"]}
        for wrong in ("source", "executing_script", "stage"):
            failed_record = root / ("run/validation_tc2_gpu/step8_job_9000"+str(2+len(wrong)))
            failed_record.mkdir()
            executing = root/stage_relative/"submission_lf.sh"
            changed_path = root/"scripts/plot_results_tc2_gpu.py"
            if wrong == "source":
                original = changed_path.read_bytes(); changed_path.write_bytes(original+b"\n")
            elif wrong == "stage":
                os.environ["TC2_ANALYSIS_STAGE_DIR"] = stage_relative+"BAD"
            else:
                executing = root/"wrong_executing.sh"; executing.write_text("# Wrong spool snapshot\n")
            refused = False
            try:
                invoke(initial,[root,failed_record,relative,"90001",executing])
            except RuntimeError:
                refused = True
            assert refused, wrong
            assert json.loads((failed_record/"setup_status.json").read_bytes())["status"] == "running"
            invoke(failed,[failed_record/"setup_status.json",2])
            assert json.loads((failed_record/"setup_status.json").read_bytes())["status"] == "failed"
            if wrong == "source": changed_path.write_bytes(original)
            os.environ["TC2_ANALYSIS_STAGE_DIR"] = stage_relative
    cases.append({"name":name,"status":"passed","expected_refusal":caught})
result = {"status":"passed","cases":cases,"wrapper_initial_and_failure_state":"passed",
          "identical_source_reuse":"passed","protected_source_count":44,"actual_tc2_connections":0,
          "actual_slurm_submissions":0,"fixture_root":str(WORK)}
(AUDIT / "analysis_publication_validation.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"status":"passed","cases":len(cases),"fixture_root":str(WORK)},indent=2))
