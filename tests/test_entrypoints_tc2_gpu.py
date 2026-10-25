"""Offline contracts for direct entrypoints, copied roots and the PowerShell client."""
from __future__ import annotations
import argparse, hashlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = None

def inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}

class EntrypointTests(unittest.TestCase):
    def temporary(self):
        value = tempfile.TemporaryDirectory(prefix="f_", dir=OUTPUT)
        self.addCleanup(value.cleanup)
        return Path(value.name)

    def clone(self, parent, name):
        target = parent / name
        for folder in ("src", "scripts", "configs", "manifests"):
            shutil.copytree(ROOT / folder, target / folder, ignore=shutil.ignore_patterns("__pycache__"))
        return target

    def run_python(self, arguments, cwd):
        return subprocess.run([sys.executable, "-I", "-B", *map(str, arguments)], cwd=cwd,
                              capture_output=True, text=True, timeout=60)

    def test_direct_plan_is_readonly_from_an_unrelated_directory(self):
        cwd = self.temporary()
        before = inventory(cwd)
        completed = self.run_python([ROOT / "scripts/tc2_gpu/workflow/run_workflow.py", "plan"], cwd)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(json.loads(completed.stdout)["fits"]), 66)
        self.assertEqual(inventory(cwd), before)

    def test_all_public_python_help_entries_start_without_output(self):
        cwd = self.temporary()
        paths = sorted((ROOT / "scripts/tc2_gpu").rglob("*.py"))
        paths = [p for p in paths if p.name not in ("__init__.py", "_bootstrap.py", "plot_results.py")]
        paths.append(ROOT / "tools/data/make_manifests.py")
        before = inventory(cwd)
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                result = self.run_python([path, "--help"], cwd)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())
        self.assertEqual(inventory(cwd), before)

    def test_two_roots_replace_cached_phase_and_protocol_modules(self):
        sandbox = self.temporary()
        first, second = self.clone(sandbox, "a"), self.clone(sandbox, "b")
        code = """
import importlib.util,json,sys
from pathlib import Path
for i, root in enumerate(sys.argv[1:]):
 root=Path(root).resolve()
 path=root/'scripts/tc2_gpu/experiments/run_stages.py'
 sys.argv=[str(path)]
 spec=importlib.util.spec_from_file_location('_isolated_'+str(i),path)
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 assert module.ROOT==root,(module.ROOT,root)
 assert Path(module.pilot.__file__).resolve().is_relative_to(root)
 protocol=module.pilot.protocol(root)
 assert Path(protocol.__file__).resolve().is_relative_to(root),protocol.__file__
 for name in ('scripts','scripts.tc2_gpu','tc2_gpu_provenance','tc2_gpu_protocol'):
  item=sys.modules[name]
  assert Path(item.__file__).resolve().is_relative_to(root),(name,item.__file__)
 assert not any(Path(p)==root/'scripts/tc2_gpu/collect' for p in sys.path)
print(json.dumps({'isolated_roots':2}))
"""
        result = self.run_python(["-c", code, first, second], sandbox)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_copied_hash_named_entry_honors_both_explicit_root_forms(self):
        sandbox = self.temporary()
        root = self.clone(sandbox, "a")
        copied = sandbox / "8f1a.py"
        shutil.copyfile(ROOT / "scripts/tc2_gpu/experiments/run_stages.py", copied)
        code = """
import importlib.util,sys
from pathlib import Path
entry,root=map(Path,sys.argv[1:3])
for i, tail in enumerate((['--root',str(root)],['--root='+str(root)])):
 sys.argv=[str(entry),*tail]
 spec=importlib.util.spec_from_file_location('_copied_'+str(i),entry)
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 assert module.ROOT==root.resolve()
 assert Path(module.pilot.__file__).resolve().is_relative_to(root.resolve())
print('copied roots verified')
"""
        result = self.run_python(["-c", code, copied, root], sandbox)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bootstrap_uses_entry_root_even_when_loaded_from_another_root(self):
        sandbox = self.temporary()
        root = self.clone(sandbox, "a")
        code = """
import importlib.util,sys
from pathlib import Path
bootstrap,entry=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('_bootstrap_contract',bootstrap)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert module.configure(entry,[])==entry.resolve().parents[3]
"""
        result = self.run_python(["-c", code, ROOT / "scripts/tc2_gpu/_bootstrap.py",
                                 root / "scripts/tc2_gpu/workflow/run_workflow.py"], sandbox)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_client_validate_and_unavailable_rejection_create_no_outputs(self):
        sandbox = self.temporary()
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        self.assertIsNotNone(powershell)
        client = ROOT / "scripts/tc2_gpu/client/tc2_gpu.ps1"
        out = sandbox / "output"
        before = inventory(sandbox)
        base = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(client),
                "-PythonExecutable", sys.executable, "-OutputRoot", str(out)]
        result = subprocess.run([*base, "-ValidateOnly"], cwd=sandbox, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertIn(66, value.values())
        self.assertEqual(inventory(sandbox), before)
        result = subprocess.run([*base, "-Action", "Probe"], cwd=sandbox, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unavailable", (result.stdout + result.stderr).lower())
        self.assertFalse(out.exists())
        self.assertEqual(inventory(sandbox), before)

    def test_missing_dependency_in_second_root_never_falls_back(self):
        sandbox = self.temporary()
        first, second = self.clone(sandbox, "a"), self.clone(sandbox, "b")
        (second / "src/metric_core.py").unlink()
        code = """
import importlib.util,sys
from pathlib import Path
bootstrap,first,second=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('_no_fallback',bootstrap)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.configure(first/'scripts/tc2_gpu/workflow/run_workflow.py',[])
import metric_core
assert Path(metric_core.__file__).resolve().is_relative_to(first)
module.configure(second/'scripts/tc2_gpu/workflow/run_workflow.py',[])
try:
 import metric_core
except ModuleNotFoundError:
 pass
else:
 raise AssertionError('Missing isolated dependency silently used another repository')
"""
        result = self.run_python(["-c", code, ROOT / "scripts/tc2_gpu/_bootstrap.py", first, second], sandbox)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    OUTPUT = args.output_dir.resolve()
    allowed = (ROOT / "run/validation_tc2_gpu").resolve()
    if OUTPUT.exists() or OUTPUT == allowed or not OUTPUT.is_relative_to(allowed):
        parser.error("Use a fresh short validation directory")
    OUTPUT.mkdir(parents=True)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EntrypointTests))
    status = {"mode": "offline", "status": "passed" if result.wasSuccessful() and not result.skipped else "failed",
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "new_gpu_acceptance": False}
    (OUTPUT / "offline_tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    (OUTPUT / "setup_status.json").write_text(json.dumps(status, indent=2)+"\n", encoding="utf-8")
    print(stream.getvalue()); print(json.dumps(status))
    return 0 if status["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())

