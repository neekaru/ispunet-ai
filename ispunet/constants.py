"""Konstanta ISPUNet: endpoint, kredensial publik, kategori ISPU, dan rekomendasi kesehatan.

Kredensial di bawah dikirim oleh APK resmi ke setiap perangkat (statis di
src/app/services/api.service.ts), jadi bersifat publik. Bisa diganti lewat env
ISPUNET_API_KEY / ISPUNET_API_SIGNATURE / ISPUNET_API_URL.
"""

from __future__ import annotations

import os

DEFAULT_BASE_URL = "https://ispu.kemenlh.go.id/apimob/v1/"

DEFAULT_API_KEY = "ispunet|NfdSdj49mb3Fo0f2MASkQ0YL60DqCpDX"
DEFAULT_API_SIGNATURE = (
    "3a80e6b8d484a15e726e111c03e1ea97c9b3aad8cf469a218bdb3cb70fc524f5"
)

REQUEST_TIMEOUT = 20.0
RETRY_ATTEMPTS = 2  # upstream app retry(2)


def base_url() -> str:
    return os.environ.get("ISPUNET_API_URL", DEFAULT_BASE_URL).rstrip("/") + "/"


def api_key() -> str:
    return os.environ.get("ISPUNET_API_KEY", DEFAULT_API_KEY)


def api_signature() -> str:
    return os.environ.get("ISPUNET_API_SIGNATURE", DEFAULT_API_SIGNATURE)


# Rekomendasi kesehatan, daftar polutan, dan ambang data ada di `normalize`
# (satu sumber untuk paket, plugin, dan skill). Diekspor ulang di sini supaya
# `ispunet.constants.RECOMMENDATIONS` tetap menjadi tempat yang lazim dilihat.
from .normalize import (  # noqa: E402  (dipisah agar blok env di atas tetap terbaca)
    ISPU_MAX,
    KONSENTRASI_MAX,
    OFFLINE_RECOMMENDATION,
    POLLUTANT_LABEL,
    POLLUTANTS,
    RECOMMENDATIONS,
    STALE_HOURS,
)

__all__ = [
    "DEFAULT_BASE_URL", "DEFAULT_API_KEY", "DEFAULT_API_SIGNATURE",
    "REQUEST_TIMEOUT", "RETRY_ATTEMPTS", "base_url", "api_key", "api_signature",
    "POLLUTANTS", "POLLUTANT_LABEL", "RECOMMENDATIONS", "OFFLINE_RECOMMENDATION",
    "ISPU_MAX", "KONSENTRASI_MAX", "STALE_HOURS",
]
