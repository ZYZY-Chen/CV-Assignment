# -*- coding: utf-8 -*-
"""临时诊断：max 图像分数是否受边界热点主导"""
import sys
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score
root = Path(r'C:\Users\theho\Documents\计算机视觉课程\小组作业\group_XX_code\run\results')
for rid in ['B0_capsule_patchcore_s17_n100', 'B0_capsule_padim_s17_n100',
            'B0_cable_patchcore_s17_n100', 'B0_cable_padim_s17_n100']:
    z = np.load(root / rid / 'predictions.npz', allow_pickle=True)
    labels = z['test_labels']; maps = z['test_maps'].astype(np.float32)
    N = len(maps); flat = maps.reshape(N, -1)
    auc_full = roc_auc_score(labels, flat.max(1))
    for strip in (1, 2):
        inner = maps[:, strip:16-strip, strip:16-strip].reshape(N, -1)
        auc_in = roc_auc_score(labels, inner.max(1))
        print(f'{rid:<40} strip={strip} 去边max={auc_in:.4f}')
    amax = flat.argmax(1); yy, xx = amax // 16, amax % 16
    border = (yy == 0) | (yy == 15) | (xx == 0) | (xx == 15)
    print(f'   full max={auc_full:.4f}  正常图max在边界={border[labels==0].mean():.2f}  '
          f'异常图={border[labels==1].mean():.2f}')
    # 按行统计平均热点位置
    rowmean = maps.mean(0).mean(1)
    print('   16 行平均分数: ', np.round(rowmean, 2))
