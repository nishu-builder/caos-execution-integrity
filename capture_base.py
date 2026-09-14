#!/usr/bin/env python3
"""Maintainer: capture and digest-check the original demo base image."""
import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen

DIGEST = "9e70a80fc3561907fd1ef391ba5509b63bc49eaa0cda04a0c33bb506ba945b10"


def checked(data, digest, size=None):
    if hashlib.sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError("Registry digest mismatch")
    if size is not None and len(data) != size:
        raise ValueError("Registry size mismatch")
    return data


def capture(registry, output):
    output.mkdir(parents=True, exist_ok=False)
    root = registry.rstrip("/") + "/v2/caos/"
    with urlopen(Request(root + "manifests/sha256:" + DIGEST, headers={
            "Accept": "application/vnd.docker.distribution.manifest.v2+json"}), timeout=60) as response:
        data = checked(response.read(), DIGEST)
    manifest = json.loads(data)
    (output / "registry-manifest.json").write_bytes(data)
    with tarfile.open(output / "base.tar", "w") as archive:
        def add(name, content):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for item in [manifest["config"]] + manifest["layers"]:
            with urlopen(root + "blobs/" + item["digest"], timeout=60) as response:
                content = checked(response.read(), item["digest"], item["size"])
            add(item["digest"].split(":")[1], content)
        add("manifest.json", json.dumps([{
            "Config": manifest["config"]["digest"].split(":")[1],
            "Layers": [i["digest"].split(":")[1] for i in manifest["layers"]]
        }]).encode())
    print(output / "base.tar")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    capture(a.registry, a.output)
