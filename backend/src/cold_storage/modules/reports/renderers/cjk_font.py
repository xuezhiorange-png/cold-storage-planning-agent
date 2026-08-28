"""Resolve a CJK-capable font file for PDF rendering.

Local ``make dev`` and operator machines often lack Debian
``fonts-wqy-zenhei``. macOS and Windows already ship CJK faces; PyMuPDF
also bundles Droid Sans Fallback as ``china-s``. Prefer a real system
font (CI keeps using WenQuanYi) and materialize the builtin face only
when no file is present.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import fitz  # PyMuPDF

_logger = logging.getLogger(__name__)

CJK_FONT_PATH_ENV = "COLD_STORAGE_CJK_FONT_PATH"
_PYMUPDF_BUILTIN_CJK = "china-s"
_FONT_SUFFIXES = {".ttc", ".ttf", ".otf"}

# Linux packages first so CI and Debian hosts keep the WenQuanYi face used
# by PDF semantic tests. macOS / Windows paths follow for ``make dev``.
_CJK_FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/NotoSansCJK-Regular.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)

_CJK_FONT_NAME_MARKERS: tuple[str, ...] = (
    "cjk",
    "wqy",
    "noto",
    "gothic",
    "mincho",
    "han",
    "pingfang",
    "heiti",
    "songti",
    "yahei",
    "simsun",
    "simhei",
    "droid",
    "wenquanyi",
    "sourcehan",
    "source-han",
    "msyh",
    "mingliu",
    "kaiti",
)

_CJK_FONT_PATH: str | None = None


def reset_cjk_font_cache() -> None:
    """Drop the resolved font path. Tests must call this after isolation."""
    global _CJK_FONT_PATH  # noqa: PLW0603
    _CJK_FONT_PATH = None


def load_cjk_font() -> fitz.Font:
    """Return a PyMuPDF font object for CJK text."""
    return fitz.Font(fontfile=find_cjk_font())


def find_cjk_font() -> str:
    """Return a readable CJK font file path, caching the first hit."""
    global _CJK_FONT_PATH  # noqa: PLW0603
    if _CJK_FONT_PATH is not None:
        return _CJK_FONT_PATH

    for candidate in _iter_font_candidates():
        if Path(candidate).is_file():
            _CJK_FONT_PATH = candidate
            return _CJK_FONT_PATH

    for font_file in _iter_scanned_font_files():
        _CJK_FONT_PATH = str(font_file)
        return _CJK_FONT_PATH

    materialized = _materialize_pymupdf_cjk_font()
    if materialized is not None:
        _logger.info(
            "No system CJK font file found; using PyMuPDF builtin %s at %s",
            _PYMUPDF_BUILTIN_CJK,
            materialized,
        )
        _CJK_FONT_PATH = materialized
        return _CJK_FONT_PATH

    raise RuntimeError(
        "No CJK font found. Install fonts-wqy-zenhei (Linux), or set "
        f"{CJK_FONT_PATH_ENV} to a .ttf/.ttc/.otf file."
    )


def _iter_font_candidates() -> list[str]:
    ordered: list[str] = []
    env_path = os.environ.get(CJK_FONT_PATH_ENV, "").strip()
    if env_path:
        ordered.append(env_path)
    ordered.extend(_CJK_FONT_CANDIDATES)
    ordered.extend(_windows_font_candidates())
    return ordered


def _windows_font_candidates() -> list[str]:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = Path(windir) / "Fonts"
    names = (
        "msyh.ttc",
        "msyhbd.ttc",
        "msyhl.ttc",
        "simsun.ttc",
        "simhei.ttf",
        "msjh.ttc",
        "mingliu.ttc",
        "NotoSansCJK-Regular.ttc",
    )
    return [str(fonts_dir / name) for name in names]


def _font_scan_roots() -> list[Path]:
    roots = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/opt/homebrew/share/fonts"),
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path.home() / ".local" / "share" / "fonts",
    ]
    windir = os.environ.get("WINDIR")
    if windir:
        roots.append(Path(windir) / "Fonts")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
    return [root for root in roots if root.is_dir()]


def _is_cjk_font_filename(name: str) -> bool:
    name_lower = name.lower()
    return any(marker in name_lower for marker in _CJK_FONT_NAME_MARKERS)


def _iter_scanned_font_files() -> Iterator[Path]:
    for root in _font_scan_roots():
        for font_file in root.rglob("*"):
            if (
                font_file.is_file()
                and font_file.suffix.lower() in _FONT_SUFFIXES
                and _is_cjk_font_filename(font_file.name)
            ):
                yield font_file


def _materialize_pymupdf_cjk_font() -> str | None:
    """Write PyMuPDF's builtin CJK face to a cache file for ``fontfile=`` APIs."""
    try:
        font = fitz.Font(_PYMUPDF_BUILTIN_CJK)
    except Exception:
        _logger.debug("PyMuPDF builtin CJK font %s is unavailable", _PYMUPDF_BUILTIN_CJK)
        return None
    buffer = font.buffer
    if not buffer:
        return None
    dest_dir = Path(tempfile.gettempdir()) / "cold-storage-cjk-fonts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "droid-sans-fallback-regular.ttf"
    if dest.is_file() and dest.stat().st_size == len(buffer):
        return str(dest)
    fd, tmp_name = tempfile.mkstemp(prefix="cjk-", suffix=".ttf", dir=dest_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(buffer)
        os.replace(tmp_name, dest)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return str(dest)
