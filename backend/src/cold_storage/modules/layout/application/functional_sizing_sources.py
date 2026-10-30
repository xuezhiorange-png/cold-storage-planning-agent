"""Verify existing immutable evidence, not a new authority or approval system."""

import gzip
import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

BASE_HEAD = "9629019ddd704426b5f7fe72b9a98d2273fca1c4"
R10 = "docs/previews/v2.2.2/r11-r10-functional-room-reverse-sizing-r1"
R1 = "docs/previews/v2.2.2/r11-functional-room-fit-r1"
HISTORICAL = "docs/evidence/v2.2.2/r11-r11-h5-sizing-sources"
CATALOG = (
    "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1/project-and-room-catalog.json"
)
ANCHORS = MappingProxyType(
    {
        f"{R10}/source-manifest.json": (
            "25073492f68bcee6d798df7aa54748569db7e373ba1c05b05e76cbbec5f19e41"
        ),
        f"{R1}/source-manifest.json": (
            "24eee74d23923b18b14ca60ffaa2a4a9b7039ea1ec84ee3a9f0a7bcfe4c4cb79"
        ),
    }
)
SOFTWARE_EVIDENCE = MappingProxyType(
    {
        "backend-regression.zip": (
            "d4eeb938502574c8de26391fb51cc954b1ebe217d8da520f07f9eacfe7cfde5b"
        ),
        "backend-regression.xml": (
            "b12887130082da54a96ff0a4a053b0ee4f62eea66b58692eed825dde08425e18"
        ),
        "verified-r10-results.json": (
            "c97b37b0e28c5e2de5d7e951f8912375ff96832a3633449f727cd040604eeea7"
        ),
    }
)
HISTORICAL_FILES = (
    "server-authorities.json",
    "source-binding.json",
    "previews/proposal-01/candidate-01/candidate.json",
    "previews/proposal-02/candidate-01/candidate.json",
)
OWNER_FILES = (
    "docs/tasks/V2_2_2-r11-r3-reviewed-project-fact.txt",
    "docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt",
)
OWNER_HASHES = (
    "53ffa4e0e3584cabe7166d75214d0569fcaebfc34cc1e71bc35c70abedab7326",
    "275ff176226358835912b5e827104028c73388b7840ef78d1e4c1eaad2a807da",
)


def checked_bytes(files: Mapping[str, bytes], name: str, expected: str) -> bytes:
    value = files.get(name)
    if not isinstance(value, bytes):
        raise ValueError("FUNCTIONAL_SIZING_EVIDENCE_REQUIRED:" + name)
    if hashlib.sha256(value).hexdigest() != expected:
        raise ValueError("FUNCTIONAL_SIZING_EVIDENCE_MISMATCH:" + name)
    return value


def required_evidence_hashes(anchors: Mapping[str, bytes]) -> dict[str, str]:
    manifests = {
        name: json.loads(checked_bytes(anchors, name, digest)) for name, digest in ANCHORS.items()
    }
    r10, r1 = manifests[f"{R10}/source-manifest.json"], manifests[f"{R1}/source-manifest.json"]
    hashes = {
        **ANCHORS,
        **r10["source_files"],
        **{f"{R10}/{name}": digest for name, digest in r10["derived_files"].items()},
        f"{R1}/review-data.json": r1["derived_files"]["review-data.json"],
        **{
            f"{HISTORICAL}/{name}": r1["original_source_data_hashes"][name]
            for name in HISTORICAL_FILES
        },
        **dict(zip(OWNER_FILES, OWNER_HASHES, strict=True)),
        **{f"{HISTORICAL}/r10-remote-ci/{name}": sha for name, sha in SOFTWARE_EVIDENCE.items()},
    }
    return hashes


def verify_sizing_evidence(files: Mapping[str, bytes]) -> dict[str, Any]:
    expected = required_evidence_hashes(files)
    for name, digest in expected.items():
        checked_bytes(files, name, digest)

    def read(name: str) -> Any:
        return json.loads(files[name])

    return dict(
        catalog=read(CATALOG),
        r10=read(f"{R10}/sizing-preview.json"),
        cases=json.loads(gzip.decompress(files[f"{R10}/selected-evidence.json.gz"])),
        authority=read(f"{HISTORICAL}/server-authorities.json"),
        binding=read(f"{HISTORICAL}/source-binding.json"),
        candidates=[read(f"{HISTORICAL}/{name}") for name in HISTORICAL_FILES[2:]],
        r1=read(f"{R1}/review-data.json"),
        hashes=expected,
    )
