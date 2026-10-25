#!/usr/bin/env python3
"""TC2 GPU workflow: read-only planning, explicit extraction/run, saved-result verification."""
from pathlib import Path
import argparse
import json
import sys

import importlib.util as _import_util
_bootstrap_spec = _import_util.spec_from_file_location(
    "_tc2_gpu_bootstrap", Path(__file__).resolve().parents[1] / "_bootstrap.py")
_bootstrap = _import_util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)
ROOT = _bootstrap.configure(__file__)
from tc2_gpu_protocol import build_plan, context, select_spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("plan", help="Print the frozen fit matrix and offline analyses; do not create outputs")
    extract = commands.add_parser("extract", help="Extract or validate one category's immutable FP32 cache")
    extract.add_argument("--dataset", required=True, choices=("mvtec_ad", "mvtec_loco"))
    extract.add_argument("--category", required=True)
    run = commands.add_parser("run", help="Execute exactly one run_key from plan")
    run.add_argument("--run-key", required=True)
    verify = commands.add_parser("verify", help="Verify one formal result, including CPU metric reproduction")
    verify.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        result = build_plan(ROOT)
    else:
        ctx = context(ROOT)
        if args.action == "extract":
            from tc2_gpu_cache import extract as extract_category
            result = extract_category(ctx, args.dataset, args.category)
        elif args.action == "run":
            from tc2_gpu_runner import execute
            result = execute(ctx, select_spec(ROOT, args.run_key))
        else:
            from tc2_gpu_runner import verify_result
            result = verify_result(ctx, args.result.absolute())
    print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
