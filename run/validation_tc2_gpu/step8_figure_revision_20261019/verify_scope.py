"""Read-only preservation audit for the approved figure revision supplement."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
AUDIT = ROOT / "run/validation_tc2_gpu/step8_figure_revision_20261019"
HELPER = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
before = json.loads((AUDIT / "before_scope.json").read_bytes())
problems = []
for name, spec in before["sources"].items():
    path = ROOT / name
    if not path.is_file() or sha(path) != spec["sha256"] or path.stat().st_mtime_ns != spec["mtime_ns"]:
        problems.append("Preexisting source changed: " + name)
for name, spec in before["historical_run_files"].items():
    path = ROOT / name
    if not path.is_file() or path.stat().st_size != spec["bytes"] or path.stat().st_mtime_ns != spec["mtime_ns"]:
        problems.append("Historical run file changed: " + name)
actual_sources = {p.relative_to(ROOT).as_posix() for folder in ("configs", "scripts", "tests", "docs", "src")
                  for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
new = actual_sources - set(before["sources"])
if new != set(before["new_runtime_files"]):
    problems.append("New runtime source set differs: " + repr(sorted(new)))

current = HELPER.read_bytes()
addition = (AUDIT / "helper_additions.ps1").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
insert = addition + b"\r\n\r\n"
if current.count(insert) != 1:
    problems.append("Helper addition differs from reviewed transport code")
else:
    restored = current.replace(insert, b"", 1)
    restored = restored.replace(b"'CollectAnalysis','RepairAnalysisDependency','RunFigureRevision','CollectFigureRevision')",
                                b"'CollectAnalysis','RepairAnalysisDependency')")
    branch = b"    } elseif ($Action -eq 'RunFigureRevision') {\n        Run-FigureRevision\n    } elseif ($Action -eq 'CollectFigureRevision') {\n        if (-not $JobId -or $InputDirectory) { throw 'CollectFigureRevision requires -JobId and accepts no input directory.' }\n        Receive-FigureRevision $JobId\n".replace(b"\n", b"\r\n")
    if restored.count(branch) != 1:
        problems.append("New helper dispatch differs")
    else:
        restored = restored.replace(branch, b"", 1)
        if restored != (AUDIT / "helper.before.ps1").read_bytes():
            problems.append("Unapproved change to preexisting helper behavior")

original_readme = (AUDIT / "README.before.md").read_bytes()
readme = (ROOT / "README.md").read_bytes()
chinese_lines = lambda data: [line for line in data.decode("utf-8").splitlines() if re.search(r"[\u4e00-\u9fff]", line)]
if chinese_lines(original_readme) != chinese_lines(readme):
    problems.append("Existing Chinese README content changed")
english = {}
for name in sorted(new):
    if re.search(r"[\u4e00-\u9fff]", (ROOT / name).read_text(encoding="utf-8")):
        problems.append("New source includes Chinese text: " + name)
    english[name] = sha(ROOT / name)
if problems:
    raise RuntimeError(json.dumps(problems, indent=2))
result = {"status": "passed", "preexisting_source_files_preserved": len(before["sources"]),
          "historical_run_files_preserved": len(before["historical_run_files"]),
          "helper_old_behavior_byte_preserved": True, "existing_chinese_readme_preserved": True,
          "new_runtime_sources": english, "helper_sha256": sha(HELPER), "readme_sha256": sha(ROOT / "README.md"),
          "actual_tc2_connections": 0, "actual_slurm_submissions": 0,
          "step_8_complete": False, "post_download_visual_review_required": True}
path = AUDIT / "scope_verification.json"
with path.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2); stream.write("\n")
print(json.dumps({key:value for key,value in result.items() if key != "new_runtime_sources"}))
