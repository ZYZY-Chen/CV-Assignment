# CA6129 工业异常检测小组作业

比较 PaDiM 和 PatchCore。实验代码在这个目录，图片不放进 Git 仓库。

## V2 实验规范与历史结果

修正后的实验规范已冻结为 V2，说明见 [EXPERIMENT_PROTOCOL_V2.md](docs/EXPERIMENT_PROTOCOL_V2.md)，机器可读配置见 [protocol_v2.json](configs/protocol_v2.json)。现有 66 次运行登记为 V1 历史结果，文件校验值见 [legacy_v1_inventory.json](run/legacy_v1_inventory.json)。

后续正式实验使用 TC2 GPU 集群，V2 输出约定在 `run/v2/` 下。当前运行代码尚未接入 V2 协议及输出目录；模型、缓存和作业流程将在对应后续项确认方案后修正和验证，指标修正的独立验收已在第 3 项完成。V1 结果及其 SUCCESS 标记不能作为 V2 完成依据。

## TC2 GPU 环境与输入核验

第 2 项的准备和验收说明见 [TC2_SETUP_V2.md](docs/TC2_SETUP_V2.md)，已核实设置及验收状态见 [tc2_setup.json](configs/tc2_setup.json)。核验使用 [check_setup_v2.py](scripts/check_setup_v2.py) 及 [SLURM 入口](scripts/slurm/check_setup_v2.sh)，记录保存到 `run/setup_v2/`。

GPU 检查必须在计算节点作业内运行。核验工具只检查已准备的输入和环境。实际集群环境已通过检查并导出 [environment-tc2.yml](environment-tc2.yml) 和 [requirements-tc2-lock.txt](requirements-tc2-lock.txt)，复建时结合准备说明中的官方 cu128 包源和安装顺序使用。现有 Windows/CUDA 依赖文件仍保留为历史记录。

第 2 项已于 2026-10-19 完成：TC2N01 的最终联合验收作业 43950 为 COMPLETED / 0:0，`step_2_complete=true`。3650 张图片及 1019 个掩膜的冻结哈希全部匹配，指定权重、CUDA FP32 运算和 ResNet18 三层特征检查均通过。实际环境为 NVIDIA A40、驱动 570.148.08、glibc 2.34、Python 3.10.22、torch 2.11.0+cu128 / torchvision 0.26.0+cu128。完整状态见 [第 2 项验收记录](run/setup_v2/step2_20261019_060542/setup_status.json)。

经用户确认的准备流程使用独立的 [环境准备脚本](scripts/prepare_tc2_environment_v2.sh)、[输入准备脚本](scripts/prepare_tc2_inputs_v2.py)、[硬件短作业](scripts/slurm/probe_hardware_v2.sh) 和 [准备作业入口](scripts/slurm/prepare_tc2_v2.sh)。AD 采用指定 Hugging Face 完整包的固定版本及哈希，只提取六类；LOCO 两类及权重继续使用官方来源。本机操作及日志回收见准备说明第 6.4、6.7 节。SLURM 作业必须从核实后的准备目录提交。

## V2 指标修正与第 3 项验收

第 3 项方案已获用户确认，说明见 [METRICS_V2.md](docs/METRICS_V2.md)。[metric_core.py](src/metric_core.py) 实现同分阈值分组的精确 AUROC/AP，[evaluate.py](src/evaluate.py) 补齐正常开发集阈值、输入检查和 LOCO 分组；现有结果字段保留，新增 `metric_policy.version=v2_tie_grouped` 标识。评价兼容原四种图像分数及后续传入的 native，模型分数的生成仍由后续项实现。

第 3 项已于 2026-10-19 完成。本地 9 项 NumPy 核心检查通过；TC2N01 的 CPU 验收作业 43956 为 COMPLETED / 0:0，24 项完整测试全部通过，`step_3_complete=true`。81 组 scikit-learn 对照的 AUROC/AP 最大绝对误差分别为 1.11e-16 / 2.22e-16，低于 1e-12 上限。回收归档的 100 份文件、五份源文件指纹和修改范围均已独立核验。最终状态见 [第 3 项验收记录](run/validation_v2/step3_20261019_081534/setup_status.json)，完整方案、命令和证据说明见指标说明；无需重复提交验收作业。

## 数据集

只用 MVTec AD 的 bottle、cable、capsule、screw、tile、wood，以及 MVTec LOCO 的 juice_bottle、screw_bag。许可是 CC BY-NC-SA 4.0，仅限非商业用途。

官方下载页：

- MVTec AD：https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads
- MVTec LOCO：https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads

下面保留 V1 旧下载器用法。它使用官方旧直链，部分链接已返回 404；V2 输入准备按上面的 TC2 说明执行，已验收的数据位于远端准备目录的 `datasets/`。旧命令默认解压到本机上一级 `datasets/`：

```powershell
python scripts/download_datasets.py --accept-license
```

本机已经有图片时会跳过。下载完成后的目录是：

```
datasets/
├── mvtec_ad/<category>/
└── mvtec_loco/<category>/
```

## V1 历史用法：在本机 CPU 复现一次 B0

以下保留旧版示例，它写入 V1 结果目录，不是 V2 集群执行入口。

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"
python run.py --config configs/b0_patchcore.yaml --dataset mvtec_ad --category bottle --device cpu
```

这台笔记本的独显在大块距离计算时蓝屏过，实验请加 `--device cpu`，并把 `CUDA_VISIBLE_DEVICES` 设为 `-1`。进展、已知问题和计时见 `run/HANDOFF_续作说明.md`。
