"""Salinan `normalize.py` / `core.py` di plugin & skill harus identik dengan paket.

Plugin Hermes dan skrip skill sengaja standalone (tidak mengimpor paket
`ispunet`), jadi modul inti di-vendor. Uji ini menjaga agar salinan tidak
menyimpang saat salah satu diperbaiki.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANONICAL = {
    "normalize.py": ROOT / "ispunet" / "normalize.py",
    "core.py": ROOT / "ispunet" / "core.py",
}
COPIES = {
    "hermes-plugin": ROOT / "hermes-plugin" / "ispunet",
    "skill": ROOT / "skills" / "ispunet" / "scripts",
}

@pytest.mark.parametrize("module", sorted(CANONICAL))
@pytest.mark.parametrize("target", sorted(COPIES))
def test_vendored_copy_matches_package(module: str, target: str):
    source = CANONICAL[module]
    copy = COPIES[target] / module
    assert copy.exists(), f"{copy} hilang — salin ulang dari {source}"
    assert copy.read_text() == source.read_text(), (
        f"{copy} menyimpang dari {source}; jalankan: cp {source} {copy}"
    )
