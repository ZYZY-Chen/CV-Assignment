# -*- coding: utf-8 -*-
"""临时诊断：全库/coreset/随机 + 全训练量 对图像 AUROC 的影响（精简版）"""
import sys
from pathlib import Path
import numpy as np, torch
import torch.nn.functional as F
root = Path(r'C:\Users\theho\Documents\计算机视觉课程\小组作业\group_XX_code')
sys.path.insert(0, str(root / 'src'))
from data import Manifest
from feature_cache import load_features, cache_path
from sampling import kcenter_coreset, random_subset
from scoring import aggregate_batch
from sklearn.metrics import roc_auc_score
dev = torch.device('cuda')
CACHE = root / 'run' / 'feature_cache'
DATA = (root / '..' / 'datasets').resolve()

def compose(feats):
    f2, f3 = feats['layer2'], feats['layer3']
    f2 = F.avg_pool2d(f2, 3, 1, 1)[:, :, ::2, ::2]
    return torch.cat([f2, f3], 1)

def score(x, xt, core):
    N, _, H, W = x.shape
    q = xt.permute(0, 2, 3, 1).reshape(xt.shape[0], H * W, x.shape[1])
    maps = []
    with torch.inference_mode():
        for s in range(0, q.shape[0], 128):
            d = torch.cdist(q[s:s + 128], core)
            topk, _ = d.topk(9, dim=2, largest=False)
            w = 1 - torch.exp(-topk[..., :1] / 2)
            maps.append((w * topk.mean(2, keepdim=True)).squeeze(-1)
                        .reshape(-1, H, W).cpu())
    return torch.cat(maps)

def variant(cat, n_fit, samp, ratio, label):
    m = Manifest(root / 'manifests' / f'manifest_mvtec_ad_{cat}.json', DATA)
    fit_items = m.fit_items(17, n_fit)
    fit = load_features(cache_path(CACHE, m.dataset, cat),
                        [x['path'] for x in fit_items], layers=('layer2', 'layer3'))
    test = load_features(cache_path(CACHE, m.dataset, cat),
                         [x['path'] for x in m.test_items()],
                         layers=('layer2', 'layer3'))
    labels = np.array([x['label'] for x in m.test_items()])
    x = compose(fit).to(dev); xt = compose(test).to(dev)
    N, _, H, W = x.shape
    bank = x.permute(0, 2, 3, 1).reshape(N * H * W, x.shape[1])
    if samp == 'all':
        core = bank
    elif samp == 'core':
        core = kcenter_coreset(bank, ratio, device=dev, seed=0)
    else:
        core = random_subset(bank, int(round(bank.shape[0] * ratio)),
                             device=dev, seed=0)
    maps = score(x, xt, core)
    sc = aggregate_batch(maps.float())
    print(f'{cat:<8} N={len(fit_items):<3} {label:<14} max={roc_auc_score(labels, sc["max"]):.4f} '
          f'top1={roc_auc_score(labels, sc["top_0.01"]):.4f}', flush=True)

for cat in ['capsule', 'cable']:
    variant(cat, 100, 'core', 0.05, 'core05')
    variant(cat, 100, 'random', 0.05, 'rand05')
    variant(cat, 100, 'all', 1.0, 'all')
    variant(cat, 100000, 'all', 1.0, 'all-fulltrain')
