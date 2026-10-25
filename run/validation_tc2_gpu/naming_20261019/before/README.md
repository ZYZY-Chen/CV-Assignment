# CA6129 工业异常检测小组作业

比较 PaDiM 和 PatchCore。实验代码在这个目录，图片不放进 Git 仓库。

## V2 experiment protocol and historical results

The corrected experiment protocol is frozen as V2. See [EXPERIMENT_PROTOCOL_V2.md](docs/EXPERIMENT_PROTOCOL_V2.md) for its explanation and [protocol_v2.json](configs/protocol_v2.json) for the machine-readable configuration. The 66 existing runs are registered as V1 historical results, with file fingerprints in [legacy_v1_inventory.json](run/legacy_v1_inventory.json).

Subsequent formal experiments use the TC2 GPU cluster, with V2 outputs under `run/v2/`. The runner has not yet integrated the V2 protocol or output directories. Models, caches, and job execution will be corrected and validated under the approved designs of their respective later steps; independent acceptance of metric corrections was completed in step 3. V1 results and SUCCESS markers do not establish V2 completion.

## TC2 GPU environment and input acceptance

See [TC2_SETUP_V2.md](docs/TC2_SETUP_V2.md) for step-2 preparation and acceptance, and [tc2_setup.json](configs/tc2_setup.json) for verified settings and status. Checks use [check_setup_v2.py](scripts/check_setup_v2.py) and its [SLURM entry point](scripts/slurm/check_setup_v2.sh), saving records in `run/setup_v2/`.

GPU checks must run within compute-node jobs. The acceptance tool checks prepared inputs and environments only. The actual cluster environment passed checks and was exported as [environment-tc2.yml](environment-tc2.yml) and [requirements-tc2-lock.txt](requirements-tc2-lock.txt). Rebuild using those exports together with the official cu128 package source and installation order in the preparation instructions. Existing Windows/CUDA dependency files remain historical records.

Step 2 completed on 2026-10-19: final combined acceptance job 43950 on TC2N01 finished as COMPLETED / 0:0 with `step_2_complete=true`. All frozen hashes for 3650 images and 1019 masks matched, and checks of the specified weights, CUDA FP32 operations, and three ResNet18 feature layers passed. The actual environment uses NVIDIA A40, driver 570.148.08, glibc 2.34, Python 3.10.22, and torch 2.11.0+cu128 / torchvision 0.26.0+cu128. See the [step-2 acceptance record](run/setup_v2/step2_20261019_060542/setup_status.json) for complete status.

The user-approved preparation workflow uses separate [environment preparation](scripts/prepare_tc2_environment_v2.sh), [input preparation](scripts/prepare_tc2_inputs_v2.py), [short hardware job](scripts/slurm/probe_hardware_v2.sh), and [preparation job entry point](scripts/slurm/prepare_tc2_v2.sh) scripts. AD uses the specified complete Hugging Face package at a fixed revision and hash, extracting only six categories. The two LOCO categories and weights retain official sources. See sections 6.4 and 6.7 of the preparation instructions for local operation and log retrieval. Submit SLURM jobs from the verified preparation directory.

## V2 metric corrections and step-3 acceptance

The user-approved step-3 design is documented in [METRICS_V2.md](docs/METRICS_V2.md). [metric_core.py](src/metric_core.py) implements exact AUROC/AP with tied scores grouped by threshold. [evaluate.py](src/evaluate.py) adds normal-development thresholds, input validation, and LOCO groups while preserving existing result fields and adding `metric_policy.version=v2_tie_grouped`. Evaluation accepts the original four image scores and a subsequently supplied native score; model score generation remains in later steps.

Step 3 completed on 2026-10-19. All nine local NumPy core checks passed. CPU acceptance job 43956 on TC2N01 finished as COMPLETED / 0:0, with all 24 full tests passing and `step_3_complete=true`. Across 81 scikit-learn comparisons, maximum AUROC/AP absolute errors were 1.11e-16 / 2.22e-16, below the 1e-12 limit. The returned archive's 100 files, five source fingerprints, and change scope were independently verified. See the [step-3 acceptance record](run/validation_v2/step3_20261019_081534/setup_status.json) for final status and the metric document for the complete design, commands, and evidence. No acceptance-job resubmission is required.

## 数据集

只用 MVTec AD 的 bottle、cable、capsule、screw、tile、wood，以及 MVTec LOCO 的 juice_bottle、screw_bag。许可是 CC BY-NC-SA 4.0，仅限非商业用途。

官方下载页：

- MVTec AD：https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads
- MVTec LOCO：https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads

The V1 downloader usage is retained below. It uses legacy official direct links, some of which now return 404. Follow the TC2 instructions above for V2 input preparation; accepted data is in the remote preparation directory's `datasets/`. The old command extracts into the local parent directory's `datasets/` by default:

```powershell
python scripts/download_datasets.py --accept-license
```

本机已经有图片时会跳过。下载完成后的目录是：

```
datasets/
├── mvtec_ad/<category>/
└── mvtec_loco/<category>/
```

## V1 historical usage: reproduce B0 on the local CPU

The retained legacy example below writes to the V1 results directory; use the separately approved cluster workflow for V2 execution.

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"
python run.py --config configs/b0_patchcore.yaml --dataset mvtec_ad --category bottle --device cpu
```

这台笔记本的独显在大块距离计算时蓝屏过，实验请加 `--device cpu`，并把 `CUDA_VISIBLE_DEVICES` 设为 `-1`。进展、已知问题和计时见 `run/HANDOFF_续作说明.md`。
