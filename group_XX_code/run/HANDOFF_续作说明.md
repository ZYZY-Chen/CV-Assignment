# 交接说明（续作）

上一份 `run/HANDOFF_中断说明.md` 停在 2026-10-18 凌晨：B0 只完成了 bottle、cable、capsule 和 screw 的 PatchCore，机器因 RTX 5050 蓝屏三次。本文件接在那之后。以本文件为准；旧文件只保留当时的现场。

仓库：https://github.com/ZYZY-Chen/CV-Assignment  
代码根目录：`group_XX_code/`  
环境：`D:\Anaconda\envs\ca6129-ad`（torch 2.11.0+cu128，但本机实验不要用 CUDA）

## 现在到哪一步

手册标准版 62 次 MVTec 拟合，加上 LOCO 的 4 次 B0，一共 **66 次全部有 `SUCCESS`**。汇总在：

- `run/results_summary.csv`
- `run/results_summary.json`

每次运行的目录是 `run/results/<run_id>/`，里面有 `config.yaml`、`metrics.json`、`evidence.json`、`predictions.npz`、`SUCCESS`。前 7 次 B0 另外保留了改分数之前的 `metrics_grid16.json`。

图像分数已经改成手册要求的做法：16×16 异常图先双线性放到 **256×256**，再算 max / top 0.1% / top 1% / top 5%。`top 1%` 是预注册的 I1。像素指标仍是每张图恢复到原图分辨率后计算，不经过这四个聚合规则。

### 三种子、六类宏平均（R0，N=100）

| 方法 | max 图像 AUROC | top 1% 图像 AUROC |
|---|---:|---:|
| PatchCore | 0.9215 ± 0.0094 | 0.9296 ± 0.0071 |
| PaDiM | 0.8950 ± 0.0083 | 0.9017 ± 0.0061 |

像素 AUROC 的六类宏平均大约是 0.956，两种方法几乎一样。只有一个 seed 时不要写成均值±标准差；`scripts/aggregate_results.py` 已经按这个规则打印。

### B0，seed 17，N=100（图像分数是 256×256）

| 类别 | PatchCore max / top1% / 像素 | PaDiM max / top1% / 像素 |
|---|---|---|
| bottle | 1.000 / 1.000 / 0.980 | 0.998 / 0.998 / 0.983 |
| cable | 0.906 / 0.942 / 0.962 | 0.802 / 0.840 / 0.962 |
| capsule | 0.884 / 0.898 / 0.982 | 0.826 / 0.868 / 0.984 |
| screw | 0.732 / 0.736 / 0.967 | 0.742 / 0.704 / 0.970 |
| tile | 0.962 / 0.977 / 0.924 | 0.957 / 0.985 / 0.910 |
| wood | 0.991 / 0.991 / 0.922 | 0.993 / 0.991 / 0.922 |

screw 的图像分数低、像素分数高。cable 上 PatchCore 明显好于 PaDiM。

### 消融（cable 与 screw 的宏平均，除非另行写出）

- 少样本 F1，max 图像 AUROC：N=20 时 PatchCore 0.734、PaDiM 0.600；N=50 时 0.760、0.696；N=100 时 0.819、0.772。
- 把 5% coreset 换成等量随机采样（C1，seed 17）：cable 的 PatchCore max 从 0.906 降到 0.662，screw 从 0.732 降到 0.529。
- PaDiM 维度（H1）：cable 上 50/100/200 维的 max 约为 0.766 / 0.802 / 0.837。基线是 100 维。
- PaDiM 层（C2）：cable 上只用 layer3 的 max 是 0.860，高于三层基线 0.802；screw 上三层基线 0.742 更好，layer2+3 和仅 layer3 都是 0.705。证据里的 `method_detail.layers` 和 `feature_maps` 记录了实际用到的层。

### LOCO（必须分开报，不要只引用混在一起的 AUROC）

正常图分别对逻辑异常、结构异常。下表是图像 AUROC（max）/ 像素 AUROC。

| 类别 | 方法 | 逻辑异常 | 结构异常 | 混在一起的图像 AUROC |
|---|---|---:|---:|---:|
| juice_bottle | PatchCore | 0.928 / 0.892 | 0.936 / 0.924 | 0.931 |
| juice_bottle | PaDiM | 0.886 / 0.921 | 0.840 / 0.929 | 0.868 |
| screw_bag | PatchCore | 0.540 / 0.632 | 0.721 / 0.960 | 0.608 |
| screw_bag | PaDiM | 0.516 / 0.699 | 0.664 / 0.957 | 0.571 |

screw_bag 的逻辑异常接近随机；结构异常的定位很好。混在一起的数会把这个差别抹掉。`metrics.json` 里正式分组在 `groups`。顶层的 `pixel` 是全部测试图混在一起的结果。

### 可以写进速度图的计时

`run/resource_benchmark.json`。协议：CPU、batch=1、预测前预热 20 次，拟合 / 预测 / 评估分开。预测读的是特征缓存，不含 JPEG 解码和 ResNet 前向。ResNet18 前向另测为 **0.012 秒/张**。

六类平均大约是：

| 方法 | 拟合 | 预测 | 评估 | 模型占用 |
|---|---:|---:|---:|---:|
| PatchCore | 5.4 秒 | 5.1 秒 | 17.4 秒 | 2.0 MB（记忆库 1280/25600） |
| PaDiM | 0.07 秒 | 5.3 秒 | 17.4 秒 | 10.3 MB |

`peak_rss_mb` 是**整个计时进程的累计峰值**，到后面停在约 3.5 GB，不会按类别回落。像素评估占了大头。方法之间比内存时用 `storage_mb`，不要把 3.5 GB 说成某一种方法单独的峰值。

最早几次 B0（bottle、cable、capsule，以及 screw 的 PatchCore）的 `evidence.json` 仍写着 RTX 5050。那些秒数不能和后面的 CPU 计时放进同一张图。screw 的 PaDiM 以及 tile、wood、全部消融、R0、F1、LOCO 都是 CPU。

## 本机怎么跑才不会死机

这台笔记本的 RTX 5050 在大批量 `cdist` 时蓝屏过三次（`HYPERVISOR_ERROR` / `WHEA_UNCORRECTABLE_ERROR`）。上一份交接里的 `scripts/debug_variant.py` 全记忆库运行就是诱因之一。

在这台机器上：

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:OMP_NUM_THREADS = "4"
$env:MKL_NUM_THREADS = "4"
cd group_XX_code
D:\Anaconda\envs\ca6129-ad\python.exe -u scripts\run_experiments.py --tags B0 --datasets mvtec_ad --device cpu
```

- `CUDA_VISIBLE_DEVICES` 设成空字符串时，PyTorch 仍看得到独显。必须设成 `-1`，并确认 `torch.cuda.is_available()` 为假。
- 不要运行 `scripts/debug_variant.py`，也不要在 GPU 上做全记忆库 `cdist`。
- `run.py` 在 `--device cpu` 时会把 DataLoader worker 设为 0、线程数设为 4、进程优先级设为低于正常。PatchCore 单块距离矩阵限制在 256 MB。
- 已有 `SUCCESS` 的运行会被 `run_experiments.py` 跳过。不要随便加 `--force`。
- 像素评估若再次把进程推到大约 14 GB，应停掉。LOCO 原图很大（果汁瓶 800×1600，螺丝袋 1600×1100），现在的像素 AUROC 只保留一份 float32 分数再排序，不要改回把整批原图堆成 float64。

## 过程中遇到并已经处理的问题

1. **图像分数网格。** 原来在 16×16 上做 top-q，top 0.1% 和 max 是同一个数。已改为 256×256。前 7 次用保存的 float16 异常图重算了图像指标，像素指标没变。重算脚本是 `scripts/recompute_image_scores.py`。后来的运行在保存半精度之前用 float32 打分，和这 7 次有很小的数值来源差别，写报告时可以一句带过。
2. **C2 层消融。** `compose_full_features` 曾经写死 layer1+2+3。配置只要 layer2+3 或 layer3 时，缓存里没有 layer1，报 `KeyError`。现已按 `cfg["layers"]` 拼接，缺层直接报错。C2 四次已重跑成功。
3. **LOCO 掩膜被缩成正方形。** `load_mask(size=高度)` 得到正方形，对不上 800×1600。已改为按每张图的 `(H, W)` 做最近邻缩放。同一类别里尺寸可以不同。
4. **LOCO 像素评估内存。** 一次把全部原图像素放进 scikit-learn，进程超过 14 GB 后被停掉，机器没有蓝屏。现用自写的 AUROC/AP，小样本上和 scikit-learn 一致。四个 LOCO 基线已重跑成功。
5. **汇总脚本。** 没有 LOCO 结果时按类别取行会 `StopIteration`。只有一个 seed 时会打印「均值 ± 0」。两处都已改掉。
6. **计时脚本。** `benchmark_resources.py` 曾向清单要 `n=32` 的拟合池，清单只有 20/50/100。已改为从 N=100 的池子取前 32 张测骨干。进程内存接口第一次因 64 位句柄被截断而得到 -1，已改用 `K32GetProcessMemoryInfo`。

## 仓库里有什么、没有什么

已提交：代码、配置、manifest、66 次结果、两份汇总、CPU 计时、两份交接、选题手册 PDF、环境锁定文件。bottle 的特征缓存经 Git LFS 已在仓库里（约 153 MB）。

没有提交，仍在本机 `group_XX_code/run/feature_cache/`：

- `cache_mvtec_ad_{cable,capsule,screw,tile,wood}.npz`
- `cache_mvtec_loco_{juice_bottle,screw_bag}.npz`

这些文件每个大约 200–450 MB，合计约 2 GB。`.gitignore` 忽略它们，只保留已经跟踪的 bottle 缓存。别人克隆后，除 bottle 以外要自己提取，而且必须避开独显：

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"
D:\Anaconda\envs\ca6129-ad\python.exe -u scripts\extract_features.py --all --device cpu
```

数据集在 `datasets/`，不要再提交 `datasets.zip`。课程讲义 `course project.pdf` 也没有放进仓库。

## 接下来建议做的事

实验矩阵已经够写标准版报告。不要再为了凑数重跑已有 `SUCCESS` 的拟合。

1. 图 F1–F5。速度和内存只用 `resource_benchmark.json`。热图用开发集定的统一尺度，并放失败例子，不要只放 bottle。
2. 约 6 页英文报告：Introduction、Methods、Experiments and Analysis、Conclusion。每个实验段落写控制变量、本组数字、解释、反例。论文里的数字只作背景。I1 直接用已经算好的 top 1% 列，不必再拟合。说明当前异常图已经是近邻加权分数，所以 max 就是这个图的最大值，没有再做一次额外平滑。
3. LOCO 放在泛化讨论里，逻辑异常和结构异常分开写。screw_bag 的逻辑异常是反例。
4. 贡献声明仍缺三人的姓名和学号。没有名字之前不要编造。没做的实验不要写进已完成贡献。
5. 补一份 README，让别人从新目录用 CPU 复现一次 B0 bottle。bottle 缓存已在仓库里，这一次不需要先提取其它类别。
6. 提交用的 `group_XX_code.zip` 不要包含数据集、特征缓存、虚拟环境和权重大文件。`scripts/debug_variant.py` 与 `scripts/debug_border.py` 不要放进给老师的压缩包，避免下一位同学在 GPU 上跑到全记忆库。

组内目标是 10 月 24 日，正式截止是 10 月 25 日 23:59（以手册为准）。
