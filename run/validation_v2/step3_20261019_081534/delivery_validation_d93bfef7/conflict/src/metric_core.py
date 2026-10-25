"""Exact binary ranking metrics with bounded temporary arrays and grouped ties.

NumPy only. Global sort indices are O(N); gathered and cumulative arrays are
bounded by chunk_size. Input scores retain their precision.
"""
from __future__ import annotations

import operator
import numpy as np

METRIC_POLICY_VERSION = "v2_tie_grouped"
DEFAULT_CHUNK_SIZE = 262144


def finite_scores(values, name="scores") -> np.ndarray:
    scores = np.asarray(values)
    if scores.ndim != 1 or not scores.size:
        raise ValueError(name + " must be a nonempty one-dimensional array")
    if scores.dtype.kind not in "biuf":
        raise ValueError(name + " must contain real numeric values")
    for start in range(0, scores.size, DEFAULT_CHUNK_SIZE):
        if not np.isfinite(scores[start:start + DEFAULT_CHUNK_SIZE]).all():
            raise ValueError(name + " contains NaN or infinity")
    return scores


def binary_inputs(labels, scores) -> tuple[np.ndarray, np.ndarray]:
    scores = finite_scores(scores)
    labels = np.asarray(labels)
    if labels.ndim != 1 or labels.size != scores.size or labels.dtype.kind not in "biuf":
        raise ValueError("labels must be a real 0/1 vector matching scores")
    for start in range(0, labels.size, DEFAULT_CHUNK_SIZE):
        block = labels[start:start + DEFAULT_CHUNK_SIZE]
        if not ((block == 0) | (block == 1)).all():
            raise ValueError("labels must contain only 0 and 1")
    labels = np.ascontiguousarray(labels, dtype=np.uint8)
    positives = int(labels.sum(dtype=np.int64))
    if positives == 0 or positives == labels.size:
        raise ValueError("binary evaluation requires both normal and anomalous samples")
    return labels, np.ascontiguousarray(scores)


def binary_auroc_ap(labels, scores, *, chunk_size=DEFAULT_CHUNK_SIZE) -> tuple[float, float]:
    """AUROC: tied positive/negative pairs get half credit. AP: grouped thresholds.

    An ascending group with p positives and q negatives adds
    p*(lower_negatives + q/2) to the pair count. Its AP contribution is p/P times
    precision at score >= this group. Hold a chunk's last group across boundaries.
    """
    if isinstance(chunk_size, (bool, np.bool_)):
        raise ValueError("chunk_size must be a positive integer")
    try:
        chunk_size = operator.index(chunk_size)
    except TypeError as error:
        raise ValueError("chunk_size must be a positive integer") from error
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    labels, scores = binary_inputs(labels, scores)
    n = labels.size
    positives = int(labels.sum(dtype=np.int64))
    negatives = n - positives
    order = np.argsort(scores, kind="quicksort")
    lower_count = lower_pos = 0
    auc_sum = ap_sum = auc_correction = ap_correction = 0.0

    def accumulate(group_pos, group_size):
        nonlocal lower_count, lower_pos, auc_sum, ap_sum, auc_correction, ap_correction
        if not group_pos.size:
            return
        before_pos = np.cumsum(group_pos, dtype=np.int64) - group_pos
        before_count = np.cumsum(group_size, dtype=np.int64) - group_size
        below_neg = lower_count - lower_pos + before_count - before_pos
        pair_sum = np.sum(group_pos * (below_neg + 0.5 * (group_size - group_pos)), dtype=np.float64)
        precision = (positives - lower_pos - before_pos) / (n - lower_count - before_count)
        ap_part = np.sum((group_pos / positives) * precision, dtype=np.float64)
        value = float(pair_sum) - auc_correction
        updated = auc_sum + value
        auc_correction = (updated - auc_sum) - value
        auc_sum = updated
        value = float(ap_part) - ap_correction
        updated = ap_sum + value
        ap_correction = (updated - ap_sum) - value
        ap_sum = updated
        lower_pos += int(group_pos.sum(dtype=np.int64))
        lower_count += int(group_size.sum(dtype=np.int64))

    pending = None
    for start in range(0, n, chunk_size):
        indices = order[start:start + chunk_size]
        block_scores, block_labels = scores[indices], labels[indices]
        starts = np.concatenate(([0], np.flatnonzero(block_scores[1:] != block_scores[:-1]) + 1))
        sizes = np.diff(np.concatenate((starts, [indices.size]))).astype(np.int64, copy=False)
        pos = np.add.reduceat(block_labels, starts, dtype=np.int64)
        if pending is not None:
            value, last_pos, last_size = pending
            if block_scores[0] == value:
                pos[0] += last_pos
                sizes[0] += last_size
            else:
                accumulate(np.array([last_pos], dtype=np.int64), np.array([last_size], dtype=np.int64))
        pending = (block_scores[-1], int(pos[-1]), int(sizes[-1]))
        accumulate(pos[:-1], sizes[:-1])
    _, last_pos, last_size = pending
    accumulate(np.array([last_pos], dtype=np.int64), np.array([last_size], dtype=np.int64))
    if lower_count != n or lower_pos != positives:
        raise RuntimeError("Grouped metric accounting is inconsistent")
    return float(auc_sum / (positives * negatives)), float(ap_sum)
