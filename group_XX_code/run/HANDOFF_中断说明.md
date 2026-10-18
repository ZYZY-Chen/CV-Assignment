# 实验中断说明（交接到此请先读）

## 中断原因
2026-10-18 上午批量跑实验时，本机三次蓝屏 **HYPERVISOR_ERROR (0x00020001)**，
WER 同时记录 **WHEA_UNCORRECTABLE_ERROR (0x124)**，故障设备为独显
NVIDIA RTX 5050 Laptop（PCI VEN_10DE&DEV_2D98）。系统已开启 VBS/内存完整性，
且该机历史上另有 5 次 VIDEO_MEMORY_MANAGEMENT_INTERNAL (0x10E) 蓝屏，
属于 **GPU 驱动/硬件/虚拟化层稳定性问题，不是代码逻辑问题**，但 CUDA 负载
（尤其大块 cdist 显存分配）会触发。

## 恢复前建议
1. 优先用 **CPU 跑**（无蓝屏风险，速度慢但可靠）：
   `python run.py --config configs/xxx.yaml --dataset mvtec_ad --category bottle --device cpu`
   批量：`python scripts/run_experiments.py --device cpu`
2. 若继续用 GPU：先更新 NVIDIA 驱动 / 考虑关闭「内存完整性」（需管理员）；
   不要同时开两个 CUDA 进程；避免全量记忆库（45k 点）的大 cdist。
3. 批量脚本幂等：有 SUCCESS 标记的运行会自动跳过，可直接续跑。

## 已完成（7 个运行，均有 SUCCESS）
- B0 bottle patchcore / padim（指标与文献吻合：patchcore 图像 AUROC 1.0000、
  像素 0.9802；padim 0.9984、0.9833）
- B0 cable patchcore / padim
- B0 capsule patchcore / padim
- B0 screw patchcore（padim 跑到一半被打断，需重跑）
- B0 tile、wood、LOCO 两类，以及 R0/H1/H2/C1/C1R/C2/F1 均未开始

## 待办/待确认
1. **cable/capsule 图像级 max AUROC 偏低**（capsule 0.88、cable 0.90），
   像素 AUROC 却与文献吻合（0.98）。初步诊断：N=100 + coreset 5% 下记忆库
   稀疏导致，疑似少样本协议的正常现象（F1/H2 正是要刻画它），但尚未完成
   对照实验（全库 / 全训练量 / 随机采样），见 scripts/debug_variant.py 的设计。
   `scripts/debug_variant.py` 中的全库大 cdist 可能就是第三次蓝屏诱因，
   复跑时请减小 chunk 或改 CPU。
2. 临时诊断脚本：scripts/debug_border.py、scripts/debug_variant.py
   （提交前可删）。
3. 汇总：全部跑完后执行 `python scripts/aggregate_results.py`。
4. AUPRO 未实现（手册标注可选）。

## 环境
- 解释器：D:\Anaconda\envs\ca6129-ad\python.exe
- 特征缓存 8 类已全部提取完毕（run/feature_cache/，约 2.1GB）
