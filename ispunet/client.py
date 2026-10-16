"""Klien HTTP untuk API mobile ISPUNet (ispu.kemenlh.go.id/apimob/v1).

Semua endpoint diambil dari APK resmi v1.5.5. Tiap request menyertakan
cache-buster path `time?=<epoch-ms>` seperti perilaku aplikasi asli.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from . import constants as C


class IspuError(Exception):
    """Kegagalan akses API ISPUNet (transport atau status != 200)."""


class IspuClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_signature: str | None = None,
        base_url: str | None = None,
        timeout: float = C.REQUEST_TIMEOUT,
        retries: int = C.RETRY_ATTEMPTS,
    ) -> None:
        self._base = (base_url or C.base_url()).rstrip("/") + "/"
        self._headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or C.api_key(),
            "x-api-signature": api_signature or C.api_signature(),
        }
        self._timeout = timeout
        self._retries = retries

    # ------------------------------------------------------------------ core
    def _get(self, action: str) -> Any:
        """GET <base><action>; retry seperti app asli (retry(2)); raise IspuError saat gagal."""
        url = f"{self._base}{action}"
        last_exc: Exception | None = None
        with httpx.Client(timeout=self._timeout, headers=self._headers) as http:
            for _ in range(self._retries + 1):
                try:
                    resp = http.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    last_exc = exc
                    continue
                if data.get("status", {}).get("statusCode") != 200:
                    raise IspuError(
                        f"API {action} error: {data.get('status')}"
                    ) from last_exc
                return data
        raise IspuError(f"API {action} gagal setelah {self._retries + 1} percobaan: {last_exc}")

    @staticmethod
    def _cache_bust(action: str) -> str:
        """Tambahkan `time?=<epoch-ms>` bila action belum punya query (cache-buster upstream)."""
        if "time?=" in action:
            return action
        return f"{action.rstrip('/')}/time?={int(time.time() * 1000)}"

    # -------------------------------------------------------------- endpoints
    def stations(self) -> list[dict[str, Any]]:
        """Semua stasiun pemantauan + nilai terkini (dari getStations)."""
        return self._get(self._cache_bust("getStations"))["rows"]

    def categories(self) -> list[dict[str, Any]]:
        """Definisi 5 kategori ISPU: BAIK .. BERBAHAYA, batas, warna, icon (dari statusispu)."""
        return self._get(self._cache_bust("statusispu"))["rows"]

    def current(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Kualitas udara terkini di sekitar koordinat: stasiun terdekat dulu, lalu sekitarnya."""
        action = f"getData/lat/{lat}/lng/{lon}"
        return self._get(self._cache_bust(action))["rows"]

    def station_detail(self, station_id: str) -> dict[str, Any]:
        """Detail satu stasiun: nilai terkini, kategori, riwayat 24 jam per polutan."""
        action = f"getDetail/stasiun/{station_id}"
        rows = self._get(action)["rows"]
        if not rows:
            raise IspuError(f"Stasiun {station_id!r} tidak ditemukan / tanpa data")
        return rows[0]

    def app_version(self, version: str) -> Any:
        """Cek versi terbaru aplikasi (endpoint version/v/<versi>, dipakai splash screen)."""
        return self._get(self._cache_bust(f"version/v/{version}"))


# ---------------------------------------------------------------- helpers publik
def recommendation(uid: int) -> str:
    """Rekomendasi kesehatan untuk nilai_uid kategori (1..5)."""
    return C.RECOMMENDATIONS.get(uid, "Kategori tidak dikenal.")


def nearest(rows: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    """Pilih stasiun terdekat dari hasil `current()` (rows sudah terurut jarak, ini fallback aman)."""
    if not rows:
        return None
    best = None
    best_d = float("inf")
    for r in rows:
        d = (float(r["lat"]) - lat) ** 2 + (float(r["lon"]) - lon) ** 2
        if d < best_d:
            best, best_d = r, d
    return best
