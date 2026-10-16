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


# Rekomendasi kesehatan per nilai_uid — persis dari api.service.ts statusRekomendasi.
RECOMMENDATIONS: dict[int, str] = {
    1: "Sangat baik melakukan kegiatan di luar",
    2: (
        "Kelompok sensitif: kurangi aktivitas fisik yang terlalu lama atau berat. "
        "Setiap orang: masih dapat beraktivitas di luar."
    ),
    3: (
        "Penderita asma: harus mengikuti petunjuk kesehatan untuk asma dan menyimpan obat asma. "
        "Penderita penyakit jantung: gejala seperti palpitasi, sesak napas, atau kelelahan yang "
        "tidak biasa mungkin mengindikasikan masalah serius. "
        "Setiap orang: mengurangi aktivitas fisik yang terlalu lama di luar ruangan."
    ),
    4: (
        "Kelompok sensitif: hindari semua aktivitas di luar. Perbanyak aktivitas di dalam ruangan "
        "atau lakukan penjadwalan ulang pada waktu dengan kualitas udara yang baik. "
        "Setiap orang: hindari aktivitas fisik yang terlalu lama di luar ruangan, pertimbangkan "
        "untuk melakukan aktivitas di dalam ruangan."
    ),
    5: (
        "Kelompok sensitif: tetap di dalam ruangan dan hanya melakukan sedikit aktivitas. "
        "Setiap orang: hindari semua aktivitas di luar."
    ),
}

# Parameter polutan yang dilaporkan stasiun.
POLLUTANTS = ("pm10", "pm25", "so2", "co", "o3", "no2", "hc")
