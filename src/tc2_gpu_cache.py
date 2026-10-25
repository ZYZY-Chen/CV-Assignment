"""Immutable FP32 layer caches with ordered reads and offline local weights."""
from __future__ import annotations

from pathlib import Path
import shutil
import time
import uuid
import numpy as np
from tc2_gpu_protocol import (CACHE_SOURCES, EXECUTION, PROTOCOL_SHA256, SHAPES, accepted_inputs,
    digest, exclusive, fingerprints, image_entries, inside, manifest, prepare_torch,
    read_json, sha, versions, write_json)


def cache_identity(ctx, value, manifest_sha256, runtime=None):
    accepted = accepted_inputs(ctx.root, allow_local_summary=ctx.namespace == "validation")
    protocol = read_json(ctx.root / "configs/tc2_gpu/protocol.json")
    runtime = runtime or {}
    return {"format": "tc2_gpu_fp32_npy_1", "namespace": ctx.namespace,
            "protocol_sha256": PROTOCOL_SHA256, "manifest_sha256": manifest_sha256,
            "split_hash": value["split_hash"], "dataset": value["dataset"], "category": value["category"],
            "images": image_entries(value), "weights_sha256": accepted["weights_sha256"],
            "preprocessing": protocol["preprocessing"], "backbone": protocol["backbone"],
            "dtype": "float32", "extraction_sources": fingerprints(ctx.root, CACHE_SOURCES),
            "software": versions(), "execution": EXECUTION,
            "hardware": {name: runtime.get(name) for name in ("gpu", "driver", "cuda_build")}}


def cache_directory(ctx, identity):
    if identity.get("namespace") != ctx.namespace or identity.get("format") != "tc2_gpu_fp32_npy_1" or identity.get("dtype") != "float32":
        raise ValueError("Cache namespace, format or precision is incompatible")
    if identity.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("Cache protocol differs")
    return inside(ctx.output("feature_cache"), "/".join([identity["dataset"], identity["category"], digest(identity)]))


class CacheReader:
    def __init__(self, ctx, directory, identity, *, _staging=False):
        self.arrays = {}
        try:
            self.directory = Path(directory)
            expected_directory = cache_directory(ctx, identity)
            staged = (_staging and self.directory.parent == expected_directory.parent
                      and self.directory.name.startswith("." + expected_directory.name + ".partial."))
            if self.directory != expected_directory and not staged:
                raise ValueError("Cache directory does not match its expected identity")
            inside(ctx.output("feature_cache"), self.directory.relative_to(ctx.output("feature_cache")).as_posix())
            expected = {"metadata.json", "COMPLETE", *(name + ".npy" for name in SHAPES)}
            if {path.name for path in self.directory.iterdir()} != expected:
                raise ValueError("Cache files are missing or unexpected")
            for name in expected:
                inside(self.directory, name)
            complete = read_json(self.directory / "COMPLETE")
            meta = read_json(self.directory / "metadata.json")
            if complete != {"status": "complete", "cache_id": digest(identity), "metadata_sha256": sha(self.directory / "metadata.json")}:
                raise ValueError("Cache completion fingerprint differs")
            if meta["identity"] != identity or meta["cache_id"] != digest(identity):
                raise ValueError("Cache input fingerprint differs")
            self.index = meta["index"]
            paths = [item["path"] for item in self.index]
            if paths != [item["path"] for item in identity["images"]] or len(set(paths)) != len(paths) or not paths:
                raise ValueError("Cache image index differs")
            for item in self.index:
                hw = item["orig_hw"]
                if len(hw) != 2 or any(type(size) is not int or size <= 0 for size in hw):
                    raise ValueError("Cache image dimensions are invalid")
            self.locations = {path: i for i, path in enumerate(paths)}
            for layer, shape in SHAPES.items():
                entry = meta["layers"][layer]
                path = self.directory / (layer + ".npy")
                if entry != {"dtype": "float32", "shape": [len(paths), *shape], "sha256": sha(path)}:
                    raise ValueError("Cache data fingerprint or shape metadata differs")
                values = np.load(path, mmap_mode="r", allow_pickle=False)
                self.arrays[layer] = values
                if values.dtype != np.float32 or values.shape != (len(paths), *shape):
                    raise ValueError("Cache data must be FP32 at the frozen feature shape")
                for image in values:
                    if not np.isfinite(image).all():
                        raise ValueError("Cache contains nonfinite features")
            self.metadata = meta
            self.fingerprint = {"cache_id": digest(identity), "metadata_sha256": complete["metadata_sha256"],
                                "layer_hashes": {name: value["sha256"] for name, value in meta["layers"].items()}}
        except Exception:
            self.close()
            raise

    def get(self, paths, layers):
        paths, layers = list(paths), tuple(layers)
        if not paths or len(set(paths)) != len(paths) or not layers or len(set(layers)) != len(layers):
            raise ValueError("Request distinct nonempty paths and layers")
        if any(path not in self.locations for path in paths) or any(layer not in SHAPES for layer in layers):
            raise ValueError("Requested feature is missing")
        rows = [self.locations[path] for path in paths]
        return {layer: np.stack([self.arrays[layer][i] for i in rows]) for layer in layers}

    def close(self):
        for value in self.arrays.values():
            if getattr(value, "_mmap", None) is not None:
                value._mmap.close()
        self.arrays.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def write_cache(ctx, identity, index, batches, extraction=None):
    target = cache_directory(ctx, identity)
    expected_paths = [item["path"] for item in identity["images"]]
    if [item["path"] for item in index] != expected_paths or not expected_paths:
        raise ValueError("Cache index does not match its expected image order")
    for item in index:
        if len(item["orig_hw"]) != 2 or any(type(size) is not int or size <= 0 for size in item["orig_hw"]):
            raise ValueError("Invalid original image dimensions")
    with exclusive(target.parent, target.name):
        if target.exists():
            with CacheReader(ctx, target, identity):
                return {"status": "cached", "path": str(target), "cache_id": target.name}
        needed = len(index) * sum(np.prod(shape) for shape in SHAPES.values()) * 4
        if shutil.disk_usage(target.parent).free < needed + 64 * 1024 * 1024:
            raise RuntimeError("Insufficient free space for the FP32 cache and write reserve")
        partial = inside(target.parent, "." + target.name + ".partial." + uuid.uuid4().hex[:8])
        partial.mkdir()
        arrays, offset = {}, 0
        started = time.perf_counter()
        try:
            for layer, shape in SHAPES.items():
                arrays[layer] = np.lib.format.open_memmap(partial / (layer + ".npy"), mode="w+", dtype=np.float32, shape=(len(index), *shape))
            for paths, batch in batches:
                paths = list(paths)
                if len(paths) != EXECUTION["extraction_batch_size"] or paths != expected_paths[offset:offset + len(paths)] or set(batch) != set(SHAPES):
                    raise ValueError("Extraction batches must cover each indexed image once in order")
                for layer, shape in SHAPES.items():
                    values = batch[layer]
                    if not isinstance(values, np.ndarray) or values.dtype != np.float32 or values.shape != (len(paths), *shape) or not np.isfinite(values).all():
                        raise ValueError("Extraction must produce finite FP32 features at the frozen shape")
                    arrays[layer][offset:offset + len(paths)] = values
                offset += len(paths)
            if offset != len(index):
                raise ValueError("Extraction did not cover all indexed images")
            for value in arrays.values():
                value.flush(); value._mmap.close()
            arrays.clear()
            meta = {"identity": identity, "cache_id": digest(identity), "index": index,
                    "extraction": dict(extraction or {}), "write_pipeline_seconds": time.perf_counter() - started,
                    "layers": {layer: {"shape": [len(index), *shape], "dtype": "float32", "sha256": sha(partial / (layer + ".npy"))}
                               for layer, shape in SHAPES.items()}}
            write_json(partial / "metadata.json", meta)
            write_json(partial / "COMPLETE", {"status": "complete", "cache_id": digest(identity), "metadata_sha256": sha(partial / "metadata.json")})
            with CacheReader(ctx, partial, identity, _staging=True):
                pass
            if target.exists():
                raise FileExistsError("Cache publication target already exists")
            partial.rename(target)
            return {"status": "extracted", "path": str(target), "cache_id": target.name}
        except Exception as error:
            for value in arrays.values():
                value._mmap.close()
            if partial.exists():
                write_json(partial / "FAILED.json", {"error": type(error).__name__ + ": " + str(error)})
            raise


def input_index(ctx, value, include_masks=False):
    from PIL import Image
    rows = image_entries(value)
    index = []
    for row in rows:
        path = inside(ctx.datasets, row["path"])
        if sha(path) != row["sha256"]:
            raise ValueError("Raw image differs from the manifest: " + row["path"])
        with Image.open(path) as image:
            index.append({"path": row["path"], "orig_hw": [image.height, image.width]})
    if include_masks:
        for entry in value["test"]["anomalies"]:
            for mask in entry["masks"]:
                if sha(inside(ctx.datasets, mask["path"])) != mask["sha256"]:
                    raise ValueError("Raw mask differs from the manifest")
    return index


def build_extractor(ctx, device):
    import torch
    from torchvision.models import resnet18
    expected = accepted_inputs(ctx.root, allow_local_summary=ctx.namespace == "validation")["weights_sha256"]
    if sha(ctx.weights) != expected:
        raise ValueError("The local ResNet18 weight file differs from accepted weights")
    backbone = resnet18(weights=None)
    backbone.load_state_dict(torch.load(ctx.weights, map_location="cpu", weights_only=True), strict=True)
    model = torch.nn.Sequential()
    model.add_module("stem", torch.nn.Sequential(backbone.conv1, backbone.bn1, backbone.relu, backbone.maxpool))
    for layer in SHAPES:
        model.add_module(layer, getattr(backbone, layer))
    model.requires_grad_(False)
    return model.to(device=device, dtype=torch.float32).eval()


def extract(ctx, dataset, category, *, value=None, manifest_sha256=None, device="cuda"):
    started = time.perf_counter()
    runtime = prepare_torch(ctx, device)
    if value is None:
        value, manifest_sha256 = manifest(ctx.root, dataset, category)
    elif ctx.namespace != "validation":
        raise ValueError("Alternate manifests are allowed only in isolated validation")
    if (value["dataset"], value["category"]) != (dataset, category):
        raise ValueError("Extraction target differs from the manifest")
    import torch
    from data import load_image
    io_start = time.perf_counter()
    index = input_index(ctx, value)
    identity = cache_identity(ctx, value, manifest_sha256, runtime)
    path = cache_directory(ctx, identity)
    input_seconds = time.perf_counter() - io_start
    if path.exists():
        with CacheReader(ctx, path, identity):
            return {"status": "cached", "path": str(path), "identity": identity}
    model = build_extractor(ctx, device)
    details = {"runtime": runtime, "input_verification_seconds": input_seconds,
               "preprocess_transfer_seconds": 0.0, "feature_gpu_seconds": 0.0,
               "feature_readback_seconds": 0.0, "warmup_seconds": 0.0,
               "batch_size": 1, "warmup_iterations": EXECUTION["warmup_iterations"]}

    def sync():
        if device == "cuda":
            torch.cuda.synchronize()

    def forward(image):
        result = {}
        for name, module in model.named_children():
            image = module(image)
            if name in SHAPES:
                result[name] = image
        return result

    with torch.inference_mode(), torch.autocast(device_type=device, enabled=False):
        image = load_image(inside(ctx.datasets, index[0]["path"]))[0].unsqueeze(0).to(device)
        sync(); begin = time.perf_counter()
        for _ in range(EXECUTION["warmup_iterations"]):
            forward(image)
        sync(); details["warmup_seconds"] = time.perf_counter() - begin

        def batches():
            for item in index:
                sync(); begin = time.perf_counter()
                tensor = load_image(inside(ctx.datasets, item["path"]))[0].unsqueeze(0).to(device)
                sync(); details["preprocess_transfer_seconds"] += time.perf_counter() - begin
                begin = time.perf_counter(); values = forward(tensor); sync()
                details["feature_gpu_seconds"] += time.perf_counter() - begin
                begin = time.perf_counter()
                arrays = {name: tensor.cpu().numpy() for name, tensor in values.items()}
                details["feature_readback_seconds"] += time.perf_counter() - begin
                yield [item["path"]], arrays

        result = write_cache(ctx, identity, index, batches(), details)
    result.update(identity=identity, total_seconds=time.perf_counter() - started)
    return result
