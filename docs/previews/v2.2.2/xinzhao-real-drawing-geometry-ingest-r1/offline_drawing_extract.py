"""Read-only PDF byte/vector inventory. No OCR, inferred rooms, or Authority tokens."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import fitz


def encode(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def primitive(value: Any) -> Any:
    if isinstance(value, (fitz.Point, fitz.Rect, fitz.Quad, fitz.Matrix)):
        return [primitive(item) for item in value]
    if isinstance(value, (list, tuple)):
        return [primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): primitive(item) for key, item in value.items()}
    return value


def inventory(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    with fitz.open(stream=raw, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("ENCRYPTED_SOURCE_REQUIRES_ACCESS")
        pages = []
        for index, page in enumerate(document):
            text = page.get_text()
            drawings = page.get_drawings()
            # Signal only. Even apparently readable text requires source-region review.
            cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
            pages.append(
                {
                    "page": index + 1,
                    "media_box": list(page.mediabox),
                    "crop_box": list(page.cropbox),
                    "display_box": list(page.rect),
                    "rotation": page.rotation,
                    "rotation_matrix": list(page.rotation_matrix),
                    "crop_status": (
                        "CROP_DIFFERS_REVIEW_REQUIRED"
                        if page.mediabox != page.cropbox
                        else "BOXES_EQUAL_CONTENT_COMPLETENESS_NOT_PROVEN"
                    ),
                    "text": text,
                    "text_status": "MANUAL_REVIEW_REQUIRED"
                    if cjk < 2
                    else "TEXT_REVIEW_REQUIRED",
                    "vector_count": len(drawings),
                    "vectors": [
                        {
                            "path_id": n,
                            "source_frame": "UNROTATED_PDF_POINTS",
                            **primitive(d),
                        }
                        for n, d in enumerate(drawings)
                    ],
                }
            )
        return {
            "contract": "drawing-source-inventory@1.0.0",
            "source_sha256": digest(raw),
            "source_bytes": len(raw),
            "pdf_page_count": len(document),
            "metadata": document.metadata,
            "pdf_library_version": fitz.VersionBind,
            "engineering_authority_approved": False,
            "pages": pages,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # Exclusive create: never silently overwrite a sealed result.
    with args.output.open("xb") as stream:
        stream.write(encode(inventory(args.pdf)))


if __name__ == "__main__":
    main()
