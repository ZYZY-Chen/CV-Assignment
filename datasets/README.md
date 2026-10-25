# CA6129 Group Project — Dataset Notes

Download and extract the datasets using the official links:

```powershell
cd group_XX_code
python scripts/download_datasets.py --accept-license
```

See [the project README](../README.md) for an overview and license information. The expected contents after download are listed below.

Prepared on: 2026-10-17
After download, this directory contains two datasets in their original official structure (MVTec format).

## 1. Contents

| Dataset | Categories | Purpose | Size |
|---|---|---|---|
| MVTec AD (main dataset) | bottle, cable, capsule, screw, tile, wood (six categories selected in the handbook) | Main experiments (B0/H1/H2/C1/C2/F1/I1, etc.) | ≈ 2.0 GB |
| MVTec LOCO AD (second dataset) | juice_bottle, screw_bag | Cross-dataset generalization and logical anomaly analysis (B0 baseline extension) | ≈ 1.6 GB |

### MVTec AD file counts (checked against official counts)

| Category | train/good | test/good | test/all defect types | Pixel masks |
|---|---|---|---|---|
| bottle | 209 | 20 | 63 | 63 |
| cable | 224 | 58 | 92 | 92 |
| capsule | 219 | 23 | 109 | 109 |
| screw | 320 | 41 | 119 | 119 |
| tile | 230 | 33 | 84 | 84 |
| wood | 247 | 19 | 60 | 60 |

### MVTec LOCO AD file counts (checked against official counts)

| Category | train/good | validation/good | test/good | test/logical | test/structural |
|---|---|---|---|---|---|
| juice_bottle | 335 | 54 | 94 | 142 | 94 |
| screw_bag | 360 | 60 | 122 | 137 | 82 |

Pixel masks are stored in `ground_truth/logical_anomalies/` and `ground_truth/structural_anomalies/`.
Each anomalous LOCO image may have multiple masks (organized as `000/000.png, 000/001.png`), with 492 mask files in total.
`defects_config.json` maps defect names to pixel values; evaluation follows the official conventions.

## 2. Directory structure

```
datasets/
├── mvtec_ad/                      # Standard MVTec format
│   └── <category>/
│       ├── train/good/            # Normal images only (source of the fitting pool)
│       ├── test/good/             # Normal test images
│       ├── test/<defect_type>/    # Anomalous test images
│       └── ground_truth/<defect_type>/*_mask.png
├── mvtec_loco/
│   └── <category>/
│       ├── train/good/
│       ├── validation/good/       # Official normal validation set; used directly as the normal development set
│       ├── test/good/
│       ├── test/logical_anomalies/
│       ├── test/structural_anomalies/
│       └── ground_truth/{logical,structural}_anomalies/<id>/*.png
├── file_inventory.csv             # relative_path / size / SHA-256 for all 4687 files
└── README.md
```

All PNG files have been checked: all 4681 PNG headers are valid, no files are empty, and sampled resolutions match the official data
(original MVTec images range from 840 to 1024 px; do not assume a uniform size).

## 3. Sources and licenses

- MVTec AD: https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads
  (the complete official package `mvtec_anomaly_detection.tar.xz` was downloaded locally through the Hugging Face mirror `micguida1/mvtech_anomaly_detection`; only the six categories were extracted, without modification)
- MVTec LOCO AD: https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads
  (the official per-category packages for juice_bottle and screw_bag were downloaded directly through a browser)
- License: both datasets use **CC BY-NC-SA 4.0**, which permits academic use for this course; cite the datasets in the report;
  **Do not include the datasets in group_XX_code.zip or redistribute them through a cloud drive** (the course rules also prohibit this).

> Note: the official mydrive.ch links return 404 to curl/script requests (only actual browsers are allowed).
> To reproduce the download, open the official links in a browser or find a complete mirror on Hugging Face.
> Caution: the `Rafa612/mvtec_loco` mirror on Hugging Face is incomplete (validation is missing and only about half of train is present).
> This directory ultimately used the official packages; the counts in the tables above are authoritative.

## 4. Integration with the experiment protocol

1. **MVTec AD**: following the handbook, select 20% of `train/good` as the normal development set using split seed 20261017;
   `test/` and `ground_truth/` remain locked and are excluded from the development set. Each of the six categories has at least 209 training images, leaving enough to select a fitting subset of 100.
2. **MVTec LOCO**: use the official `validation/good` (54/60 images) directly as the normal development set, without splitting train;
   report logical and structural metrics **separately** during evaluation (the two test subdirectories are already separate), which is a central feature of this dataset.
3. LOCO `ground_truth` uses one folder per image, containing one or more masks;
   evaluation code must not assume one mask file per image in a flat directory.
4. Preprocessing uses RGB conversion, resizing to 256×256 and ImageNet normalization; anomaly maps are resized back to the original image resolution using bilinear interpolation;
   **always use nearest-neighbor interpolation and binarization for masks; never use bilinear interpolation**.
5. In Anomalib, use the `MVTec`/`MVTecAD` datamodule for MVTec AD and the `MVTecLOCO` datamodule for LOCO;
   point their roots to `mvtec_ad` and `mvtec_loco`, respectively; continue creating project manifests as required by the handbook;
   do not use `val_split_mode=same_as_test`.

## 5. Integrity checks

- `file_inventory.csv`: dataset, kind(image/mask/other), relative_path, size_bytes, sha256.
  A total of 4687 rows (MVTec 2709 + LOCO 1978).
- Verification (PowerShell): run `Get-FileHash -Algorithm SHA256 <file>` and compare the result with the CSV.
- Manifests for formal runs should build on this inventory and record the files and hashes actually used by each experiment split.
