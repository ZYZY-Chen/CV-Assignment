"""Synthetic CPU/GPU algorithm acceptance; full completion requires verified TC2."""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROTOCOL_HASH = "3098B6A86DBA64EE439BFE61C7A4FCFFCD082371D5A80FFBC7940997ED6A1ED1"
SOURCES = ["src/padim_adapter.py", "src/patchcore_adapter.py", "src/sampling.py", "src/scoring.py",
           "src/anomaly_postprocess.py", "tests/test_algorithms_tc2_gpu.py", "scripts/slurm/check_tc2_gpu_algorithms.sh",
           "src/metric_core.py", "src/evaluate.py", "src/data.py", "configs/tc2_gpu.json"]
OUTPUT = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def resize_reference(values, height=256, width=256):
    """Independent NumPy bilinear interpolation with half-pixel coordinates."""
    values = np.asarray(values, dtype=np.float64)
    y = np.clip((np.arange(height) + 0.5) * values.shape[-2] / height - 0.5, 0, values.shape[-2] - 1)
    x = np.clip((np.arange(width) + 0.5) * values.shape[-1] / width - 0.5, 0, values.shape[-1] - 1)
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    y1, x1 = np.minimum(y0 + 1, values.shape[-2] - 1), np.minimum(x0 + 1, values.shape[-1] - 1)
    wy, wx = (y - y0)[:, None], (x - x0)[None, :]
    return ((1 - wy) * ((1 - wx) * values[..., y0[:, None], x0] + wx * values[..., y0[:, None], x1])
            + wy * ((1 - wx) * values[..., y1[:, None], x0] + wx * values[..., y1[:, None], x1]))


def gaussian_reference(patches):
    values = resize_reference(patches)
    kernel = np.exp(-np.arange(-16, 17, dtype=np.float64)**2 / 32)
    kernel /= kernel.sum()
    horizontal = np.pad(values, ((0, 0), (0, 0), (16, 16)), mode="reflect")
    values = sum(kernel[i] * horizontal[:, :, i:i + 256] for i in range(33))
    vertical = np.pad(values, ((0, 0), (16, 16), (0, 0)), mode="reflect")
    return sum(kernel[i] * vertical[:, i:i + 256, :] for i in range(33))


def pool_reference(values):
    values = np.asarray(values, dtype=np.float64)
    padded = np.pad(values, ((0, 0), (0, 0), (1, 1), (1, 1)))
    h, w = values.shape[-2:]
    return sum(padded[:, :, i:i + h, j:j + w] for i in range(3) for j in range(3)) / 9


def embedding_reference(features):
    f2, f3 = [pool_reference(features[key].cpu().numpy()) for key in ("layer2", "layer3")]
    return np.concatenate((f2, resize_reference(f3, *f2.shape[-2:])), axis=1)


def nearest_reference(queries, bank, count=1):
    queries, bank = np.asarray(queries, dtype=np.float64), np.asarray(bank, dtype=np.float64)
    distances = np.sqrt(((queries[:, None] - bank[None])**2).sum(axis=-1))
    indices = np.argsort(distances, axis=1, kind="stable")[:, :min(count, len(bank))]
    return np.take_along_axis(distances, indices, axis=1), indices


def native_reference(points, bank, support=9):
    result = []
    for patches in np.asarray(points, dtype=np.float64):
        distances, indices = nearest_reference(patches, bank)
        patch = int(distances[:, 0].argmax())
        reference = int(indices[patch, 0])
        _, neighbors = nearest_reference(np.asarray(bank)[reference:reference + 1], bank, len(bank))
        others = [i for i in neighbors[0] if i != reference][:min(support, len(bank)) - 1]
        selected = np.asarray([reference, *others])
        d = np.linalg.norm(patches[patch] - np.asarray(bank)[selected], axis=1)
        weights = np.exp(d - d.max()); weights /= weights.sum()
        result.append((1 - weights[0]) * distances[patch, 0])
    return np.asarray(result)


def load_implementation():
    global torch, pd, pc, sp, sc, pp
    import torch
    import padim_adapter as pd
    import patchcore_adapter as pc
    import sampling as sp
    import scoring as sc
    import anomaly_postprocess as pp
    torch.set_num_threads(2)


def features(n=6, seed=7, real=False):
    generator = torch.Generator(device="cpu").manual_seed(seed)
    shapes = {"layer1": (64, 64, 64), "layer2": (128, 32, 32), "layer3": (256, 16, 16)} if real else {
        "layer1": (3, 4, 4), "layer2": (3, 2, 2), "layer3": (2, 1, 1)}
    return {key: torch.randn((n, *shape), generator=generator, dtype=torch.float32) * 0.3 for key, shape in shapes.items()}


class AlgorithmCPU(unittest.TestCase):
    def close(self, actual, expected, *, atol=1e-5, rtol=1e-4):
        if isinstance(actual, torch.Tensor):
            actual = actual.detach().cpu().numpy()
        np.testing.assert_allclose(actual, expected, atol=atol, rtol=rtol)

    def test_feature_validation(self):
        base = features()
        for value in (torch.zeros(0, 3, 4, 4), torch.zeros(2, 3, 4), base["layer1"].half(), base["layer1"].double(),
                      torch.full_like(base["layer1"], float("nan")), torch.full_like(base["layer1"], float("inf"))):
            with self.subTest(shape=value.shape, dtype=value.dtype), self.assertRaises(ValueError):
                pd.compose_full_features({**base, "layer1": value})
        with self.assertRaises(ValueError):
            pc.compose_patch_features({"layer2": base["layer2"]})
        with self.assertRaises(ValueError):
            pc.compose_patch_features({**base, "layer3": base["layer3"][:1]})

    def test_padim_alignment_and_dimension_seeds(self):
        base = features()
        for layers, grid in [(("layer1", "layer2", "layer3"), 4), (("layer2", "layer3"), 2), (("layer3",), 1)]:
            composed = pd.compose_full_features(base, layers)
            expected = np.concatenate([np.repeat(np.repeat(base[l].numpy(), grid // base[l].shape[-2], axis=-2),
                                                   grid // base[l].shape[-1], axis=-1) for l in layers], axis=1)
            self.close(composed, expected)
        for seed in (17, 29, 43):
            cfg = pd.PaDiMConfig(n_dims=3, dims_seed=seed)
            model = pd.fit_padim(base, cfg, "cpu")
            expected = torch.randperm(8, generator=torch.Generator().manual_seed(seed))[:3].sort().values
            self.assertTrue(torch.equal(model.dim_indices, expected))
            self.assertEqual(model.info["model_grid_hw"], [4, 4])

    def test_padim_numpy_covariance_and_distances(self):
        x = np.array([[[-1, 2], [1, 0]], [[0, 0], [0, 1]], [[1, -1], [2, -1]],
                      [[2, 1], [-1, 2]], [[-2, -2], [1, 1]], [[1, 3], [-2, 0]]], dtype=np.float32)
        train = {"layer1": torch.from_numpy(x.reshape(6, 2, 1, 2))}
        cfg = pd.PaDiMConfig(n_dims=2, layers=("layer1",), position_chunk_size=1)
        model = pd.fit_padim(train, cfg, "cpu")
        samples = x.transpose(0, 2, 1).astype(np.float64)
        means = samples.mean(axis=0)
        inverse = np.stack([np.linalg.inv(np.cov(samples[:, p, :], rowvar=False, ddof=1) + 0.01 * np.eye(2)) for p in range(2)])
        self.close(model.means, means); self.close(model.inv_covs, inverse)
        test = {"layer1": train["layer1"][:2] + 0.2}
        delta = test["layer1"].numpy().reshape(2, 2, 2).transpose(0, 2, 1) - means
        raw = np.sqrt(np.maximum(np.einsum("npd,pde,npe->np", delta, inverse, delta), 0)).reshape(2, 1, 2)
        prediction = pd.predict_padim(model, test, cfg)
        self.close(prediction["anomaly_maps"], gaussian_reference(raw))
        self.close(prediction["image_scores"]["native"], prediction["anomaly_maps"].amax((1, 2)).numpy())

    def test_padim_square_root_and_chunks(self):
        train = {"layer1": torch.tensor([-1.0, 1.0]).reshape(2, 1, 1, 1)}
        cfg = pd.PaDiMConfig(n_dims=1, layers=("layer1",))
        model = pd.fit_padim(train, cfg, "cpu")
        prediction = pd.predict_padim(model, {"layer1": torch.tensor([3.0]).reshape(1, 1, 1, 1)}, cfg)
        self.close(prediction["anomaly_maps"], np.full((1, 256, 256), 3 / np.sqrt(2.01)))
        base = features(); cfg = pd.PaDiMConfig(n_dims=3, position_chunk_size=1)
        left = pd.fit_padim(base, cfg, "cpu")
        right = pd.fit_padim(base, replace(cfg, position_chunk_size=7), "cpu")
        self.close(left.inv_covs, right.inv_covs.numpy())
        self.close(pd.predict_padim(left, base, cfg)["anomaly_maps"],
                   pd.predict_padim(right, base, replace(cfg, position_chunk_size=7))["anomaly_maps"].numpy())

    def test_padim_bad_configuration_and_state(self):
        base = features()
        for cfg in (pd.PaDiMConfig(n_dims=0), pd.PaDiMConfig(n_dims=9), pd.PaDiMConfig(eps=0),
                    pd.PaDiMConfig(layers=()), pd.PaDiMConfig(dims_seed=True), pd.PaDiMConfig(position_chunk_size=0)):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                pd.fit_padim(base, cfg, "cpu")
        with self.assertRaises(ValueError):
            pd.fit_padim(features(1), pd.PaDiMConfig(n_dims=2), "cpu")
        cfg = pd.PaDiMConfig(n_dims=3); model = pd.fit_padim(base, cfg, "cpu")
        with self.assertRaises(ValueError):
            pd.predict_padim(model, base, replace(cfg, dims_seed=29))
        with self.assertRaises(ValueError):
            pd.predict_padim(model, {**base, "layer2": torch.zeros(6, 3, 3, 3)}, cfg)

    def test_patchcore_both_pooling_and_alignment(self):
        base = features()
        self.close(pc.compose_patch_features(base), embedding_reference(base))
        ones = {"layer2": torch.ones(1, 1, 4, 4), "layer3": torch.ones(1, 1, 2, 2)}
        actual = pc.compose_patch_features(ones)
        self.close(actual, embedding_reference(ones))
        self.assertAlmostEqual(float(actual[0, 0, 0, 0]), 4 / 9, places=6)
        self.assertAlmostEqual(float(actual[0, 1, 1, 1]), 4 / 9, places=6)

    def test_sampling_counts_and_invalid_inputs(self):
        bank = torch.arange(15, dtype=torch.float32).reshape(5, 3)
        self.assertEqual(sp.retained_count(5, 0.5), 2)
        self.assertEqual(sp.retained_count(5, 0.001), 1)
        self.assertEqual(sp.retained_count(5, 1), 5)
        for ratio in (0, -1, 1.1, float("nan"), True):
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                sp.kcenter_coreset(bank, ratio, "cpu")
        for count in (0, 6, 1.5, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                sp.random_subset(bank, count, "cpu")

    def test_coreset_all_duplicates_and_exact_ties(self):
        bank = torch.zeros(7, 3)
        for chunk in (1, 2, 20):
            selected, indices = sp.kcenter_coreset(bank, 1, "cpu", 17, chunk_size=chunk, return_indices=True)
            first = int(torch.randint(7, (1,), generator=torch.Generator().manual_seed(17)))
            self.assertEqual(indices.tolist(), [first] + [i for i in range(7) if i != first])
            self.assertEqual(len(indices.unique()), 7)
            self.assertTrue(torch.equal(selected, bank[indices]))

    def test_coreset_against_independent_greedy(self):
        bank = torch.tensor([-4, -2, -1, 0, 3, 7], dtype=torch.float32).reshape(-1, 1)
        first = int(torch.randint(6, (1,), generator=torch.Generator().manual_seed(29)))
        expected = [first]
        for _ in range(2):
            d = ((bank.numpy()[:, None] - bank.numpy()[expected][None])**2).sum(-1).min(1)
            d[expected] = -np.inf
            expected.append(int(d.argmax()))
        for chunk in (1, 3, 20):
            _, indices = sp.kcenter_coreset(bank, 0.5, "cpu", 29, chunk_size=chunk, return_indices=True)
            self.assertEqual(indices.tolist(), expected)

    def test_random_sampling_and_fit_evidence(self):
        base = features(2); saved = {k: v.clone() for k, v in base.items()}
        bank = pc.compose_patch_features(base).permute(0, 2, 3, 1).reshape(-1, 5)
        for strategy in ("random", "coreset"):
            cfg = pc.PatchCoreConfig(coreset_ratio=0.5, sampling=strategy, sampling_seed=17)
            model = pc.fit_patchcore(base, cfg, "cpu")
            indices = model.info["retained_indices"]
            self.assertEqual(len(indices), 4); self.assertEqual(len(set(indices)), 4)
            self.close(model.bank, bank[indices].numpy())
            self.assertEqual(model.info["sampling_seed"], 17)
        expected = torch.randperm(len(bank), generator=torch.Generator().manual_seed(43))[:3]
        _, actual = sp.random_subset(bank, 3, "cpu", 43, return_indices=True)
        self.assertTrue(torch.equal(actual, expected))
        for key in base:
            self.assertTrue(torch.equal(saved[key], base[key]))

    def test_neighbors_against_full_matrix_and_chunk_changes(self):
        bank = torch.tensor([[0, 0], [0, 0], [2, 0], [-2, 0], [3, 1]], dtype=torch.float32)
        queries = torch.tensor([[0, 0], [1, 0], [0, 2]], dtype=torch.float32)
        for count in (1, 3, 9):
            expected, indices = nearest_reference(queries.numpy(), bank.numpy(), count)
            for q_chunk, b_chunk in ((1, 1), (2, 2), (100, 4), (100, 100)):
                actual, selected = pc.nearest_neighbors(queries, bank, count, query_chunk_size=q_chunk, bank_chunk_size=b_chunk)
                self.close(actual, expected)
                np.testing.assert_array_equal(selected.numpy(), indices)

    def test_native_formula_small_banks_and_support_ties(self):
        points = torch.tensor([[[0.5, 0], [3, 2]], [[1, 0], [0, 4]]], dtype=torch.float32)
        for size in (1, 2, 8, 9, 12):
            bank = torch.stack((torch.arange(size, dtype=torch.float32), torch.zeros(size)), dim=1)
            distances, indices = pc.nearest_neighbors(points.reshape(-1, 2), bank)
            cfg = pc.PatchCoreConfig(query_chunk_size=1, bank_chunk_size=2)
            actual = pc._native_scores(points, distances.reshape(2, 2), indices.reshape(2, 2), bank, cfg)
            self.close(actual, native_reference(points.numpy(), bank.numpy()))
        bank = torch.zeros(12, 2)
        distances, indices = pc.nearest_neighbors(points.reshape(-1, 2), bank)
        self.close(pc._native_scores(points, distances.reshape(2, 2), indices.reshape(2, 2), bank, cfg),
                   native_reference(points.numpy(), bank.numpy()))

    def test_patchcore_final_map_and_native_are_separate(self):
        base = {"layer2": torch.zeros(2, 1, 4, 4), "layer3": torch.zeros(2, 1, 2, 2)}
        bank = torch.tensor([[1, 0], [2, 0], [3, 0]], dtype=torch.float32)
        model = pc.PatchCoreModel(bank, torch.device("cpu"))
        cfg = pc.PatchCoreConfig(query_chunk_size=1, bank_chunk_size=1, chunk_size=1)
        result = pc.predict_patchcore(model, base, cfg)
        self.close(result["anomaly_maps"], np.ones((2, 256, 256)))
        self.close(result["image_scores"]["native"], native_reference(np.zeros((2, 16, 2)), bank.numpy()))
        self.assertGreater(float((result["image_scores"]["max"] - result["image_scores"]["native"]).min()), 0.01)
        self.close(result["anomaly_maps"], pc.anomaly_maps(model, base, cfg).numpy())
        other = pc.predict_patchcore(model, base, replace(cfg, query_chunk_size=100, bank_chunk_size=100, chunk_size=20))
        for rule in sc.TC2_GPU_RULES:
            self.close(other["image_scores"][rule], result["image_scores"][rule].numpy())

    def test_patchcore_nonconstant_reference(self):
        base = features(2, seed=37)
        bank = torch.tensor(np.random.default_rng(3).normal(size=(12, 5)), dtype=torch.float32)
        cfg = pc.PatchCoreConfig(query_chunk_size=3, bank_chunk_size=4)
        result = pc.predict_patchcore(pc.PatchCoreModel(bank, torch.device("cpu")), base, cfg)
        embedding = embedding_reference(base)
        points = embedding.transpose(0, 2, 3, 1).reshape(2, 4, 5)
        distances, _ = nearest_reference(points.reshape(-1, 5), bank.numpy())
        self.close(result["anomaly_maps"], gaussian_reference(distances.reshape(2, 2, 2)))
        self.close(result["image_scores"]["native"], native_reference(points, bank.numpy()))

    def test_postprocessing_constants_impulses_and_boundaries(self):
        maps = np.zeros((3, 5, 7), dtype=np.float32)
        maps[0] = 2.5; maps[1, 2, 3] = 1; maps[2, 0, 0] = 1
        saved = maps.copy()
        actual = pp.postprocess_anomaly_maps(torch.from_numpy(maps))
        self.close(actual, gaussian_reference(maps))
        self.close(actual[0], np.full((256, 256), 2.5))
        np.testing.assert_array_equal(maps, saved)

    def test_five_scoring_rules_and_legacy_default(self):
        maps = torch.arange(2 * 256 * 256, dtype=torch.float32).reshape(2, 256, 256) / 1000
        native = torch.tensor([0.2, 0.3], dtype=torch.float32)
        saved = maps.clone(); result = sc.aggregate_batch(maps, sc.TC2_GPU_RULES, native_scores=native)
        self.assertEqual(tuple(result), sc.TC2_GPU_RULES)
        self.assertEqual(tuple(sc.aggregate_batch(maps)), sc.RULES)
        for rule, fraction in (("top_0.001", 0.001), ("top_0.01", 0.01), ("top_0.05", 0.05)):
            count = int(np.ceil(fraction * 256 * 256))
            expected = np.sort(maps.numpy().reshape(2, -1), axis=1)[:, -count:].astype(np.float64).mean(1)
            self.close(result[rule], expected)
        self.assertTrue(torch.equal(maps, saved))
        self.assertTrue(torch.equal(sc.to_image_score_grid(maps), maps))
        with self.assertRaises(ValueError):
            sc.aggregate_batch(maps, sc.TC2_GPU_RULES)
        with self.assertRaises(ValueError):
            sc.aggregate_batch(maps, sc.TC2_GPU_RULES, native_scores=native[:1])
        self.close(sc.aggregate(maps[0], "native", native_score=0.2), 0.2)

    def test_autocast_disabled_and_input_preservation(self):
        base = features(); saved = {k: v.clone() for k, v in base.items()}
        cfg = pd.PaDiMConfig(n_dims=3)
        with torch.autocast("cpu", dtype=torch.bfloat16):
            model = pd.fit_padim(base, cfg, "cpu"); result = pd.predict_padim(model, base, cfg)
        self.assertEqual(model.inv_covs.dtype, torch.float32)
        self.assertEqual(result["anomaly_maps"].dtype, torch.float32)
        self.close(pd.anomaly_maps_padim(model, base, cfg), result["anomaly_maps"].numpy())
        for key in base:
            self.assertTrue(torch.equal(base[key], saved[key]))

    def test_invalid_patchcore_state_and_execution(self):
        base = features()
        for cfg in (pc.PatchCoreConfig(sampling="invalid"), pc.PatchCoreConfig(query_chunk_size=0),
                    pc.PatchCoreConfig(bank_chunk_size=True), pc.PatchCoreConfig(num_neighbors=0)):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                pc.fit_patchcore(base, cfg, "cpu")
        with self.assertRaises(ValueError):
            pc.predict_patchcore(pc.PatchCoreModel(), base, pc.PatchCoreConfig())
        with self.assertRaises(ValueError):
            pc.nearest_neighbors(torch.zeros(1, 2), torch.zeros(1, 3))
        with self.assertRaises(ValueError):
            pp.postprocess_anomaly_maps(torch.ones(1, 2, 2).half())

    def test_evaluation_bridge_with_five_scores(self):
        from PIL import Image
        import evaluate
        root = OUTPUT / "evaluation_fixture"; root.mkdir()
        Image.fromarray(np.full((4, 5), 255, dtype=np.uint8)).save(root / "mask.png")
        items = [dict(path="test/good/0.png", label=0, defect_type="good", mask_paths=[], orig_hw=(4, 5)),
                 dict(path="test/bad/0.png", label=1, defect_type="bad", mask_paths=["mask.png"], orig_hw=(4, 5))]
        dev = [dict(path=f"dev/good/{i}.png", label=0, defect_type="good", mask_paths=[], orig_hw=(4, 5)) for i in range(2)]
        base = features(2); model = pc.fit_patchcore(base, pc.PatchCoreConfig(coreset_ratio=0.5), "cpu")
        prediction = pc.predict_patchcore(model, base, pc.PatchCoreConfig(coreset_ratio=0.5))
        scores = {r: v.numpy() for r, v in prediction["image_scores"].items()}
        result = evaluate.evaluate_all(items, dev, prediction["anomaly_maps"], prediction["anomaly_maps"], scores, scores, root, torch.device("cpu"))
        self.assertEqual(set(result["image"]), set(sc.TC2_GPU_RULES))
        self.assertTrue(np.isfinite(result["pixel"]["pixel_auroc"]))
        four = {r: scores[r] for r in sc.RULES}
        other = evaluate.evaluate_all(items, dev, prediction["anomaly_maps"], prediction["anomaly_maps"], four, four, root, torch.device("cpu"))
        self.assertEqual(result["pixel"], other["pixel"])


class AlgorithmGPU(unittest.TestCase):
    def test_cpu_gpu_numerical_agreement(self):
        base = features(12, seed=123)
        gpu = {k: v.to("cuda") for k, v in base.items()}
        for method in ("padim", "patchcore"):
            cfg = pd.PaDiMConfig(n_dims=3) if method == "padim" else pc.PatchCoreConfig(coreset_ratio=0.5, sampling="random", sampling_seed=17)
            fit = pd.fit_padim if method == "padim" else pc.fit_patchcore
            predict = pd.predict_padim if method == "padim" else pc.predict_patchcore
            cpu_model, gpu_model = fit(base, cfg, "cpu"), fit(gpu, cfg, "cuda")
            cpu_prediction, gpu_prediction = predict(cpu_model, base, cfg), predict(gpu_model, gpu, cfg)
            np.testing.assert_allclose(gpu_prediction["anomaly_maps"].cpu().numpy(), cpu_prediction["anomaly_maps"].numpy(), atol=1e-4, rtol=1e-4)
            for rule in sc.TC2_GPU_RULES:
                np.testing.assert_allclose(gpu_prediction["image_scores"][rule].cpu().numpy(), cpu_prediction["image_scores"][rule].numpy(), atol=1e-4, rtol=1e-4)
            key = "dim_indices" if method == "padim" else "retained_indices"
            self.assertEqual(cpu_model.info[key], gpu_model.info[key])

    def test_real_feature_shapes_and_frozen_variants(self):
        base = {k: v.to("cuda") for k, v in features(4, real=True).items()}
        for layers, dimensions, grid in [(("layer1", "layer2", "layer3"), d, 64) for d in (50, 100, 200)] + [(("layer2", "layer3"), 100, 32), (("layer3",), 100, 16)]:
            with self.subTest(layers=layers, dimensions=dimensions):
                cfg = pd.PaDiMConfig(n_dims=dimensions, layers=layers)
                model = pd.fit_padim(base, cfg, "cuda")
                with torch.autocast("cuda", dtype=torch.float16):
                    prediction = pd.predict_padim(model, {k: v[:1] for k, v in base.items()}, cfg)
                self.assertEqual(model.info["model_grid_hw"], [grid, grid])
                self.assertEqual(model.inv_covs.dtype, torch.float32)
                self.assertEqual(tuple(prediction["anomaly_maps"].shape), (1, 256, 256))
                self.assertEqual(prediction["anomaly_maps"].dtype, torch.float32)
                self.assertTrue(bool(torch.isfinite(prediction["anomaly_maps"]).all()))
                del model, prediction
        for strategy in ("coreset", "random"):
            cfg = pc.PatchCoreConfig(sampling=strategy, sampling_seed=17)
            model = pc.fit_patchcore({k: v[:2] for k, v in base.items()}, cfg, "cuda")
            prediction = pc.predict_patchcore(model, {k: v[:1] for k, v in base.items()}, cfg)
            self.assertEqual(model.info["model_grid_hw"], [32, 32])
            self.assertEqual(model.bank.shape[1], 384)
            self.assertEqual(len(model.bank), round(0.05 * 2 * 32 * 32))
            self.assertEqual(len(set(model.info["retained_indices"])), len(model.bank))
            self.assertEqual(set(prediction["image_scores"]), set(sc.TC2_GPU_RULES))
            self.assertEqual(prediction["anomaly_maps"].dtype, torch.float32)
            self.assertTrue(bool(torch.isfinite(prediction["anomaly_maps"]).all()))


def contract(full):
    protocol_path = ROOT / "configs/protocol_v2.json"
    if sha(protocol_path) != PROTOCOL_HASH:
        raise ValueError("Frozen protocol changed")
    protocol = json.loads(protocol_path.read_text())
    for manifest in protocol["data"]["frozen_manifests"]:
        if sha(ROOT / manifest["path"]) != manifest["file_sha256"]:
            raise ValueError("Frozen manifest changed")
    if full:
        if platform.system() != "Linux" or not os.environ.get("SLURM_JOB_ID", "").isdigit():
            raise RuntimeError("Full algorithm acceptance requires a Linux SLURM compute job")
        if any(not (ROOT / name).is_file() for name in SOURCES):
            raise RuntimeError("The approved eleven-file algorithm payload is incomplete")
        naming = json.loads((ROOT / "configs/tc2_gpu.json").read_text())
        if naming["workflow_id"] != "tc2_gpu" or naming["frozen_protocol"]["sha256"] != PROTOCOL_HASH:
            raise RuntimeError("Workflow naming map differs from the frozen protocol alias")
        setup = json.loads((ROOT / "configs/tc2_setup.json").read_text())
        if ROOT != Path(setup["remote"]["setup_root"]) or Path(sys.prefix) != Path(setup["remote"]["conda_environment_prefix"]):
            raise RuntimeError("Use the verified TC2 staging root and environment")
        if os.environ.get("SLURM_JOB_PARTITION") != setup["remote"]["partition"]:
            raise RuntimeError("Allocated partition differs from verified setup")
        pointer = ROOT / "run/validation_tc2_gpu/last_check_metrics_job.txt"
        job = pointer.read_text().strip()
        if not job.isdigit():
            raise RuntimeError("Invalid metric regression job ID")
        metrics = json.loads((ROOT / f"run/validation_tc2_gpu/step3_job_{job}/setup_status.json").read_text())
        if not metrics["step_3_complete"] or metrics["mode"] != "full" or metrics["status"] != "passed":
            raise RuntimeError("Current metric regression has not passed")
        for name in ("src/metric_core.py", "src/evaluate.py", "src/data.py"):
            if sha(ROOT / name) != metrics["source_hashes"][name]:
                raise RuntimeError("Read-only metric dependency differs from accepted regression")
        setup_root = ROOT / "run/setup_tc2_gpu"
        last = setup_root / "last_check_all_job.txt"
        if not last.exists():
            last = ROOT / "run/setup_v2/last_check_all_job.txt"
        all_job = last.read_text().strip()
        if not all_job.isdigit():
            raise RuntimeError("Invalid step-2 acceptance job ID")
        ready = setup_root / f"job_{all_job}_all/setup_status.json"
        if not ready.exists():
            ready = ROOT / f"run/setup_v2/job_{all_job}_all/setup_status.json"
        acceptance = json.loads(ready.read_text())
        if not acceptance["step_2_complete"]:
            raise RuntimeError("Step-2 all acceptance has not passed")
        for entry in acceptance["environment_export"]["files"]:
            if sha(ROOT / Path(entry["path"]).name) != entry["sha256"]:
                raise RuntimeError("Actual environment lock changed")
        expected = {"numpy": "1.26.4", "scikit-learn": "1.7.2", "torch": "2.11.0+cu128", "torchvision": "0.26.0+cu128", "pillow": "12.3.0"}
        if {name: metadata.version(name) for name in expected} != expected or sys.version_info[:2] != (3, 10):
            raise RuntimeError("Acceptance environment differs from approved versions")
    load_implementation()
    runtime = {"python": sys.version, "numpy": np.__version__, "torch": torch.__version__, "protocol_sha256": PROTOCOL_HASH,
               "frozen_manifests_verified": 8, "gpu_requested": full, "device": "cuda" if full else "cpu"}
    if full:
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("Exactly one allocated visible CUDA GPU is required; no CPU fallback")
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        runtime.update(slurm_job_id=os.environ["SLURM_JOB_ID"], metric_regression_job_id=job,
                       step_2_job_id=all_job, gpu=torch.cuda.get_device_name(0), cuda_build=torch.version.cuda,
                       matmul_tf32=False, cudnn_tf32=False, autocast_enabled=False)
    return runtime


def run_suite(test_class, filename):
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_class)
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    text = log.getvalue(); print(text)
    (OUTPUT / filename).write_text(text, encoding="utf-8")
    return {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped), "passed": result.wasSuccessful() and not result.skipped,
            "failure_details": [{"test": test.id(), "traceback": trace} for test, trace in result.failures + result.errors]}


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cpu", "full"), default="full")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(); OUTPUT = args.output_dir.resolve()
    allowed = (ROOT / "run/validation_tc2_gpu").resolve()
    if OUTPUT == allowed or not OUTPUT.is_relative_to(allowed) or OUTPUT.exists():
        parser.error("Use a fresh directory strictly under run/validation_tc2_gpu")
    OUTPUT.mkdir(parents=True)
    status = {"mode": args.mode, "status": "failed", "step_4_complete": False, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        status["runtime"] = contract(args.mode == "full")
        status["cpu"] = run_suite(AlgorithmCPU, "cpu_tests.txt")
        if status["cpu"]["passed"] and args.mode == "full":
            status["gpu"] = run_suite(AlgorithmGPU, "gpu_tests.txt")
        passed = status["cpu"]["passed"] and (args.mode == "cpu" or status.get("gpu", {}).get("passed", False))
        status.update(status="passed" if passed else "failed", step_4_complete=passed and args.mode == "full")
    except Exception as error:
        status["error"] = type(error).__name__ + ": " + str(error)
    status["source_hashes"] = {name: sha(ROOT / name) for name in SOURCES if (ROOT / name).is_file()}
    (OUTPUT / "setup_status.json").write_text(json.dumps(status, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2, allow_nan=False))
    return 0 if status["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
