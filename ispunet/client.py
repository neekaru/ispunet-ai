"""Klien HTTP untuk API mobile ISPUNet (ispu.kemenlh.go.id/apimob/v1).

Semua endpoint diambil dari APK resmi v1.5.5. Tiap request menyertakan
cache-buster path `time?=<epoch-ms>` seperti perilaku aplikasi asli.

Transport (httpx, retry, rate-limit) ada di sini; seluruh logika pemilihan
stasiun dan normalisasi ada di `ispunet.core` / `ispunet.normalize` sehingga
paket, plugin Hermes, dan skrip skill memakai perilaku yang sama.

Respons mentah TIDAK pernah dikembalikan apa adanya: semuanya lewat
normalisasi. Butuh data mentah? Pakai `*_raw()`.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import httpx

from . import constants as C
from .core import (  # noqa: F401 — re-export: IspuError/StationNotFound tetap di sini
    CITY_COORDS,
    IspuCore,
    IspuError,
    StationNotFound,
    nearest,
    rank_replacements,
    recommendation,
    resolve_city,
)

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
        self._core = IspuCore(self._fetch)

    # ------------------------------------------------------------ transport
    def _get(self, action: str) -> dict[str, Any]:
        """GET <base><action> dengan retry + backoff; raise IspuError saat gagal.

        Upstream membalas HTTP 400 `{"statusDesc": "Too Many Attempts."}` saat
        dipanggil terlalu rapat — itu satu-satunya 400 yang layak diulang.
        """
        url = f"{self._base}{action}"
        last_exc: Exception | None = None
        with httpx.Client(timeout=self._timeout, headers=self._headers) as http:
            for attempt in range(self._retries + 1):
                try:
                    resp = http.get(url)
                    data = resp.json() if resp.content else {}
                except (httpx.HTTPError, ValueError) as exc:
                    last_exc = exc
                    time.sleep(1.0 * (attempt + 1))
                    continue
                status = data.get("status") or {}
                if status.get("statusCode") == 200:
                    return data
                desc = str(status.get("statusDesc") or "")
                limited = "too many attempts" in desc.lower() or (
                    resp.status_code == 400 and "too many attempts" in resp.text.lower()
                )
                if limited and attempt < self._retries:
                    last_exc = IspuError(f"rate limit upstream: {desc or resp.status_code}")
                    time.sleep(2.5 * (attempt + 1))
                    continue
                raise IspuError(f"API {action} error: {status or resp.status_code}")
        raise IspuError(f"API {action} gagal setelah {self._retries + 1} percobaan: {last_exc}")

    @staticmethod
    def _cache_bust(action: str) -> str:
        """Tambahkan `time?=<epoch-ms>` bila action belum punya query (cache-buster upstream)."""
        if "time?=" in action:
            return action
        return f"{action.rstrip('/')}/time?={int(time.time() * 1000)}"

    def _fetch(self, action: str) -> dict[str, Any]:
        """Transport untuk `IspuCore`: cache-buster untuk semua kecuali getDetail."""
        if action.startswith("getDetail/"):
            return self._get(action)  # endpoint ini menolak query tambahan
        return self._get(self._cache_bust(action))

    # ---------------------------------------------------------- raw endpoints
    def stations_raw(self) -> list[dict[str, Any]]:
        """Baris mentah `getStations` (107 stasiun; TIDAK memuat semua stasiun aktif)."""
        return self._core.stations_raw()

    def detail_raw(self, station_id: str) -> list[dict[str, Any]]:
        """Baris mentah `getDetail/stasiun/<id>`."""
        return self._core.detail_raw(station_id)

    def nearby_raw(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Baris mentah `getData/lat/<lat>/lng/<lon>` (terurut jarak dari upstream)."""
        return self._core.nearby_raw(lat, lon)

    def categories(self) -> list[dict[str, Any]]:
        """Definisi 5 kategori ISPU: BAIK .. BERBAHAYA, batas, warna."""
        return self._core.categories()

    # -------------------------------------------------------------- normalized
    def stations(
        self,
        *,
        q: str | None = None,
        provinsi: str | None = None,
        kota: str | None = None,
        hanya_aktif: bool = False,
        order: str = "wilayah",
        limit: int | None = None,
        now: dt.datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Stasiun ternormalisasi, terurut deterministik; `limit` memotong urutan yang sama.

        `getStations` hanya memuat 107 stasiun dan melewatkan sebagian stasiun
        aktif (Palangka Raya, Banjar Baru, Perawang, Mobile AQMS Kalteng).
        Untuk kota-kota itu pakai `current()` / `compare()`.
        """
        return self._core.stations(
            q=q, provinsi=provinsi, kota=kota,
            hanya_aktif=hanya_aktif, order=order, limit=limit, now=now,
        )

    def station_detail(
        self, station_id: str, *, history: bool = True, now: dt.datetime | None = None
    ) -> dict[str, Any]:
        """Detail stasiun + riwayat 24 jam bersih + `pengganti` bila stasiun mati.

        `station_id` peka huruf besar/kecil di upstream? Tidak — `dki1` tetap
        ditemukan. Bila tidak ada, `StationNotFound` membawa saran ID + pengganti.
        """
        return self._core.station_detail(station_id, history=history, now=now)

    def current(
        self, lat: float | None = None, lon: float | None = None, *,
        kota: str | None = None, now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        """Udara di sekitar koordinat (atau nama kota): `primary`, `nearby`, `catatan`."""
        return self._core.current(lat, lon, kota=kota, now=now)

    def compare(
        self, targets: list[str], *, now: dt.datetime | None = None
    ) -> dict[str, Any]:
        """Bandingkan beberapa stasiun/kota dalam satu panggilan."""
        return self._core.compare(targets, now=now)
