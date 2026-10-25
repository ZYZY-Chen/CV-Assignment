"""Read-only verification of the immutable TC2 GPU and pre-correction archives."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import importlib.util as _import_util
_bootstrap_spec = _import_util.spec_from_file_location(
    "_tc2_gpu_bootstrap", Path(__file__).resolve().parents[1] / "_bootstrap.py")
_bootstrap = _import_util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)
ROOT = _bootstrap.configure(__file__)
from tc2_gpu_provenance import archive_index,historical_sha,verify_archive
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--entry",help="Verify one original repository-relative entry instead of all members")
    args=parser.parse_args()
    if args.entry:
        result={"status":"passed","entry":args.entry,"sha256":historical_sha(args.root,args.entry)}
    else:
        result=verify_archive(args.root)
    print(json.dumps(result,indent=2,ensure_ascii=True))
    return 0
if __name__=="__main__":raise SystemExit(main())

