# 第三方资源与版权声明（THIRD_PARTY_NOTICES）

本项目代码为小组成员独立实现，未复制 Anomalib 等第三方框架的源代码；
PaDiM / PatchCore 均依据原论文复现。以下为数据、模型权重与开源库的声明。

## 1. 数据集（随报告引用，不打包进代码 zip）

- **MVTec Anomaly Detection Dataset (MVTec AD)**，版本 v1.1（2024 快照）
  - 版权：MVTec Software GmbH
  - 许可：**Creative Commons Attribution-NonCommercial-ShareAlike 4.0
    International（CC BY-NC-SA 4.0）**
  - 引用：Paul Bergmann, Kilian Batzner, et al. *The MVTec Anomaly Detection
    Dataset for Unsupervised Anomaly Detection.* 2019/2021.
  - 下载：https://www.mvtec.com/company/research/datasets/mvtec-ad

- **MVTec LOCO Anomaly Detection Dataset (LOCO)**
  - 版权：MVTec Software GmbH
  - 许可：**CC BY-NC-SA 4.0**
  - 引用：Jan-Aike Lohweg, Johannes Heidemann, et al. *The MVTec LOCO Dataset:
    Detecting Logical Anomalies.*（MVTec LOCO 数据集论文）
  - 下载：https://www.mvtec.com/company/research/datasets/mvtec-loco

数据集仅用于本课程非营利学术实验；报告中保留上述署名与许可说明。

## 2. 预训练模型权重

- **ResNet18（ImageNet-1K 预训练）**：由 torchvision 自动下载
  - 模型论文：He et al., *Deep Residual Learning for Image Recognition*, CVPR 2016
  - torchvision 许可：BSD 3-Clause；权重遵循 ImageNet 发布条款
  - 本项目不将权重打包进提交物，首次运行自动下载并缓存

## 3. 开源软件依赖

| 库 | 版本 | 许可 |
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

## 4. 方法引用（报告参考文献必须包含）

- Thomas Defard et al., *PaDiM: A Patch Distribution Modeling Framework for
  Anomaly Detection and Segmentation*, ICPR Workshops 2021.
- Karsten Roth et al., *Towards Total Recall in Industrial Anomaly Detection*,
  CVPR 2022（PatchCore）。
