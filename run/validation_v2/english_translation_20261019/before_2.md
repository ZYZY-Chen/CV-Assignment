# TC2 V2 环境与输入核验

第 2 项已于 2026-10-19 通过最终联合验收，为后续修正后的实验准备了集群环境、原始数据和预训练权重。最终作业为 43950，状态 COMPLETED / 0:0，`step_2_complete=true`；完整证据见第 6.9 节。核验工具只读取输入并保存检查记录；不安装软件、不下载或修复数据、不提取缓存、不拟合模型，也不修改 V1 结果及冻结协议。

第 6 节补充方案确认后，独立准备脚本在限定的个人目录创建了专用环境并恢复输入；来源补充见第 6.7 节。硬件作业 43939、环境准备作业 43940、输入准备作业 43945，以及最终联合验收作业 43950 均已通过。以下保留按阶段记录的准备过程；当前完成状态以第 6.9 节及 setup_status.json 为准。

连接为 `huajie001@10.96.189.12:22`，协议为 SSH。当前已确认用户通过终端输入密码登录；这不会让另一个新发起的非交互 SSH 连接自动获得认证。密码和私钥只由用户在本机终端或客户端管理，不写入项目文件。

## 1 准备阶段发现记录和输入配置

[tc2_setup.json](../configs/tc2_setup.json) 保存已核实的连接信息、环境、目录、分区、QoS 和最终验收状态。发现过程中远端字段为 null 时表示尚未核验，不应猜测用户名对应的 Home 路径、环境名称或数据位置。下列查询记录保留当时的状态。

2026-10-19 06:22 SGT 的本人终端查询已确认：Home 为 `/home/mcaai/huajie001`，分区为 `MGPU-TC2`，QoS 为 `normal`。该 QoS 的每用户资源上限为 `cpu=10,gres/gpu=1,mem=30G`，最多 2 个作业，单个作业最长 6 小时。分区显示的 `infinite` 不取消账号 QoS 的时长限制。原定 1 GPU、2 CPU、4 GB、15 分钟的核验请求在这些限制内，仍按一次一个 GPU 核验作业执行。

可用模块列表包含 `anaconda/25.5.1`，但本轮终端未实际加载它，尚未取得 Conda 环境清单。个人 Home 深度不超过 3 层的候选项目与数据目录搜索未返回结果；这不证明所有原始数据或环境均不存在。`df` 显示的是共享文件系统剩余空间，不能作为个人存储配额。GPU、驱动、依赖、数据和权重仍待核验。

远端准备目录限定为核实后的个人 Home 下 `ca6129_v2_setup`。首次创建前检查同名目录；有既有文件时先核对，不直接覆盖。已有项目与数据作为只读输入复用，访问范围限于个人 Home 和明确授权的共享目录。

登录后首先执行以下管理查询，并据其输出填写准备配置：

```bash
pwd
mytcinfo
module avail anaconda
module load anaconda/25.5.1
conda info --base
conda env list
ls -la "$HOME"
```

这些查询不检查 GPU，不运行模型。GPU 信息、依赖导入和骨干运行均留在 SLURM 计算作业内。已有环境缺包、版本冲突或输入缺失时，先列出准确变更清单，更新设计方案并再次确认，不自动安装或下载。

当前下一轮只需实际加载上述模块，查询环境列表和 base 环境包清单，并查看个人配额及本人 `.conda/envs`、`.cache/torch/hub/checkpoints`、`ca6129_v2_setup` 目录是否存在。配置中的准备目录是已按真实 Home 推导出的目标路径，尚未创建或检查；环境前缀和输入路径继续保持 null。

上述下一轮查询随后已收到：`anaconda/25.5.1` 加载成功，Conda base 为 `/apps/anaconda3-2025.06-0`；环境列表只列出 base，Python 为 3.13.5。筛选后的包清单列出 NumPy 2.1.3、SciPy 1.15.3、scikit-learn 1.6.1、Pillow 11.1.0、pandas 2.2.3、matplotlib 3.10.0、PyYAML 6.0.2、tqdm 4.67.1，没有列出 torch/torchvision。本人 `.conda/envs`、`.cache/torch/hub/checkpoints`、`ca6129_v2_setup` 均不存在。输出未提供个人配额结果，GPU 仍未测试。这些结果不证明未登记环境或搜索范围之外的输入一定不存在。

## 2 检查工具和所需文件

[check_setup_v2.py](../scripts/check_setup_v2.py) 有三种模式：

| 模式 | 内容 | 执行位置 |
|---|---|---|
| inputs | 核对冻结 manifest、数据和掩膜哈希、权重哈希、旧缓存元数据 | 可在本地 CPU，或与其他检查一同在计算节点执行 |
| environment | 查询实际依赖、驱动和 GPU，执行小型 FP32 CUDA 运算 | Linux SLURM 计算节点 |
| all | 完整输入检查，加上述环境检查和已验证权重的骨干前向 | Linux SLURM 计算节点 |

在准备目录保留以下结构后运行；目录内只放核验所需文件，不必复制旧结果或旧缓存：

```text
ca6129_v2_setup/
  configs/protocol_v2.json
  configs/tc2_setup.json
  manifests/manifest_mvtec_ad_bottle.json
  manifests/manifest_mvtec_ad_cable.json
  manifests/manifest_mvtec_ad_capsule.json
  manifests/manifest_mvtec_ad_screw.json
  manifests/manifest_mvtec_ad_tile.json
  manifests/manifest_mvtec_ad_wood.json
  manifests/manifest_mvtec_loco_juice_bottle.json
  manifests/manifest_mvtec_loco_screw_bag.json
  scripts/check_setup_v2.py
  scripts/slurm/check_setup_v2.sh
  run/setup_v2/
```

原始数据和权重可留在核实后的既有位置，绝对路径填入 `remote.datasets_root` 和 `remote.weights_path`。八份 manifest 及协议须与本地冻结文件逐字节一致。工具会先验证协议及 manifest 指纹；发现不一致就停止，不重建划分。

GPU 模式还要求 Home、准备目录、环境前缀、分区和 QoS 已填写；检查程序只从核实后的个人 Home 下 `ca6129_v2_setup` 副本运行，并核对实际 Python 前缀和 SLURM 分区，避免把验收记录或环境导出写入原项目目录。

## 3 数据与权重检查

固定清单需要 3650 张图片、1019 个掩膜文件。逐文件记录预期 SHA-256、实际 SHA-256、大小和状态，区分匹配、缺失、哈希不一致、读错误和路径越界。不需要数据集的额外说明文件来凑足这些数量，也不把额外文件误计入图像或掩膜数量。

配置未填写数据路径时，inputs/all 模式明确停止；不会扫描其他用户目录寻找数据。旧 FP16 缓存只读取元数据并标记不符合 V2 缓存条件，保持原文件不变。

权重固定为 `ResNet18_Weights.IMAGENET1K_V1`，官方文件来源为 [torchvision ResNet18 定义](https://github.com/pytorch/vision/blob/v0.26.0/torchvision/models/resnet.py)。核验完整 SHA-256，检查其符合官方文件名中的 `f37072fd` 哈希前缀，并在计算节点加载文件确认模型兼容性。只记录本地实际权重的完整哈希，不编造完整校验值。

骨干创建时使用 `weights=None`，随后显式加载已验证文件，避免 torchvision 自动联网下载。前向输入为一个 `1×3×256×256` 的 FP32 零张量，仅检查三层形状、精度和有限值，不构成检测或定位实验。应得到 `layer1=[64,64,64]`、`layer2=[128,32,32]`、`layer3=[256,16,16]`，顺序为通道、高、宽。

## 4 SLURM 核验作业

[check_setup_v2.sh](../scripts/slurm/check_setup_v2.sh) 只在已有 SLURM 作业内运行；直接在头节点或本机运行时会停止。脚本保留调度器分配的 `CUDA_VISIBLE_DEVICES`，通过核实后的 Anaconda 模块和已存在的 Conda 环境前缀激活环境，不修改 `.bashrc` 或环境内容。

初始请求为 1 节点、1 task、1 GPU、2 CPU、4 GB 主机内存、15 分钟。分区和 QoS 不写成手册示例默认值，必须从账号实际查询结果传入；超过实际配额时先调整设计再提交。同一账号一次运行一个 GPU 核验作业。

账号、环境及路径核实后，依次提交 environment、all 两类检查。提交者须从准备目录提交并显式指定该目录内的输出路径。以下使用的变量必须先按真实查询结果赋值：

```bash
mkdir -p run/setup_v2
sbatch --partition="$verified_partition" --qos="$verified_qos" \
  --export="ALL,TC2_ANACONDA_MODULE=$verified_anaconda_module" \
  --output="$PWD/run/setup_v2/slurm-%j.out" \
  --error="$PWD/run/setup_v2/slurm-%j.err" \
  scripts/slurm/check_setup_v2.sh "$verified_environment_prefix" environment
```

environment 通过且数据、权重路径齐全后，以同样资源将最后一个参数改为 `all`，提交最终验收。环境和 GPU 检查不能以本地 CPU 结果替代；CUDA 不可用时不会静默回落 CPU。

本地只读 inputs 检查的命令为：

```text
python -B scripts/check_setup_v2.py --mode inputs --datasets-root <已核实的数据根目录> --output-dir run/setup_v2/<新的检查编号>
```

本地检查不会导入 torch。每次使用新的检查编号，工具拒绝覆盖非空检查目录。inputs 模式即使全部文件匹配，也只能证明输入条件，不会把第 2 项标为已全部完成。

## 5 记录和验收

检查记录保存在 `run/setup_v2/<检查编号>/`，与第 5 项才启用的 `run/v2/` 正式实验目录分开。

| 文件 | 记录 |
|---|---|
| connection_info.txt | 连接和认证实际状态，不含密码或私钥 |
| qos_info.txt | 从本人账号查询得到的资源信息 |
| data_audit.json | 完整、缺失和不匹配的输入文件清单，以及旧缓存审计 |
| weights_info.json | 指定权重的实际位置、完整哈希和核验状态 |
| environment.json | 实际 Python、依赖、驱动、GPU 与检查结果 |
| gpu_info.txt | GPU 运算、FP32 设置和骨干检查记录 |
| versions.txt | 实际 Python 和依赖版本 |
| setup_status.json | 已完成、未完成及阻塞条件；不会把缺项写成通过 |

GPU 环境检查通过后，导出 `environment-tc2.yml` 与 `requirements-tc2-lock.txt`；导出时排除个人 prefix、Conda 环境变量及带认证信息的包源。已有锁文件内容不同时停止并报告，不直接覆盖。尚未核验时不生成看似有效的空锁文件或示例版本清单。

第 2 项仅在 all 模式的输入、权重、环境、GPU 运算、骨干前向和环境导出全部通过时完成。依赖版本与驱动实测不兼容、数据缺失或哈希异常时保留核验结果，进入补充设计与确认。

第 3 至第 5 项继续修复评价、方法与运行流程；第 6 项再生成 FP32 特征缓存并做两方法端到端试运行。

## 6 第 2 项补充设计：新建环境并恢复输入（已确认）

用户已明确回复“确认执行第2项补充修改”，并要求后续远端命令参考本机 `output/tc2_readonly_check.ps1`，自动把输出保存到本地。本节方案已获确认；远端操作是否完成仍以实际回传记录为准。此前核验内容和数据划分不变。SLURM 会把脚本复制到作业暂存目录，三个 SLURM 入口统一用 `SLURM_SUBMIT_DIR` 定位并检查准备目录，修正此前入口以脚本位置定位的问题；因此提交前必须切换到准备目录。

### 6.1 顺序与停止条件

1. 检查个人 Home、准备目录及同名目标是否仍符合本次发现，记录存储配额查询结果和文件系统空间。配额无结果时明确标为未知。仅在 `/home/mcaai/huajie001/ca6129_v2_setup` 建立准备目录；同名已有内容先检查，遇到冲突停止，不覆盖或删除。上传冻结协议、八份 manifest、核验脚本、只读的现有 `requirements-lock.txt` 及本节列明的补充脚本。
2. 先提交硬件短作业：`MGPU-TC2` / `normal`，1 节点、1 task、1 GPU、2 CPU、4 GiB、15 分钟，只记录 GPU 型号、显存、驱动、操作系统架构和 glibc 版本。无需先安装 PyTorch，不在头节点查询 GPU。以 Linux x86_64、glibc >=2.28、驱动 >=570.26 作为本方案 cu128 安装的保守放行条件；不足时暂停，另行讨论版本方案，不修改系统驱动。实际 GPU 对所选软件的支持仍由后续 CUDA 运算验收。
3. 硬件放行后，新建专用 Conda 环境 `/home/mcaai/huajie001/ca6129_v2_setup/envs/ca6129-ad-v2`。不向 `/apps` 共享 base 安装包。Conda 使用 conda-forge 创建 Python 3.10 与 pip>=24；先从官方 cu128 索引安装 `torch==2.11.0+cu128`、`torchvision==0.26.0+cu128`，再安装现有锁文件固定的其余依赖。先检查包解析结果；冲突、缺失或网络失败时保留日志并停止，不自行升级、降级或换镜像。
4. 恢复固定八类原始输入：MVTec AD 的 bottle、cable、capsule、screw、tile、wood；MVTec LOCO AD 的 juice_bottle、screw_bag。若发现或由用户提供已存在的完整副本，先按冻结哈希验收再复用；否则只从 MVTec 官方入口取得对应原始包。官方直链无法使用时，可通过官方网页下载同一包，再经用户本机 SSH/SFTP 上传；不自动改用第三方镜像。按 CC BY-NC-SA 4.0 用于本课程。数据解压至准备目录下 `datasets/{mvtec_ad,mvtec_loco}`；校验包成员路径并拒绝链接或越界成员，缺损或冲突文件不覆盖。允许恢复该八类完整官方目录，验收只按冻结 manifest 的 3650 图片和 1019 掩膜逐文件哈希判断，不重新划分。
5. 从 `https://download.pytorch.org/models/resnet18-f37072fd.pth` 下载权重至准备目录下 `weights/resnet18-f37072fd.pth`，记录来源、大小、完整 SHA-256，并核对冻结的 `f37072fd` 前缀。下载写入临时文件，完整校验后发布，已有文件先核验不覆盖。
6. 用已有核验脚本依次执行 environment、all 作业。CUDA FP32 运算、依赖导入及权重骨干前向在 SLURM 内执行；通过后导出实际 Conda 和 pip 锁文件，回传日志与验收记录。仅 all 的全部检查通过，才将第 2 项标记完成。

### 6.2 依赖与准备作业

专用环境的顶层目标如下，沿用当前项目依赖版本；共享 base 中现有版本不作为目标：

| 包 | 目标 |
|---|---|
| Python | 3.10；实际补丁版本写入验收导出 |
| torch / torchvision | 2.11.0+cu128 / 0.26.0+cu128 |
| NumPy / SciPy | 1.26.4 / 1.12.0 |
| scikit-learn / Pillow | 1.7.2 / 12.3.0 |
| pandas / matplotlib | 2.2.3 / 3.10.9 |
| PyYAML / tqdm | 6.0.3 / 4.70.1 |

PyTorch 的版本配对与 cu128 发行源已核对 [官方历史版本安装说明](https://pytorch.org/get-started/previous-versions/)。驱动放行条件采用 [NVIDIA CUDA 12.8 GA 驱动表](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html)，是本方案选用的保守条件，不把较低驱动一概判为无法使用所有 CUDA 软件。

安装与数据解压通过独立 SLURM 准备作业执行：1 节点、1 task、2 CPU、8 GiB、1 小时，优先不申请 GPU；如果该分区明确要求 GPU，则允许同样资源下申请 1 GPU。每次只提交一个准备或核验作业，任意时刻最多使用 1 GPU。超时或资源不足时保留日志和可续传临时包，不自动扩大资源或反复重试。GPU 验收作业继续使用已批准的 1 GPU、2 CPU、4 GiB、15 分钟。

临时包、下载记录、Conda/pip 缓存及临时文件限于准备目录的 `_downloads`、`_package_cache`、`tmp`。Conda 创建环境可能登记本人 `~/.conda/environments.txt`，仅允许正常追加该环境登记并保留已有条目；不运行 `conda init`、不修改 shell 启动文件。存储不足时停止，不自动删除已有数据或环境。

### 6.3 文件与目录变更范围

除已批准的第 2 项配置、文档、README、SLURM 核验入口目录定位修正、实际环境导出及 `run/setup_v2` 记录外，本补充方案新增四个源文件：

| 新文件（相对 group_XX_code） | 职责 |
|---|---|
| scripts/slurm/probe_hardware_v2.sh | 无 PyTorch 依赖的硬件短作业 |
| scripts/slurm/prepare_tc2_v2.sh | SLURM 内按 environment / inputs 模式调度准备动作 |
| scripts/prepare_tc2_environment_v2.sh | 创建专用环境、固定依赖、限定缓存和日志路径 |
| scripts/prepare_tc2_inputs_v2.py | 官方输入获取、安全解压、权重下载与逐文件哈希验收 |

远端新增内容仅位于准备目录内的 `envs/ca6129-ad-v2`、`datasets`、`weights`、`_downloads`、`_package_cache`、`tmp` 和核验文件/日志，以及上述 Conda 个人环境登记。官方网页下载需要本机中转时，下载包暂存在本机 `group_XX_code/run/setup_v2/<检查编号>/transfer`，仅上传这八类原始包与指定权重，不复制旧结果或旧缓存。转移后不自动删除中转包。

现有环境文件、旧下载器、算法、指标、运行器、冻结协议、八份 manifest、V1 输出均保持原样。本补充方案不安装 Anomalib，不生成特征缓存、不拟合模型、不激活正式 `run/v2` 实验输出、不撰写报告。SSH 继续由用户在自己的终端输入密码，不新增或修改 SSH 密钥、代理和配置；需要交互认证的传输与提交由该终端执行，助手准备限定范围的文件与命令并核验回传证据。

### 6.4 本机操作与输出回收（本次用户新增要求）

新增本机 `output/tc2_setup_v2.ps1`，保留参考脚本不变。运行时密码仍交给 OpenSSH 直接读取。默认 `Probe` 动作先验证本人 Home 和目标路径，再上传限定文件、校验文件哈希并提交硬件短作业；不会安装包或获取数据。首次上传需要分别进行 SSH 检查、SCP 上传和 SSH 提交，可能提示多次输入密码。

后续通过同一脚本的 `PrepareEnvironment`、`PrepareInputs`、`CheckEnvironment`、`CheckAll` 分阶段操作；准备作业的 GPU 申请默认 0，分区明确拒绝无 GPU 作业时才使用 `-PreparationGpu 1`。`Collect -JobId <编号>` 只读取作业状态和回收输出，不提交或重试作业。`UploadInputs -InputDirectory <目录>` 仅上传名字符合固定八类包或指定权重的文件到 `_downloads`，已有文件须哈希一致。

每次操作生成本机 `output/tc2_setup_v2_<时间_编号>/terminal.txt`，并将远端 `run/setup_v2` 下的记录、日志、配置及已产生的实际锁文件下载到该目录的 `remote`。传输内容通过 SSH 输出独立的 Base64 归档段回收，终端日志只记录归档摘要；校验归档 SHA-256 和允许的文件路径后解包。不会把数据集、环境目录、预训练权重或特征缓存下载为日志附件。

提交后最多等待约 40 秒回收当前状态，排队或运行中的作业明确保留为未完成；使用 Collect 再回收，不把提交成功当作验收通过。environment 核验工具返回 2 可能仅表示第 2 项尚未全部完成，须读取其 environment_ready、environment_export 等字段，不能单看 SLURM 退出码。安装和输入准备仍遵守本节前置条件及停止条件。

当前首先在本机 Windows PowerShell 执行：

```powershell
& 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_setup_v2.ps1' -Action Probe
```

若本机策略阻止执行该脚本，可只对这次进程使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_setup_v2.ps1' -Action Probe
```

无需把上述命令粘贴到远端 Linux。硬件结果由助手核对后，再按相同本机入口依次运行 `PrepareEnvironment`、`PrepareInputs`、`CheckEnvironment`、`CheckAll`。某作业尚未结束时，用同一入口加 `-Action Collect -JobId <已返回的数字编号>` 回收新状态，不重新提交同一阶段。官方直链失败时先保存失败记录；下载完成的官方包或指定权重可用 `-Action UploadInputs -InputDirectory <本机包所在目录>` 上传，再继续输入准备。

### 6.5 已核验的实际进展

用户回传 `output/tc2_setup_v2_20261019_065131_7cb9d616/terminal.txt`。2026-10-19 06:51:58 SGT 的硬件作业 `43939` 在 `TC2N01` 成功完成，SLURM 为 `COMPLETED / 0:0`。实际 GPU 为 NVIDIA A40，显存 46068 MiB，驱动 570.148.08；系统为 Linux x86_64、glibc 2.34。全部硬件放行条件通过；CUDA 张量运算及骨干前向尚未测试。

首次准备目录已经创建，17 个上传文件逐一显示 SHA-256 校验 OK。回收归档完整哈希为 `3C4BF5352C5304BDEE88AE088CAFDB25D2CF44DAB9BB7E2D28F81B8D6FF1904A`，归档与已解包的五个记录文件已逐一核对一致。个人存储配额仍无有效数值，8.9T 是共享文件系统剩余空间。

环境准备作业 `43940` 已按原定 2 CPU、8 GiB、1 小时、默认不申请 GPU 的请求成功提交。用户随后回传 `output/tc2_setup_v2_20261019_065531_0283f854/terminal.txt`，该快照显示作业在 `TC2N01` 为 `RUNNING`，已运行 39 秒。前置检查通过，Conda dry-run 依赖计划为 success；尚无安装完成记录，不能将计划中的包版本认定为已安装版本。stdout/stderr 在该快照中均为空。

该次回收归档 SHA-256 为 `0D68D5A83091D9629B5C886A46217791F1B4C4A11ADC7E474F0FCADC96FE249C`，已核对归档及解包的 11 个记录一致。当时下一动作仅为 `Collect -JobId 43940` 回收最新状态，没有重复提交环境准备或开始数据恢复。已有的远端核验文件无需再次上传。

后续 `output/tc2_setup_v2_20261019_065834_e0fda803/terminal.txt` 快照显示同一作业 43940 仍为 RUNNING，已运行 2 分 59 秒，正在安装 torch、torchvision 和 CUDA 依赖。torch 安装计划中的版本为 2.11.0+cu128 / 0.26.0+cu128，stderr 为空，尚无 preparation_status.json 或失败标记。回收归档 SHA-256 为 `8958F6888AB24878388747548A1ECC747248487F4A4F113CF8FE596B13F1C274`，12 个记录与归档一致。继续等待后用 Collect 查询同一作业；此时不重提安装作业。

最新 `output/tc2_setup_v2_20261019_070538_5b0fa3c0/terminal.txt` 及结构化记录确认环境作业 43940 为 `COMPLETED / 0:0`，用时 5 分 56 秒。专用环境前缀为 `/home/mcaai/huajie001/ca6129_v2_setup/envs/ca6129-ad-v2`；全部 10 个顶层包的实际版本与第 6.2 节目标一致，pip check 输出 `No broken requirements found.`，stderr 为空。回收归档完整哈希为 `9B38B44D0D9E4E12E63FE7546CD232F60FD8DC4ED05A8D9ABD8DBE59259ADE72`，14 个记录逐一核对通过。

当前下一动作是 `PrepareInputs`，恢复冻结八类数据和指定权重并按 manifest 哈希验收。环境包安装通过不等于 CUDA 验收通过；尚不导出最终环境锁文件，不开展缓存提取、拟合或正式实验。第 2 项仍未完成。

### 6.6 准备脚本的 Conda 激活兼容修复

用户回传 `output/tc2_setup_v2_20261019_070807_e3560acc/terminal.txt`，输入准备作业 43943 在 3 秒内以 `FAILED / 1:0` 结束。错误为共享 base 的 `qt-main_activate.sh` 读取未定义的 `QT_XCB_GL_INTEGRATION`，触发入口脚本的 `set -u`。失败发生在输入准备 Python 程序启动前；环境作业 43940 已通过的安装结果继续有效。

此修复限定在已批准的两个 SLURM 入口 `scripts/slurm/prepare_tc2_v2.sh` 和 `scripts/slurm/check_setup_v2.sh`：仅在 Conda hook 求值及环境激活期间临时使用 `set +u`，激活后恢复 `set -u`；整个过程保留 `set -e` 和 pipefail。先将 hook 保存为变量，使 hook 命令失败也能正确终止。共享 Qt/Conda 文件、已安装依赖、数据协议和实验代码均不修改。

本机现有 PowerShell 入口增加 `RepairActivation`，只传送上述两个修正版脚本。替换前要求远端文件哈希为首次上传的已知值或本次修正值；其他内容一律停止。两个旧文件和变更清单先备份到远端 `run/setup_v2/activation_fix_<编号>/`。检查无运行作业、最近输入准备确实是上述激活失败且尚未进入 Python 后，才应用修复并重新提交一次原资源的 inputs 准备作业，回收日志到本机。该动作不重建环境、不重提环境安装，不反复重试下载；后续输入或网络问题继续按既定停止条件处理。

回归验证覆盖原始激活片段能复现未定义变量错误、修正片段可处理同类 hook、激活后 nounset 恢复、hook/激活失败继续终止、替换前哈希冲突不写入，以及本机修复入口的命令渲染与输出回收。实际远端修复是否通过仍以回传证据为准。

用户回传 `output/tc2_setup_v2_20261019_071513_90e03083/terminal.txt`：两个入口已部署，作业 43944 已进入输入 Python 程序，证明原激活错误已解决。该作业因第一个 bottle 官方旧直链返回 HTTP 404，以 FAILED / 2:0 结束，用时 5 秒；不重建环境、不盲目重试该链接。归档 SHA-256 为 `993910EF013A6A0A17D5C365ED8F2909A2263C16500EE16A72582CCEEBB4AFE3`。第 2 项仍未完成。

### 6.7 数据来源补充修改（已确认）

用户参考项目 `datasets/README.md`，明确回复“确认执行第2项数据来源补充修改”。本节仅替代第 6.1 节第 4 步中 AD 必须直接从官方交付的限制；其他环境、资源、数据划分及验收条件不变。不自动搜索或切换其他镜像。

1. MVTec AD 固定使用 README 指定的第三方仓库 `micguida1/mvtech_anomaly_detection`，版本固定为 `eb692b36147a3b3f12c561b879a062104c1f20b8`。下载 `mvtec_anomaly_detection.tar.xz`，5264982680 字节；文件 SHA-256 必须为 `CF4313B13603BEC67ABB49CA959488F7EEDCE2A9F7795EC54446C649AC98CD3D`。该哈希证明取得指定镜像文件，不代替原图的冻结哈希验收。原始发布者仍记为 MVTec Software GmbH，交付来源如实记录为 Hugging Face 第三方镜像。
2. 完整压缩包只暂存于准备目录 `_downloads`，仅将 bottle、cable、capsule、screw、tile、wood 六类解压至 `datasets/mvtec_ad`。先流式检查整个包的成员路径、类型、重复项和六类必需文件的哈希及目标冲突，再进行第二遍流式提取；不提取其他九类或包根目录说明文件，不重新压缩图像、不改变像素。链接、设备、越界路径、缺项及哈希冲突均停止，已有文件不覆盖。
3. LOCO 仍用原定两个官方逐类包。2026-10-19 的本机抽样请求均返回 HTTP 206 和合法 XZ 头：juice_bottle 为 655555080 字节，screw_bag 为 1102844304 字节。这只证明抽样可达，不代表整包或图像已验收。ResNet18 权重仍从 PyTorch 官方来源取得。
4. 优先由原资源的 TC2 inputs 作业下载和恢复。已有下载器保留单次尝试及受控续传，镜像大小或哈希不符不发布，部分包保留，不扩大资源、不自动改源。若集群网络不能取得这些固定包，可在本机调用同一个输入脚本的 download-only 模式，将包暂存在本项目 `run/setup_v2/<检查编号>/transfer`，只下载不解压、不导入 Torch。完成后用已有 SSH 上传流程中转；上传白名单增加上述固定 AD 完整包，继续拒绝未知名称及覆盖冲突。
5. 变更限定为 `scripts/prepare_tc2_inputs_v2.py`、`configs/tc2_setup.json`、本机 `output/tc2_setup_v2.ps1` 和本操作文档，以及 `run/setup_v2` 的验证与证据记录。旧下载器、数据 README、算法、指标、依赖、冻结协议、八份 manifest、V1 输出均不修改。配置中保留原 LOCO 来源，显式新增已批准的 AD 镜像身份和固定版本，不设第三方自动兜底。
6. 本机入口新增 `UpdateInputSources`：依据作业 43944 回收的配置生成只改变上述来源字段的候选配置，连同输入准备脚本打包。要求远端最近 inputs 作业仍为已记录的 43944 / HTTP 404、安装成功、无本人排队或运行作业，且两个目标文件哈希属于已知旧值或本次新值；全部检查通过后先备份两个旧文件，再发布并提交一次相同资源的 inputs 作业。遇未知修改停止。`-ValidateOnly` 只生成本机包，不连接集群。
7. 本机入口新增 `DownloadInputs`，只执行上述 download-only 备用下载；默认建立新的 transfer 目录，显式提供 `-InputDirectory <原 transfer 目录>` 时才复用原目录并按原来源续传。`UploadInputs` 允许指定完整 AD 包；两个动作都不自行提交作业。网络失败时保留原日志和部分包，不反复重试。全部输入仍按冻结清单核验 3650 张图片和 1019 个掩膜；最终 environment / all GPU 验收通过后才完成第 2 项。

本机下一命令为 `tc2_setup_v2.ps1 -Action UpdateInputSources`，SSH 密码仍由用户在本机终端输入。返回运行中状态时仅用 `Collect -JobId <编号>` 回收；不重复执行更新或重新提交同一阶段。

本次本地验证已通过：旧输入恢复的回归检查、完整包按类别筛选及异常包拒绝、固定镜像身份验证、download-only 无解压与无 Torch 导入、候选远端配置仅改变三个来源字段、两文件更新的备份及未知冲突保护、十种本机动作的十三条远端命令渲染与 Bash 语法检查、日志归档传输及错误哈希/路径拒绝。另已用实际入口的 `UpdateInputSources -ValidateOnly` 生成更新包；此操作没有联网或提交作业。完整数据下载和冻结哈希验收尚未完成。

用户随后回传 `output/tc2_setup_v2_20261019_073239_2a2bf5ec/terminal.txt`。来源更新已实际部署：两个目标的新哈希及对应旧文件备份核验通过，远端配置的语义差异仅限本节批准的三个来源字段。回收归档 SHA-256 为 `F2607938735D69E8C1A6127F4B6C02A1961D6FF7E27387C375C7664E0A16049D`，32 个记录逐一核对一致。

该快照显示 inputs 作业 43945 在 TC2N01 运行 39 秒，状态 RUNNING，已进入固定 AD 镜像的恢复阶段；stderr 为空。尚未产生 transfers.json 或 preparation_status.json，不能据此判定整包下载或任何类别恢复完成。当前只需 `Collect -JobId 43945` 回收后续状态；不重复更新来源、不重提 inputs、不启动后续 GPU 验收。第 2 项保持未完成。

后续 `output/tc2_setup_v2_20261019_073540_1c2557d6/terminal.txt` 显示同一作业 43945 仍为 RUNNING，已运行 2 分 40 秒，stderr 为空。归档哈希和 32 个记录与上次一致，未新增完成或失败记录；当前日志未提供下载字节进度，不能推断下载比例或卡住。继续等待约五分钟后仅 Collect 同一作业，不重复提交。

`output/tc2_setup_v2_20261019_074202_446cbb69/terminal.txt` 显示作业 43945 仍在 TC2N01 运行，已运行 9 分 03 秒，stderr 为空。回收归档 SHA-256 为 `403729988D0CDFD913C2E63A784EAE418FA5A70B125DAC38D2A6C94D672816F6`，33 个记录核对一致。新增 transfers.json 确认 AD 完整包的 5264982680 字节及固定 SHA-256 匹配，选定六类已恢复；官方 juice_bottle 包 655555080 字节、SHA-256 为 `72B36B16AE9E5308AB4257F655EDE22173B98FC8E0CE44DB8007B588753747F2`，已恢复。日志已进入官方 screw_bag 恢复阶段。尚无最终输入验收或权重恢复记录，不将七类恢复等同于第 2 项完成。继续等待后 Collect 同一作业。

`output/tc2_setup_v2_20261019_074826_4ba86798/terminal.txt` 回收时，43945 仍为 RUNNING，已运行 15 分 28 秒，stderr 为空。33 个记录及归档哈希与前次一致；仍只有 AD 六类和 juice_bottle 的恢复完成记录，最新阶段为 screw_bag，无法据现有日志细分下载、解压或校验进度。尚不具备开始 GPU 验收的输入完成条件。下一步等待约十分钟后 Collect 同一作业，不修改资源或重提作业。

`output/tc2_setup_v2_20261019_075833_86e1edef/terminal.txt` 及结构化记录确认 inputs 作业 43945 已为 COMPLETED / 0:0，用时 21 分 58 秒，stderr 为空。回收归档 SHA-256 为 `DF844DFB046277CDE9DE65F2BCF0ADB11712D29CC6AF246AC1D6560EE3186622`，36 个记录核对一致。本机逐条交叉核对回传 data_audit.json 与原冻结 manifest：4669 个唯一路径完全一致，3650 张图片及 1019 个掩膜的实际 SHA-256 全部等于冻结值，无缺失或不匹配。八类已恢复，但尚未执行 GPU 验收。

官方 screw_bag 包为 1102844304 字节，实际 SHA-256 为 `4A300E12F5974A9ABDE65984BE4529175698CFCB48D3E3C1430E7CC01D839AAB`。指定 ResNet18 权重为 46830571 字节，实际完整 SHA-256 为 `F37072FD47E89C5E827621C5BAFFA7500819F7896BBACEC160B1A16C560E07EC`，官方 f37072fd 前缀检查通过；模型兼容性仍待计算节点前向验证。核实后的远端数据根目录及权重路径已写入本机配置，未改变来源或实验划分。

当前下一动作改为本机 `tc2_setup_v2.ps1 -Action CheckEnvironment`，使用原批准的 1 GPU、2 CPU、4 GiB、15 分钟检查环境、CUDA FP32 运算并导出实际环境。先核对该作业的 environment_ready 与 environment_export；二者通过后再运行 CheckAll，验收输入、权重、骨干前向及全部条件。不要重提输入准备、重新下载或开始后续实验。第 2 项仍保持未完成。

### 6.8 GPU 环境核验结果与最终验收入口

用户回传 `output/tc2_setup_v2_20261019_080054_297ec9d5/terminal.txt`。environment 作业 43949 在 TC2N01 运行 31 秒，environment_ready=true、environment_export.ready=true，stderr 为空；实际 Python 为 3.10.22，十个目标包版本与批准方案一致，pip check 通过。NVIDIA A40 上 CUDA FP32 运算通过，autocast、matmul TF32、cuDNN TF32 均关闭。

SLURM 显示 FAILED / 2:0，原因是当前核验器只在 all 模式全部通过后返回 0；environment 模式即使检查通过，也因 step_2_complete=false 返回 2。这与 CUDA 失败不同。此模式未请求骨干前向，backbone.status=not_requested，对应 backbone_ready=false；最终 CheckAll 才执行该检查。脚本行为未在本轮修改。

回收归档 SHA-256 为 `71C0E8F2F5C4829649D5AB26B3DB10043F96690534AD3F8B40DCCA215B7FA0CF`，46 个记录核对一致。两个实际环境导出已按原方案保存到本机代码根目录，存在同名不同内容时会拒绝覆盖：environment-tc2.yml 的 SHA-256 为 `47F1DAA83A744743946C83E6DC1963B8FA7E835A4A0F7010A3B0501EF5A3DF38`；requirements-tc2-lock.txt 含 53 个实际 Python 分发包，SHA-256 为 `F7B848F10FFB3F3CCEB707450B2A5FE4DCD9A6C3B489963A8932094E016840B6`。导出没有 prefix 或 variables 顶层字段，没有带认证信息的 URL。

下一动作是本机 `tc2_setup_v2.ps1 -Action CheckAll`，沿用 1 GPU、2 CPU、4 GiB、15 分钟，联合检查原始输入、权重、环境、GPU 骨干前向及实际导出。只有该 all 模式记录 step_2_complete=true 才完成第 2 项；不重提环境安装或数据恢复，不推进第 3 项。

### 6.9 第 2 项最终验收通过

用户回传 `output/tc2_setup_v2_20261019_080436_6b57e857/terminal.txt`。all 作业 43950 在 TC2N01 成功完成，COMPLETED / 0:0，用时 32 秒，stderr 为空。最终状态为 mode=all、status=ready、step_2_complete=true；inputs_ready、weights_ready、environment_ready、backbone_ready 及 environment_export.ready 全部为 true。

回收归档 SHA-256 为 `00646CDD5FC11334A28D8C52EE39D986FE3E73C77DDEB9B5052CBFDCD4913561`，55 个记录逐一核对一致。最终 data_audit.json 再次与冻结 manifest 交叉核对：4669 个唯一路径、3650 张图片和 1019 个掩膜全部匹配。GPU 骨干加载的权重完整 SHA-256 与已验证的官方文件一致；三层 FP32 特征 CHW 分别为 layer1=[64,64,64]、layer2=[128,32,32]、layer3=[256,16,16]，形状、精度和有限值检查均通过。autocast 和两项 TF32 均关闭。

两个实际环境导出的哈希与作业 43949 及本机保存文件完全一致。完整原始记录及本机交叉核验结果保存在 `run/setup_v2/step2_20261019_060542/all_check_job_43950/snapshot_20261019_080436_6b57e857/`。配置的 final_acceptance、本节操作说明、代码 README 和第 2 项总状态均更新为已完成；这属于已批准的验收收尾记录。原有 388 个基线文件再次核对，只有获准更新的代码 README 改变，346 个 V1 结果和汇总文件、协议、manifest 及用户原有 .gitignore 均保留。

本验收证明 GPU 环境、固定输入和预训练骨干运行条件已具备。指标、算法、运行器及后续实验继续按既定顺序设计和执行；当前不开展第 3 项修改，等待用户发出“开始第3项”后先提供设计方案。
