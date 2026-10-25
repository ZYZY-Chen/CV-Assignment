"""Execute source bootstrap and isolated publication with only host preflight stubbed."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import uuid

AUDIT = Path(__file__).parent
CODE = AUDIT.parents[2]
HELPER = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
OUTPUT = Path(sys.argv[1])
archive = OUTPUT / "experiments-files.tar"
data = archive.read_bytes()
digest = hashlib.sha256(data).hexdigest()
with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as package:
    contents = {member.name: package.extractfile(member).read() for member in package.getmembers()}
manifest = contents["experiments.sha256"]
assert all(line[:64].lower() == line[:64] for line in manifest.splitlines())
text = HELPER.read_text(encoding="utf-8")
source = re.search(r"<<'EXPERIMENTS_BOOTSTRAP_PY'\n(.*?)\nEXPERIMENTS_BOOTSTRAP_PY", text, re.S)[1]
workspace = AUDIT / ("bootstrap_" + uuid.uuid4().hex[:8])
workspace.mkdir()


def bootstrap(case, archive_bytes=data, expected_sha=None, expected_manifest=manifest):
    root = workspace / case
    (root / "tmp").mkdir(parents=True)
    (root / "run/validation_tc2_gpu").mkdir(parents=True)
    tar = root / "source.tar"
    tar.write_bytes(archive_bytes)
    incoming = root / "tmp/incoming"
    arguments = [str(root), str(tar), str(incoming), expected_sha or hashlib.sha256(archive_bytes).hexdigest(), base64.b64encode(expected_manifest).decode()]
    saved = sys.argv
    sys.argv = ["bootstrap", *arguments]
    error = None
    try:
        exec(compile(source, "actual_helper_bootstrap", "exec"), {"__name__": "__main__"})
    except (RuntimeError, ValueError, OSError) as caught:
        error = str(caught)
    finally:
        sys.argv = saved
    return root, incoming, error


root, incoming, error = bootstrap("good")
assert error is None, error
for name, blob in contents.items():
    assert (incoming / name).read_bytes() == blob
for name in ("scripts/pilot_tc2_gpu.py", "src/tc2_gpu_protocol.py"):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CODE / name, target)
probe = workspace / "publication_probe.py"
probe.write_text('''import importlib.util,json,pathlib,sys
root=pathlib.Path(sys.argv[sys.argv.index("--root")+1])
incoming=pathlib.Path(sys.argv[sys.argv.index("--incoming")+1])
record=pathlib.Path(sys.argv[sys.argv.index("--record")+1])
spec=importlib.util.spec_from_file_location("isolated_incoming",incoming/"scripts/experiments_tc2_gpu.py")
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
calls=[]
def host_preflight(*args,**kwargs):
    calls.append("host_preflight_stub_only")
    return {"status":"passed","offline_fixture":True,"model_calls":0}
module.preflight=host_preflight
value=module.publish(root,incoming,"B0",record)
assert calls == ["host_preflight_stub_only"]
print(json.dumps(value,sort_keys=True))
''', encoding="utf-8")
publications = []
for index in range(2):
    record = root / ("run/validation_tc2_gpu/experiments_stage_offline_" + str(index))
    command = [sys.executable, "-I", "-B", str(probe), "--root", str(root), "--incoming", str(incoming), "--record", str(record)]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert value["status"] == "published" and value["files"] == 7
    assert json.loads((record / "preflight.json").read_text())["offline_fixture"] is True
    assert (record / "experiments.sha256").read_bytes() == manifest
    publications.append(value)
files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in contents if name != "experiments.sha256"}
assert all(files[name] == hashlib.sha256(blob).hexdigest() for name, blob in contents.items() if name != "experiments.sha256")
bad_cases = []
for case, archive_bytes, expected_sha, expected_manifest in (
    ("bad_archive_sha", data, "0" * 64, manifest),
    ("bad_source_sha", data, None, manifest.replace(manifest[:64], b"0" * 64, 1)),
):
    badroot, badincoming, failure = bootstrap(case, archive_bytes, expected_sha, expected_manifest)
    assert failure and not badincoming.exists()
    bad_cases.append({"name": case, "status": "passed", "rejection": failure})
for case, member_type in (("bad_member", tarfile.REGTYPE), ("symbolic_member", tarfile.SYMTYPE)):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:") as package:
        for name, blob in contents.items():
            member = tarfile.TarInfo(name)
            member.size = len(blob)
            if member_type == tarfile.SYMTYPE and name == "scripts/experiments_tc2_gpu.py":
                member.type, member.linkname, member.size = tarfile.SYMTYPE, "outside", 0
                package.addfile(member)
            else:
                package.addfile(member, io.BytesIO(blob))
        if case == "bad_member":
            member = tarfile.TarInfo("../outside")
            member.size = 1
            package.addfile(member, io.BytesIO(b"x"))
    badroot, badincoming, failure = bootstrap(case, stream.getvalue())
    assert failure and not badincoming.exists()
    bad_cases.append({"name": case, "status": "passed", "rejection": failure})
result = {"status": "passed", "archive_sha256": digest.upper(), "packaging_directory": str(OUTPUT),
          "exact_members": 8, "payload_sha256": {name: hashlib.sha256(blob).hexdigest().upper() for name, blob in contents.items() if name != "experiments.sha256"},
          "actual_bootstrap_positive": True, "isolated_publication_absent_then_identical": publications,
          "lowercase_manifest_normalized": True, "host_preflight_stubbed_explicitly": True, "negative_cases": bad_cases,
          "actual_tc2_connections": 0, "actual_slurm_submissions": 0, "actual_model_calls": 0}
(AUDIT / "experiments_bootstrap_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": "passed", "bootstrap_cases": 5, "isolated_publication_cases": 2, "actual_tc2_connections": 0, "actual_slurm_submissions": 0}))
