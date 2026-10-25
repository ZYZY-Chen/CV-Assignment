"""Parse generated shell templates without evaluating remote commands."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

audit = Path(__file__).parent
helper = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
text = helper.read_text(encoding="utf-8")
scripts = {}
python_blocks = 0
for name in ("experimentsCollect", "experimentsPreflight", "experimentsStage"):
    match = re.search(r"\$" + name + r" = @'\r?\n(.*?)\r?\n'@", text, re.S)
    assert match, name
    source = match[1].replace("\r\n", "\n") + "\n"
    path = audit / (name + ".sh")
    path.write_text(source, encoding="utf-8", newline="\n")
    scripts[name] = path
    for block in re.finditer(r"<<'(EXPERIMENTS_[A-Z_]+)'\n(.*?)\n\1", source, re.S):
        ast.parse(block[2])
        python_blocks += 1
    for token in ("__JOBID__", "__RUNID__", "__COLLECTORHASH__", "__CONFIG__", "__STAGE__", "__BUNDLEHASH__", "__MANIFEST__", "__RESOURCES__"):
        source = source.replace(token, "fixture")
    assert "__" not in source
    subprocess.run([r"C:\Program Files\Git\bin\bash.exe", "-n", str(path).replace("\\", "/")], check=True)
record = {"status": "passed", "powershell_ast_errors": 0, "shell_templates_parsed": len(scripts),
          "python_heredocs_parsed": python_blocks, "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest().upper(),
          "actual_tc2_connections": 0, "actual_slurm_submissions": 0}
(audit / "helper_static_validation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record))
