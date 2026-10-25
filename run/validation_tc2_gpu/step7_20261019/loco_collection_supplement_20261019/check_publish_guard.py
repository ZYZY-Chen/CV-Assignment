"""Run only the rendered publication Python against fresh local fixtures."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import uuid

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
COURSE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS")
HERE = Path(__file__).resolve().parent
text = (COURSE / "output/tc2_gpu_setup.ps1").read_text(encoding="utf-8")
matches = re.findall(r"<<'LOCO_COLLECTION_PUBLISH_PY'\n(.*?)\nLOCO_COLLECTION_PUBLISH_PY", text, re.S)
assert len(matches) == 1
program = matches[0]
base = (ROOT / "scripts/collect_experiments_tc2_gpu.py").read_bytes()
collector = (ROOT / "scripts/collect_experiments_loco_tc2_gpu.py").read_bytes()
sha = lambda data: hashlib.sha256(data).hexdigest()
base_sha, collector_sha = sha(base).upper(), sha(collector)
assert base_sha == "AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010"
fixtures = COURSE / "output" / ("loco_publish_" + uuid.uuid4().hex[:8])
fixtures.mkdir()
results = []
for case in ("create", "identical", "target_conflict", "base_mismatch", "upload_mismatch", "upload_oversize"):
    root = fixtures / case
    (root / "scripts").mkdir(parents=True)
    (root / "_downloads").mkdir()
    original = root / "scripts/collect_experiments_tc2_gpu.py"
    original.write_bytes(base if case != "base_mismatch" else base + b"\n# negative fixture\n")
    old_base = original.read_bytes()
    incoming = root / "_downloads/loco-collector-offline.py"
    data = collector
    if case == "upload_mismatch":
        data += b"\n# negative fixture\n"
    if case == "upload_oversize":
        data = b"#" * 262145
    incoming.write_bytes(data)
    target = root / "scripts" / ("collect_experiments_loco_tc2_gpu_" + collector_sha[:16] + ".py")
    if case == "identical":
        target.write_bytes(collector)
    if case == "target_conflict":
        target.write_bytes(b"conflicting fixture; must not be overwritten")
    previous = target.read_bytes() if target.exists() else None
    result = subprocess.run([sys.executable, "-I", "-B", "-", str(root), "offline", collector_sha, base_sha],
                            input=program, text=True, capture_output=True, check=False)
    success = case in ("create", "identical")
    assert (result.returncode == 0) == success, (case, result.stderr)
    assert original.read_bytes() == old_base
    if success:
        assert target.read_bytes() == collector
        assert result.stdout.strip() == "LOCO_COLLECTION_REMOTE_COLLECTOR_SHA256=" + collector_sha.upper()
    elif previous is None:
        assert not target.exists()
    else:
        assert target.read_bytes() == previous
    results.append({"case": case, "status": "passed", "exit_code": result.returncode,
                    "frozen_base_unchanged": True, "conflict_not_overwritten": True})
value = {"status": "passed", "fixture_root": str(fixtures), "checks": results,
         "collector_sha256": collector_sha.upper(), "base_collector_sha256": base_sha,
         "actual_tc2_connections": 0, "actual_slurm_submissions": 0, "actual_model_calls": 0}
with (HERE / "publish_guard_validation.json").open("x", encoding="utf-8") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value, indent=2))
