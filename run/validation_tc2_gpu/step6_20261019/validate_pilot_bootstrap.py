"""Execute the exact rendered standard-library bootstrap against local fixtures."""
from pathlib import Path
import base64
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import uuid

audit = Path(__file__).parent
transport = json.loads((audit / "pilot_transport_validation.json").read_text())
rendered = list(Path(transport["validation_root"]).rglob("command_*.sh"))
stages = [path for path in rendered if "PILOT_BOOTSTRAP_PY" in path.read_text()]
assert len(stages) == 1
text = stages[0].read_text()
script = re.search(r"<<'PILOT_BOOTSTRAP_PY'\n(.*?)\nPILOT_BOOTSTRAP_PY", text, re.S)[1]
compile(script, "rendered-pilot-bootstrap", "exec")
preflights = [path for path in rendered if "PILOT_PREFLIGHT_PY" in path.read_text()]
assert len(preflights) == 1
preflight = re.search(r"<<'PILOT_PREFLIGHT_PY'\n(.*?)\nPILOT_PREFLIGHT_PY", preflights[0].read_text(), re.S)[1]
compile(preflight, "rendered-pilot-preflight", "exec")
bundle = stages[0].parent / "pilot-files.tar"
with tarfile.open(bundle) as package:
    contents = {item.name: package.extractfile(item).read() for item in package.getmembers()}
assert len(contents) == 7
manifest = contents["pilot.sha256"]
assert all(hashlib.sha256(contents[line.split("  ", 1)[1]]).hexdigest() == line.split("  ", 1)[0]
           for line in manifest.decode().splitlines())
fixture = audit / ("bootstrap_" + uuid.uuid4().hex[:8])
fixture.mkdir()
cases = []
for case in ("valid", "bad_archive_sha256", "unexpected_member", "duplicate_member", "symlink_member", "bad_payload_sha256", "missing_member", "unknown_manifest", "existing_destination"):
    root = fixture / case
    root.mkdir()
    archive, incoming = root / "payload.tar", root / "incoming"
    entries = list(contents.items())
    candidate_manifest = manifest
    if case == "unexpected_member":
        entries.append(("../outside.txt", b"unsafe"))
    if case == "duplicate_member":
        entries.append(entries[-1])
    if case == "bad_payload_sha256":
        entries[0] = (entries[0][0], b"changed")
    if case == "missing_member":
        entries.pop()
    if case == "unknown_manifest":
        candidate_manifest = manifest + b"0" * 64 + b"  ../outside.txt\n"
    if case == "existing_destination":
        incoming.mkdir()
        (incoming / "preserved.txt").write_bytes(b"preserved")
    with tarfile.open(archive, "w") as package:
        for index, (name, value) in enumerate(entries):
            member = tarfile.TarInfo(name)
            member.size = len(value)
            if case == "symlink_member" and index == 0:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                member.size = 0
                package.addfile(member)
            else:
                package.addfile(member, io.BytesIO(value))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if case == "bad_archive_sha256":
        digest = "0" * 64
    command = [sys.executable, "-I", "-B", "-", str(root), str(archive), str(incoming), digest,
               base64.b64encode(candidate_manifest).decode()]
    result = subprocess.run(command, input=script, text=True, capture_output=True)
    (root / "stdout.txt").write_text(result.stdout)
    (root / "stderr.txt").write_text(result.stderr)
    if case == "valid":
        assert result.returncode == 0, result.stderr
        assert {str(item.relative_to(incoming)).replace("\\", "/"): item.read_bytes()
                for item in incoming.rglob("*") if item.is_file()} == contents
    elif case == "existing_destination":
        assert result.returncode != 0
        assert list(incoming.iterdir()) == [incoming / "preserved.txt"]
        assert (incoming / "preserved.txt").read_bytes() == b"preserved"
    else:
        assert result.returncode != 0 and not incoming.exists(), case
    cases.append({"case": case, "status": "passed", "returncode": result.returncode})
result = {"status": "passed", "exact_rendered_bootstrap_executed": True, "fixture": str(fixture),
          "cases": cases, "embedded_python_scripts_compiled": 2, "pilot_payload_files": 6,
          "actual_tc2_connections": 0, "actual_slurm_submissions": 0,
          "readiness_note": "Real TC2 readiness was not claimed or simulated; only delivery bootstrap was executed locally."}
(audit / "pilot_bootstrap_validation.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
