#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 MVTec 官方链接下载本作业用到的 8 个类别。

只下载手册用到的 MVTec AD 六类和 LOCO 两类，不下载完整数据集。
图片许可是 CC BY-NC-SA 4.0，仅限非商业用途。脚本不会把图片提交到 Git。

用法（在 group_XX_code 目录）：
  python scripts/download_datasets.py --accept-license
"""
from __future__ import annotations

import argparse
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DEST = (HERE / ".." / ".." / "datasets").resolve()

# 官方页面上的直链。页面本身：
# https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads
# https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads
MVTEC_AD = {
    "bottle": "https://www.mydrive.ch/shares/150452/132a93367fb17cdf968dfb5c4013f6e7/download/420937370-1629958698/bottle.tar.xz",
    "cable": "https://www.mydrive.ch/shares/150453/10f960e07fec2838b2cd512586633a32/download/420937413-1629958794/cable.tar.xz",
    "capsule": "https://www.mydrive.ch/shares/150454/e0ce6dd74eb150f46c0d98131b3703f2/download/420937454-1629958872/capsule.tar.xz",
    "screw": "https://www.mydrive.ch/shares/150461/242f454cc6385e5693c4fd4b94567d1e/download/420938130-1629960389/screw.tar.xz",
    "tile": "https://www.mydrive.ch/shares/150462/5479f0fdc97bc6fa16eab0cb0cf0109f/download/420938133-1629960456/tile.tar.xz",
    "wood": "https://www.mydrive.ch/shares/150465/d5b4115b720cdb54d217e75636e6e374/download/420938383-1629960649/wood.tar.xz",
}
MVTEC_LOCO = {
    "juice_bottle": "https://www.mydrive.ch/shares/48239/3ad28d48636eada48f0caded666a804a/download/430647100-1646843074/juice_bottle.tar.xz",
    "screw_bag": "https://www.mydrive.ch/shares/48241/be5dc3a69c92932644aaac945451d4e7/download/430647115-1646843129/screw_bag.tar.xz",
}

LICENSE_NOTE = """\
MVTec AD 与 MVTec LOCO AD 由 MVTec Software GmbH 发布，许可为
CC BY-NC-SA 4.0。不得用于商业目的，转载须保留署名并使用相同许可。
继续下载表示你接受该许可。
"""


def safe_extract(archive: Path, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if dest != target and dest not in target.parents:
                raise RuntimeError(f"压缩包路径不安全：{member.name}")
        tar.extractall(dest)


def place_category(archive: Path, parent: Path, category: str) -> None:
    """压缩包若自带类别目录，就解到 parent；否则解到 parent/category。"""
    with tarfile.open(archive, "r:xz") as tar:
        names = [m.name for m in tar.getmembers() if m.name and not m.name.startswith("./")]
    tops = {name.split("/")[0] for name in names}
    if tops == {category}:
        safe_extract(archive, parent)
    else:
        safe_extract(archive, parent / category)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"下载 {url}", flush=True)
    urllib.request.urlretrieve(url, dest)


def already_present(category_dir: Path) -> bool:
    return category_dir.is_dir() and any(category_dir.rglob("*.png"))


def fetch_group(urls: dict, parent: Path, tmp: Path) -> None:
    for category, url in urls.items():
        category_dir = parent / category
        if already_present(category_dir):
            print(f"已存在，跳过 {category_dir}", flush=True)
            continue
        archive = tmp / f"{category}.tar.xz"
        download(url, archive)
        print(f"解压 {category}", flush=True)
        place_category(archive, parent, category)
        archive.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="下载本作业使用的 MVTec 类别")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST,
                        help="数据集根目录，默认是仓库里的 datasets/")
    parser.add_argument("--accept-license", action="store_true",
                        help="确认接受 CC BY-NC-SA 4.0 后再下载")
    args = parser.parse_args()
    print(LICENSE_NOTE)
    if not args.accept_license:
        print("加上 --accept-license 后才会开始下载。")
        print("MVTec AD： https://www.mvtec.com/research-teaching/datasets/mvtec-ad/downloads")
        print("MVTec LOCO： https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad/downloads")
        return 2
    dest = args.dest.resolve()
    tmp = dest / "_downloads"
    fetch_group(MVTEC_AD, dest / "mvtec_ad", tmp)
    fetch_group(MVTEC_LOCO, dest / "mvtec_loco", tmp)
    if tmp.is_dir() and not any(tmp.iterdir()):
        tmp.rmdir()
    print(f"完成。数据放在 {dest}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
