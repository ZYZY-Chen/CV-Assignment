# 第 3 项：评价指标修正与对照验收

用户已确认“确认执行第3项修改”。本方案落实已冻结的 protocol_v2.json，不修改协议或划分。第 3 项已于 2026-10-19 完成：本地核心检查和 TC2 作业 43956 的完整对照验收均通过，回收文件、源代码指纹与修改范围核验通过。

## 1 已确认的修正

1. 图像和像素的 AUROC 对正负样本同分对计半分；AP 采用同分阈值分组后的召回增量加权 precision，不使用 PR 曲线梯形面积。完全同分时 AUROC=0.5、AP=正样本占比，且结果不依赖输入顺序。
2. 像素保留原图全部像素及 FP32 连续分数，正常图使用零掩膜，多掩膜取并集；连续图双线性恢复、align_corners=False，掩膜只用最近邻。指标核进行一次精确排序，并分块统计同分组，正确合并跨块同分；不量化分数、不抽样像素、不创建全量 float64 分数或累计数组。计数使用整数、指标累计使用 float64。
3. 阈值只从对应正常开发分数计算第 95 百分位，显式使用 NumPy method=linear，测试判异常条件为 score > threshold。验证开发样本全正常、开发与测试路径不重叠、所有分数/标签/异常图数量匹配。
4. 空输入、非法或缺类标签、NaN/Inf、维度及尺寸错误明确报错；不输出不可解释的 NaN 或替代值。正式图像与像素二分类评价均需正常和异常样本。异常条目必须提供掩膜，正常条目不得携带异常掩膜。
5. LOCO 的正常对逻辑异常、正常对结构异常分别计算；识别到 LOCO 分组时，缺正常、缺任一异常组或夹杂其他异常组均报错。顶层 pooled 结果保留为辅助输出，正式口径仍为 groups。
6. 保留现有指标字段，增加 metric_policy 标识；接受开发和测试中完全相同的合法评分规则集合，兼容原四种规则与后续传入的 native。分数生成不属于本项。

## 2 文件及边界

- 新增 src/metric_core.py：仅依赖 NumPy 的指标核心及数组检查。
- 修改 src/evaluate.py：接入核心，补齐阈值、输入、分组检查及口径元数据。
- 新增 tests/test_metrics_v2.py：可独立运行的核心检查、scikit-learn 对照和合成图像/掩膜测试，使用标准库 unittest，无新增安装依赖。
- 新增 scripts/slurm/check_metrics_v2.sh：TC2 计算节点 CPU 验收入口。
- 修改本机 output/tc2_setup_v2.ps1：新增 CheckMetrics 动作，限定上传指标核心、评价模块、测试、CPU 入口以及现有 data.py 的只读副本；Collect 增加 run/validation_v2 日志回收和路径白名单。
- 本说明、README 和 run/validation_v2/step3_<编号>/：保存方案、证据及状态。第 3 项修改前指纹与 helper/评价模块原文件已保存于 step3_20261019_081534。

模型、评分生成、原始数据、冻结协议、manifest、环境与依赖锁、V1 结果及旧缓存均不修改。不重算旧结果，不启动模型拟合或正式 run/v2。跨类别/种子汇总及运行器接入继续在后续对应项完成。

## 3 验收顺序及资源

1. 本机 NumPy 核心检查：完全同分、部分同分、排列不变性、跨块同分、完美/反向排序、不平衡、非法输入。固定小样本用独立逐正负对/阈值枚举作为参考。
2. 本机离线运输检查：PowerShell/Bash 语法、限定文件上传、已有不同文件拒绝、归档哈希及路径保护、原动作命令仍可渲染。不实际连接集群。
3. TC2 CheckMetrics：复用已验收的专用环境，MGPU-TC2 / normal，1 节点、1 task、2 CPU、4 GiB、15 分钟，不申请 GPU；一次一个本人准备或验收作业。不在头节点运行指标计算。
4. 完整验收使用 scikit-learn 1.7.2 对照同一数组，AUROC/AP 绝对误差 <=1e-12；合成测试覆盖第 95 百分位、等于阈值、开发测试隔离、零掩膜、并集、最近邻、矩形原图和 LOCO 分组。兼容四/五种评分规则，检查指标不修改输入数组。
5. 远端运行要求最后一次第 2 项 all 验收已通过；先验证冻结协议与八份 manifest 哈希，确认环境/导出与第 2 项一致。只发布不存在或哈希相同的测试源文件，未知不同文件停止、不覆盖。作业结果和源文件哈希记录于 run/validation_v2/step3_job_<jobid>/，full 全通过才输出 step_3_complete=true；core 通过不代表本项完成。

SSH 密码仍由用户在本机终端输入。CheckMetrics 先检查、上传再提交一次 CPU 作业，最多等待约 40 秒回收快照；未结束时只 Collect 同一编号，不重复提交。新记录在独立 validation_v2 目录，既有 setup_v2 记录保持原样。

## 4 参考与实施状态

- [scikit-learn 1.7 AP](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.average_precision_score.html)
- [scikit-learn 1.7 AUROC](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.roc_auc_score.html)
- [NumPy 1.26 percentile](https://numpy.org/doc/1.26/reference/generated/numpy.percentile.html)

本地与远端均已实际验收通过，结果及证据路径见第 5、6 节。

## 5 已完成的本机实现与验证

指标核心和评价入口已按上述范围实现。图像与像素共用同一分组核心；正式二分类缺类时均明确报错。输入保护同时覆盖重复路径、相对路径越界、缺少必要元数据、正常图携带掩膜及异常图没有掩膜。LOCO 可通过分组名或 mvtec_loco 路径识别，避免缺失全部组名时被当作普通 AD。原四种规则的结果字段保持兼容，五种规则以相同入口接收；像素结果与图像聚合规则无关。

本机最终核心检查为 `run/validation_v2/step3_local_core_final_20261019/setup_status.json`，9 个测试全部通过，覆盖独立枚举参考、多种分块大小、跨块同分、次序不变性和相邻 FP32 数值。运行使用本机已有 Python 3.12.14 / NumPy 2.3.5，未安装新依赖；它不能替代 TC2 固定 NumPy 1.26.4 / scikit-learn 1.7.2 下的完整验收。另一次本机 full 调用被 Linux SLURM 防护按预期拒绝，记录于 step3_local_full_guard_20261019；这不是远端测试失败。

运输离线检查覆盖现有十种动作加 CheckMetrics，共 15 条远端命令的渲染与 Bash 语法、两种日志目录回收、坏归档哈希和非法路径拒绝。实际渲染的发布代码还以新目录、相同文件、未知冲突、损坏包四种合成场景验证；确认只发布五个批准文件，data.py 内容与修改前一致。所有此类调用均已替换为本机模拟，不连接或提交远端。

本次使用的本机验收入口为：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_setup_v2.ps1" -Action CheckMetrics
```

仅检查打包内容、不连接远端时，追加 `-ValidateOnly`。若作业仍在排队或运行，仅使用同一入口 `-Action Collect -JobId <返回编号>` 回收。本次作业已完成，无需重复提交。

## 6 TC2 完整验收与第 3 项完成

TC2 作业 43956 于 2026-10-19 在 TC2N01 完成，状态为 COMPLETED / 0:0，耗时 19 秒。它使用第 2 项已验收的专用环境，以 2 CPU、4 GiB、15 分钟上限执行合成测试，未申请 GPU，也未执行模型拟合或正式实验。运行记录中的 Python 3.10.22、NumPy 1.26.4、scikit-learn 1.7.2、torch 2.11.0+cu128、torchvision 0.26.0+cu128、Pillow 12.3.0 与固定环境一致。

完整模式共 24 项测试通过，失败、错误、跳过均为 0。81 组 scikit-learn 对照中，AUROC 最大绝对误差为 1.1102230246251565e-16，AP 为 2.220446049250313e-16，均小于约定上限 1e-12。测试包括同分及跨块边界、全像素原图尺寸、零掩膜与多掩膜并集、开发集阈值隔离、严格大于阈值、四/五种评分规则、LOCO 两类异常分别评价和非法输入拒绝。远端完整状态为 `step_3_complete=true`，标准错误日志为空。

本机独立核验回收归档的 SHA-256 为 `E4D4112A233B39754EB10BC35E877F820379B00588BC525C3A8DBFCDF041515A`，其中 100 个普通文件与已下载内容逐字节一致，路径及成员类型均通过检查。五份源文件的当前本机、上传包、远端阶段清单与测试记录哈希完全一致。冻结协议、八份 manifest、环境导出、依赖锁及第 2 项完成记录保持不变；修改前 750 份文件只出现方案允许的 evaluate.py 与 README 修改，346 份 V1 文件均保留，未创建正式 run/v2。

证据保存在 `run/validation_v2/step3_20261019_081534/`：

- `setup_status.json`：本项最终完成状态及实现指纹。
- `remote_job_43956/verification.json`：独立回收核验、源代码一致性及范围检查。
- `remote_job_43956/snapshot_20261019_083700_13089bef/`：终端记录、完整归档及展开的状态/日志；合成 PNG 完整保存在归档中。

本项完成不代表运行器、模型实现或正式 V2 结果已验收。后续仍按用户逐项确认的方案推进。
