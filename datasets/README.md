# CA6129 小组项目 — 数据集说明

图片不在 Git 仓库里。按官方链接下载并解压：

```powershell
cd group_XX_code
python scripts/download_datasets.py --accept-license
```

说明和许可见 `group_XX_code/README.md`。下面是下载完成后应有的内容。

整理日期：2026-10-17
本目录在下载后包含两个数据集，均为官方原始结构（MVTec 格式）。

## 1. 内容总览

| 数据集 | 类别 | 用途 | 体积 |
|---|---|---|---|
| MVTec AD（主数据集） | bottle, cable, capsule, screw, tile, wood（手册选定 6 类） | 主实验（B0/H1/H2/C1/C2/F1/I1 等） | ≈ 2.0 GB |
| MVTec LOCO AD（第二数据集） | juice_bottle, screw_bag | 跨数据集泛化 + 逻辑异常分析（B0 基线扩展） | ≈ 1.6 GB |

### MVTec AD 文件统计（已核对官方数量）

| 类别 | train/good | test/good | test/各缺陷 | 像素掩膜 |
|---|---|---|---|---|
| bottle | 209 | 20 | 63 | 63 |
| cable | 224 | 58 | 92 | 92 |
| capsule | 219 | 23 | 109 | 109 |
| screw | 320 | 41 | 119 | 119 |
| tile | 230 | 33 | 84 | 84 |
| wood | 247 | 19 | 60 | 60 |

### MVTec LOCO AD 文件统计（已核对官方数量）

| 类别 | train/good | validation/good | test/good | test/logical | test/structural |
|---|---|---|---|---|---|
| juice_bottle | 335 | 54 | 94 | 142 | 94 |
| screw_bag | 360 | 60 | 122 | 137 | 82 |

像素掩膜位于 `ground_truth/logical_anomalies/` 与 `ground_truth/structural_anomalies/`，
LOCO 每张异常图可能有多个掩膜（按 `000/000.png, 000/001.png` 组织），共 492 个掩膜文件。
`defects_config.json` 包含缺陷名与像素值映射，评估时按官方口径使用。

## 2. 目录结构

```
datasets/
├── mvtec_ad/                      # 标准 MVTec 格式
│   └── <category>/
│       ├── train/good/            # 仅正常图（拟合池来源）
│       ├── test/good/             # 正常测试图
│       ├── test/<defect_type>/    # 异常测试图
│       └── ground_truth/<defect_type>/*_mask.png
├── mvtec_loco/
│   └── <category>/
│       ├── train/good/
│       ├── validation/good/       # 官方无异常验证集，可直接作为"正常开发集"
│       ├── test/good/
│       ├── test/logical_anomalies/
│       ├── test/structural_anomalies/
│       └── ground_truth/{logical,structural}_anomalies/<id>/*.png
├── file_inventory.csv             # 全部 4687 个文件的 relative_path / size / SHA-256
└── README.md
```

所有 PNG 已校验：4681 张 PNG 文件头全部合法、无 0 字节文件，抽查分辨率与官方一致
（MVTec 原图 840–1024 px 不等，不要假定统一尺寸）。

## 3. 来源与许可

- MVTec AD：https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads
  （本机经 HuggingFace 镜像 `micguida1/mvtech_anomaly_detection` 的官方完整包 `mvtec_anomaly_detection.tar.xz` 下载后只解出 6 类，未做任何修改）
- MVTec LOCO AD：https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads
  （juice_bottle、screw_bag 两个官方逐类包，浏览器直接下载）
- 许可：均为 **CC BY-NC-SA 4.0**，课程学术使用允许；报告中须引用数据集；
  **禁止把数据集打进 group_XX_code.zip 或转存网盘对外分发**（课程规则也禁止）。

> 备注：官方 mydrive.ch 链接对 curl/脚本请求返回 404（仅放行真实浏览器），
> 复现下载时请用浏览器打开官方链接，或在 HuggingFace 上找完整镜像。
> 注意：HuggingFace 上 `Rafa612/mvtec_loco` 镜像不完整（缺 validation 且 train 约一半），
> 本目录最终使用的是官方包，数量以上表为准。

## 4. 接入你们实验协议的注意事项

1. **MVTec AD**：按手册从 `train/good` 以 split seed 20261017 抽 20% 作正常开发集；
   `test/` 与 `ground_truth/` 全部锁定，不进开发集。6 类 train 均 ≥209 张，抽 100 张拟合池无压力。
2. **MVTec LOCO**：直接用官方 `validation/good`（54/60 张）作为正常开发集，无需再从 train 切分；
   评估时 logical 与 structural 必须**分开报指标**（两个 test 子目录天然分开），这是该数据集的核心价值。
3. LOCO 的 `ground_truth` 是"每图一个文件夹、内含一个或多个掩膜"，
   写评估代码时不要假设一张图对应一个平铺 mask 文件。
4. 预处理统一 RGB、resize 256×256、ImageNet 归一化；异常图双线性恢复到原图分辨率，
   **掩膜一律最近邻/二值处理，严禁双线性插值**。
5. Anomalib 中 MVTec AD 用 `MVTec`/`MVTecAD` datamodule、LOCO 用 `MVTecLOCO` datamodule，
   根目录分别指向 `mvtec_ad` 与 `mvtec_loco`；继续按手册要求自建 manifest，
   不要使用 `val_split_mode=same_as_test`。

## 5. 完整性校验

- `file_inventory.csv`：dataset, kind(image/mask/other), relative_path, size_bytes, sha256。
  共 4687 行（MVTec 2709 + LOCO 1978）。
- 校验方法（PowerShell）：`Get-FileHash -Algorithm SHA256 <文件>` 后与 CSV 比对。
- 正式 run 的 manifest 应在本清单基础上按实验 split 记录实际用到的文件与哈希。
