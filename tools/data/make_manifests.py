#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_manifests.py — CA6129 group project: consistent data splits and manifest generation
=====================================================================================

Follow the split protocol on page 2 of the CA6129 industrial anomaly detection
topic and team assignment handbook:

  1. Use fixed split seed 20261017. For each MVTec AD category, reserve about
     20% of official train/good as the normal development set (normal images
     only, for distribution/operating-threshold calibration, not model selection).
     Use the remaining 80% as the normal fitting pool.
  2. Do not split MVTec LOCO: use official validation/good as the normal
     development set and all train/good images as the fitting pool.
  3. Lock official test and ground_truth; exclude them from development/fitting.
  4. Use run seeds 17 / 29 / 43, selecting 100 fitting-pool images per seed.
     For the same seed, the 20 / 50 / 100 image subsets are nested (20⊂50⊂100).
     PaDiM and PatchCore share the same manifest for each seed; generate it once.
  5. Record each file's SHA-256 and one split_hash per category as run evidence.

Uses only the Python standard library; runs on Python 3.8+ without a GPU.

Usage (from tools/data/):
    py make_manifests.py
    py make_manifests.py --datasets-root ../../datasets --out-dir ../../manifests
    py make_manifests.py --rehash        # Recompute all hashes instead of trusting file_inventory.csv

Outputs (written to --out-dir, default ../../manifests/):
    manifest_<dataset>_<category>.json   Complete manifest for each category (8 files)
    manifest_index.json                 Configuration, counts, and split_hash summary
    splits_overview.csv                 Human-readable split overview
"""

import argparse
import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixed experiment protocol (record approved changes in the report and update split_hash)
# ---------------------------------------------------------------------------
SPLIT_SEED = 20261017          # Development/fitting-pool split seed for MVTec AD
DEV_RATIO = 0.20               # Development fraction of train/good
RUN_SEEDS = [17, 29, 43]       # Standard experiment run seeds
FIT_SIZES = [100, 50, 20]      # Nested fitting subsets (the script guarantees 20 ⊂ 50 ⊂ 100)
MAIN_FIT_N = 100               # Number of fitting images for the main B0 experiment

MANIFEST_VERSION = "1.0"

# Datasets and categories (matching datasets/)
DATASETS = {
    "mvtec_ad": {
        "categories": ["bottle", "cable", "capsule", "screw", "tile", "wood"],
        "dev_mode": "split_train",          # Reserve 20% of train/good
    },
    "mvtec_loco": {
        "categories": ["juice_bottle", "screw_bag"],
        "dev_mode": "official_validation",  # Use official validation/good directly
    },
}

# Group scope: 6 MVTec AD categories as standard; 2 LOCO categories as the second-dataset extension
MASK_SUBDIR = "ground_truth"


# ---------------------------------------------------------------------------
# Basic utilities
# ---------------------------------------------------------------------------
def log(msg):
    print(f"[make_manifests] {msg}", flush=True)


def sha256_file(path, bufsize=1 << 20):
    """Compute one file's SHA-256 with a 1 MB buffer."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(bufsize)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().upper()


def list_png(directory):
    """List nonrecursive .png files as absolute paths in lexicographic filename order."""
    if not directory.is_dir():
        return []
    return sorted([p for p in directory.iterdir() if p.is_file() and p.suffix == ".png"],
                  key=lambda p: p.name)


def rel(datasets_root, path):
    """POSIX path relative to the datasets root, portable across platforms and HPC."""
    return Path(path).resolve().relative_to(Path(datasets_root).resolve()).as_posix()


def load_inventory(datasets_root):
    """Read datasets/file_inventory.csv and return the relative_path -> sha256 mapping."""
    inv_path = Path(datasets_root) / "file_inventory.csv"
    table = {}
    if not inv_path.is_file():
        log("file_inventory.csv was not found; computing hashes directly will take longer.")
        return table, False
    with open(inv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            table[row["relative_path"]] = row["sha256"].strip().upper()
    log(f"Loaded hash inventory {inv_path.name}: {len(table)} entries.")
    return table, True


def make_entry(datasets_root, path, inventory, rehash, missing_hashes):
    """Build a {path, sha256} entry, preferring inventory hashes and computing missing ones."""
    r = rel(datasets_root, path)
    if rehash or r not in inventory:
        digest = sha256_file(path)
        missing_hashes.append(r)
    else:
        digest = inventory[r]
    return {"path": r, "sha256": digest}


# ---------------------------------------------------------------------------
# Mask path mapping
# ---------------------------------------------------------------------------
def masks_for_ad(datasets_root, cat_root, defect, image_path):
    """MVTec AD: test/<defect>/<id>.png ↔ ground_truth/<defect>/<id>_mask.png."""
    mask = cat_root / MASK_SUBDIR / defect / f"{image_path.stem}_mask.png"
    return [mask] if mask.is_file() else []


def masks_for_loco(datasets_root, cat_root, defect, image_path):
    """LOCO: test/<defect>/<id>.png ↔ ground_truth/<defect>/<id>/000.png[,001.png...]."""
    mask_dir = cat_root / MASK_SUBDIR / defect / image_path.stem
    if not mask_dir.is_dir():
        return []
    return sorted([p for p in mask_dir.iterdir() if p.is_file() and p.suffix == ".png"],
                  key=lambda p: p.name)


# ---------------------------------------------------------------------------
# Build one category
# ---------------------------------------------------------------------------
def build_category(dataset, category, datasets_root, inventory, rehash):
    cfg = DATASETS[dataset]
    cat_root = Path(datasets_root) / dataset / category
    missing_hashes = []
    errors = []

    # --- All official train/good images ---
    train_all = list_png(cat_root / "train" / "good")
    if not train_all:
        raise RuntimeError(f"{dataset}/{category}: train/good is empty; check the dataset path.")

    # --- Development set and fitting pool ---
    if cfg["dev_mode"] == "split_train":
        n_dev = int(round(len(train_all) * DEV_RATIO + 1e-9))
        order = list(train_all)
        random.Random(SPLIT_SEED).shuffle(order)  # Use the same fixed seed for each category for reproducibility
        dev_abs = sorted(order[:n_dev], key=lambda p: p.name)
        fit_abs = sorted(order[n_dev:], key=lambda p: p.name)
        dev_note = f"{DEV_RATIO:.0%} of train/good (split seed={SPLIT_SEED})"
    elif cfg["dev_mode"] == "official_validation":
        dev_abs = list_png(cat_root / "validation" / "good")
        fit_abs = train_all
        if not dev_abs:
            raise RuntimeError(f"{dataset}/{category}: validation/good is empty.")
        dev_note = "Official validation/good (not split from train)"
    else:
        raise ValueError(cfg["dev_mode"])

    if len(fit_abs) < MAIN_FIT_N:
        errors.append(f"The fitting pool has only {len(fit_abs)} images; the main experiment requires {MAIN_FIT_N}.")

    # --- Official test set (locked)---
    test_dir = cat_root / "test"
    good_abs = list_png(test_dir / "good")
    mask_fn = masks_for_ad if dataset == "mvtec_ad" else masks_for_loco
    anomalies = []
    defect_dirs = sorted([d for d in test_dir.iterdir()
                          if d.is_dir() and d.name != "good"], key=lambda d: d.name)
    for d in defect_dirs:
        for img in list_png(d):
            mask_abs = mask_fn(datasets_root, cat_root, d.name, img)
            if not mask_abs:
                errors.append(f"Anomaly image has no mask: {rel(datasets_root, img)}")
            anomalies.append({
                "path": rel(datasets_root, img),
                "sha256": (sha256_file(img) if rehash or rel(datasets_root, img) not in inventory
                           else inventory[rel(datasets_root, img)]),
                "label": 1,
                "defect_type": d.name,
                "masks": [make_entry(datasets_root, m, inventory, rehash, missing_hashes)
                          for m in mask_abs],
            })
    anomalies.sort(key=lambda x: (x["defect_type"], x["path"]))

    # --- Build entries with hashes---
    dev_entries = [make_entry(datasets_root, p, inventory, rehash, missing_hashes) for p in dev_abs]
    fit_entries = [make_entry(datasets_root, p, inventory, rehash, missing_hashes) for p in fit_abs]
    good_entries = [make_entry(datasets_root, p, inventory, rehash, missing_hashes) for p in good_abs]
    # Add anomaly images to missing_hashes if their hashes were computed above
    for a in anomalies:
        if rehash or a["path"] not in inventory:
            if a["path"] not in missing_hashes:
                missing_hashes.append(a["path"])

    # --- Nested fitting subsets for the three run seeds ---
    fit_paths = [e["path"] for e in fit_entries]
    runs = {}
    for seed in RUN_SEEDS:
        shuffled = list(fit_paths)
        random.Random(seed).shuffle(shuffled)
        picks = {MAIN_FIT_N: shuffled[:MAIN_FIT_N]}
        for n in FIT_SIZES:
            if n not in picks:
                picks[n] = shuffled[:n]
        runs[str(seed)] = {str(n): picks[n] for n in FIT_SIZES}

    # --- Consistency checks ---
    dev_set = {e["path"] for e in dev_entries}
    fit_set = set(fit_paths)
    test_set = {e["path"] for e in good_entries} | {a["path"] for a in anomalies}
    if dev_set & fit_set:
        errors.append("The development set and fitting pool overlap!")
    if (dev_set | fit_set) & test_set:
        errors.append("The training and official test sets overlap!")
    for seed in RUN_SEEDS:
        s20, s50, s100 = (set(runs[str(seed)][str(n)]) for n in (20, 50, 100))
        if not (s20 <= s50 <= s100):
            errors.append(f"seed={seed}: the 20⊂50⊂100 nested-subset relation does not hold!")
        if len(s100) != MAIN_FIT_N:
            errors.append(f"seed={seed}: main experiment sample count != {MAIN_FIT_N}.")

    # --- split_hash (deterministic hash of the split itself for run evidence)---
    canonical = json.dumps({
        "manifest_version": MANIFEST_VERSION,
        "dataset": dataset,
        "category": category,
        "dev_mode": cfg["dev_mode"],
        "split_seed": SPLIT_SEED,
        "dev_ratio": DEV_RATIO,
        "run_seeds": RUN_SEEDS,
        "fit_sizes": FIT_SIZES,
        "dev": sorted(dev_set),
        "fit_pool": sorted(fit_set),
        "test_good": sorted(e["path"] for e in good_entries),
        "test_anomaly": sorted(a["path"] for a in anomalies),
        "masks": sorted(m["path"] for a in anomalies for m in a["masks"]),
    }, sort_keys=True, ensure_ascii=False)
    split_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "dataset": dataset,
        "category": category,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "split_seed": SPLIT_SEED,
            "dev_ratio": DEV_RATIO,
            "dev_mode": cfg["dev_mode"],
            "dev_note": dev_note,
            "run_seeds": RUN_SEEDS,
            "fit_sizes": FIT_SIZES,
            "main_fit_n": MAIN_FIT_N,
            "image_size": 256,
            "backbone": "ResNet18 (ImageNet pretrain)",
        },
        "split_hash": split_hash,
        "counts": {
            "train_good_total": len(train_all),
            "dev_normal": len(dev_entries),
            "fit_pool": len(fit_entries),
            "test_good": len(good_entries),
            "test_anomaly": len(anomalies),
            "defect_types": len(defect_dirs),
            "masks": sum(len(a["masks"]) for a in anomalies),
        },
        "dev": dev_entries,
        "fit_pool": fit_entries,
        "test": {
            "good": [dict(e, label=0) for e in good_entries],
            "anomalies": anomalies,
        },
        "runs": runs,
        "notes": [
            "Paths are relative to the datasets root; resolve them with --datasets-root at runtime.",
            "runs contains paths to fitting images; their hashes are recorded in fit_pool.",
            "test/ground_truth is locked and must not be used for threshold or model selection.",
            "Report logical_anomalies and structural_anomalies metrics separately for LOCO.",
        ],
    }
    overview_row = {
        "dataset": dataset,
        "category": category,
        "dev_mode": cfg["dev_mode"],
        "train_good_total": len(train_all),
        "dev_normal": len(dev_entries),
        "fit_pool": len(fit_entries),
        "test_good": len(good_entries),
        "test_anomaly": len(anomalies),
        "defect_types": len(defect_dirs),
        "masks": sum(len(a["masks"]) for a in anomalies),
        "fit_n100": len(runs[str(RUN_SEEDS[0])]["100"]),
        "fit_n50": len(runs[str(RUN_SEEDS[0])]["50"]),
        "fit_n20": len(runs[str(RUN_SEEDS[0])]["20"]),
        "split_hash": split_hash,
    }
    return manifest, overview_row, errors, missing_hashes


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="CA6129 consistent data splits and manifest generation")
    parser.add_argument("--datasets-root", default=str(here / ".." / ".." / "datasets"),
                        help="Path to the datasets directory (default: ../../datasets)")
    parser.add_argument("--out-dir", default=str(here / ".." / ".." / "manifests"),
                        help="Manifest output directory (default: ../../manifests)")
    parser.add_argument("--rehash", action="store_true",
                        help="Ignore file_inventory.csv and recompute SHA-256 for every file")
    args = parser.parse_args()

    datasets_root = Path(args.datasets_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    if not datasets_root.is_dir():
        log(f"Error: datasets directory not found: {datasets_root}")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory, have_inv = load_inventory(datasets_root)
    if args.rehash:
        log("--rehash: recomputing SHA-256 for every file.")

    index = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "split_seed": SPLIT_SEED,
            "dev_ratio": DEV_RATIO,
            "run_seeds": RUN_SEEDS,
            "fit_sizes": FIT_SIZES,
            "main_fit_n": MAIN_FIT_N,
        },
        "datasets": [],
    }
    overview_rows = []
    total_errors = []
    total_rehashed = 0

    for dataset, cfg in DATASETS.items():
        for category in cfg["categories"]:
            manifest, row, errors, rehashed = build_category(
                dataset, category, datasets_root, inventory, args.rehash)
            total_rehashed += len(rehashed)
            total_errors.extend([f"{dataset}/{category}: {e}" for e in errors])
            out_path = out_dir / f"manifest_{dataset}_{category}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            index["datasets"].append({
                "dataset": dataset, "category": category,
                "file": out_path.name,
                "counts": manifest["counts"],
                "split_hash": manifest["split_hash"],
            })
            overview_rows.append(row)
            log(f"{dataset}/{category}: dev={row['dev_normal']} "
                f"fit={row['fit_pool']} good={row['test_good']} "
                f"anom={row['test_anomaly']} masks={row['masks']} -> {out_path.name}")

    # Global split_hash (category aggregate for overall reproducibility checks)
    index["global_split_hash"] = hashlib.sha256(
        json.dumps([d["split_hash"] for d in index["datasets"]],
                   sort_keys=True).encode("utf-8")).hexdigest().upper()
    with open(out_dir / "manifest_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    cols = ["dataset", "category", "dev_mode", "train_good_total", "dev_normal",
            "fit_pool", "test_good", "test_anomaly", "defect_types", "masks",
            "fit_n100", "fit_n50", "fit_n20", "split_hash"]
    with open(out_dir / "splits_overview.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(overview_rows)

    # Console overview
    log("")
    log("Split overview by category (fitting subsets shown for seed 17):")
    colw = 12
    header = f"{'dataset':<{colw}}{'category':<{colw}}{'dev':>4}{'fit':>5}{'good':>5}{'anom':>5}{'masks':>6}"
    print(header)
    for r in overview_rows:
        print(f"{r['dataset']:<{colw}}{r['category']:<{colw}}{r['dev_normal']:>4}"
              f"{r['fit_pool']:>5}{r['test_good']:>5}{r['test_anomaly']:>5}{r['masks']:>6}")

    log("")
    if total_errors:
        log("Validation found issues:")
        for e in total_errors:
            print("  [ERROR]", e)
        sys.exit(2)
    log("All consistency checks passed: development/fitting/test sets are disjoint; 20⊂50⊂100 subsets are nested; all masks are present.")
    log(f"Global split hash (global_split_hash) = {index['global_split_hash']}")
    if total_rehashed:
        log(f"Computed missing hashes directly for {total_rehashed} files.")
    log(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()
