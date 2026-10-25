# Third-Party Resources and Copyright Notices (THIRD_PARTY_NOTICES)

The project code was independently implemented by group members, without copying source code from Anomalib or other third-party frameworks;
PaDiM and PatchCore were implemented from their original papers. The following notices cover datasets, model weights and open-source libraries.

## 1. Datasets (to be cited in the report)

- **MVTec Anomaly Detection Dataset (MVTec AD)**, version v1.1 (2024 snapshot)
  - Copyright: MVTec Software GmbH
  - License: **Creative Commons Attribution-NonCommercial-ShareAlike 4.0
    International (CC BY-NC-SA 4.0)**
  - Citation: Paul Bergmann, Kilian Batzner, et al. *The MVTec Anomaly Detection
    Dataset for Unsupervised Anomaly Detection.* 2019/2021.
  - Download: https://www.mvtec.com/company/research/datasets/mvtec-ad

- **MVTec LOCO Anomaly Detection Dataset (LOCO)**
  - Copyright: MVTec Software GmbH
  - License: **CC BY-NC-SA 4.0**
  - Citation: Jan-Aike Lohweg, Johannes Heidemann, et al. *The MVTec LOCO Dataset:
    Detecting Logical Anomalies.* (MVTec LOCO dataset paper)
  - Download: https://www.mvtec.com/company/research/datasets/mvtec-loco

The datasets are used only for nonprofit academic experiments in this course. The report retains the attribution and license notices above.

## 2. Pretrained model weights

- **ResNet18 (pretrained on ImageNet-1K)**: downloaded automatically by torchvision
  - Model paper: He et al., *Deep Residual Learning for Image Recognition*, CVPR 2016
  - torchvision license: BSD 3-Clause; the weights are subject to the ImageNet release terms
  - The project excludes weights from the submission; they are downloaded and cached automatically on the first run

## 3. Open-source dependencies

| Library | Version | License |
|---|---|---|
| PyTorch (torch) | 2.11.0+cu128 | BSD 3-Clause |
| torchvision | 0.26.0+cu128 | BSD 3-Clause |
| NumPy | 1.26.4 | BSD 3-Clause |
| SciPy | 1.12.0 | BSD 3-Clause |
| scikit-learn | 1.7.2 | BSD 3-Clause |
| Pillow | 12.3.0 | HPND/MIT-CMU |
| pandas | 2.2.3 | BSD 3-Clause |
| matplotlib | 3.10.9 | PSF/BSD |
| PyYAML | 6.0.3 | MIT |
| tqdm | 4.70.1 | MPL-2.0/MIT |

## 4. Method references

- Thomas Defard et al., *PaDiM: A Patch Distribution Modeling Framework for
  Anomaly Detection and Segmentation*, ICPR Workshops 2021.
- Karsten Roth et al., *Towards Total Recall in Industrial Anomaly Detection*,
  CVPR 2022 (PatchCore).
