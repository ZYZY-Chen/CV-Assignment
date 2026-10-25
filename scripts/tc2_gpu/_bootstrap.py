"""Resolve repository imports for direct, isolated TC2 GPU script execution."""
from __future__ import annotations

from pathlib import Path
import sys


def _root_option(arguments):
    for index, argument in enumerate(arguments):
        if argument == "--root":
            if index + 1 >= len(arguments):
                raise ValueError("--root requires a repository path")
            return Path(arguments[index + 1]).resolve()
        if argument.startswith("--root="):
            if not argument.partition("=")[2]:
                raise ValueError("--root requires a repository path")
            return Path(argument.partition("=")[2]).resolve()
    return None


def _module_paths(module):
    source = getattr(module, "__file__", None)
    if source:
        yield Path(source).resolve()
    for path in getattr(module, "__path__", ()):
        yield Path(path).resolve()


def _repository_root(path):
    marker = "scripts/tc2_gpu/_bootstrap.py"
    for directory in (path, *path.parents):
        if directory.name in ("src", "scripts"):
            candidate = directory.parent
            if (candidate / marker).is_file():
                return candidate
    if (path / marker).is_file():
        return path
    return None


def configure(entry_file, argv=None):
    """Use this entry's root, including an explicit root for copied controllers.

    A process may load several repository copies during offline validation.
    Cached package and flat source modules from an earlier copy must not make
    the next entry import code from that earlier repository.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = _root_option(arguments) or Path(entry_file).resolve().parents[3]
    markers = ("scripts/tc2_gpu/_bootstrap.py", "src/tc2_gpu_protocol.py",
               "configs/tc2_gpu/protocol.json")
    missing = [name for name in markers if not (root / name).is_file()]
    if missing:
        raise ValueError("TC2 GPU repository root lacks required files: " + ", ".join(missing))
    scripts = root / "scripts"
    source = root / "src"
    stale = set()
    other_roots = set()
    search_paths = {}
    for value in sys.path:
        if isinstance(value, str):
            directory = Path(value).resolve()
            search_paths[value] = directory
            candidate = _repository_root(directory)
            if candidate is not None and candidate != root:
                other_roots.add(candidate)
    modules = [(name, tuple(_module_paths(module)))
               for name, module in tuple(sys.modules.items()) if module is not None]
    for _, paths in modules:
        for path in paths:
            candidate = _repository_root(path)
            if candidate is not None and candidate != root:
                other_roots.add(candidate)
    for name, paths in modules:
        if name == "scripts" or name.startswith("scripts."):
            if paths and any(not path.is_relative_to(scripts) for path in paths):
                stale.add(name)
        else:
            if any(path.is_relative_to(other / "src") for other in other_roots for path in paths):
                stale.add(name.partition(".")[0])
    for name in tuple(sys.modules):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in stale):
            del sys.modules[name]
    foreign_paths = {directory for other in other_roots for directory in (other, other / "src")}
    sys.path[:] = [value for value in sys.path if search_paths.get(value) not in foreign_paths]
    for directory in (root, source):
        value = str(directory)
        while value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)
    return root
