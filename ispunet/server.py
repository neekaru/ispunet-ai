"""REST API FastAPI untuk ISPUNet.

Jalankan:  uvicorn ispunet.server:app  (atau  ispunet serve)

Semua respons sudah dinormalisasi (timestamp, riwayat tanpa duplikat, nilai
mustahil ditandai, stasiun offline/usang dilabeli) — lihat `ispunet.normalize`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from . import __version__
from .client import IspuClient, IspuError, StationNotFound

app = FastAPI(
    title="ISPUNet API",
    description=(
        "Kualitas udara Indonesia (ISPU) — dibangun ulang dari API mobile resmi KLHK, "
        "dengan normalisasi data: umur data, stasiun offline, riwayat 24 jam tanpa "
        "duplikat, dan penanda nilai di luar skala ISPU."
    ),
    version=__version__,
)

@lru_cache(maxsize=1)
def _client() -> IspuClient:
    return IspuClient()

def _fail(exc: IspuError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))

@app.get("/", tags=["meta"])
def root() -> dict[str, Any]:
    return {
        "name": "ispunet",
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "/stations?q=&provinsi=&kota=&limit=&order=",
            "/stations/{station_id}",
            "/current?lat=&lon=  atau  /current?kota=",
            "/compare?targets=DKI1,Jakarta,Banjarmasin",
            "/categories",
        ],
        "catatan": [
            "field `usang` = data lebih tua dari 3 jam; jangan disajikan sebagai kondisi terkini",
            "field `mencurigakan` = konsentrasi di luar skala ISPU (ISPU >500); nilai dipertahankan",
            "`rekomendasi` = 'TIDAK VALID / stasiun offline' bila stasiun tidak melaporkan ISPU",
        ],
    }

@app.get("/stations", tags=["ispu"])
def stations(
    q: str | None = Query(None, description="Cari id/nama/kota/provinsi (case-insensitive)"),
    provinsi: str | None = Query(None, description="Filter provinsi (substring)"),
    kota: str | None = Query(None, description="Filter kota (substring)"),
    hanya_aktif: bool = Query(False, description="Hanya stasiun yang melaporkan ISPU"),
    order: str = Query("wilayah", pattern="^(wilayah|ispu)$", description="Urutan deterministik"),
    limit: int | None = Query(None, ge=1, description="Potong setelah diurutkan"),
) -> dict[str, Any]:
    """Stasiun pemantauan + nilai terkini, rata-rata, dan status kesegaran data."""
    try:
        rows = _client().stations(
            q=q, provinsi=provinsi, kota=kota,
            hanya_aktif=hanya_aktif, order=order,
        )
    except IspuError as exc:
        raise _fail(exc) from exc
    shown = rows[:limit] if limit else rows
    return {
        "total": len(rows),
        "ditampilkan": len(shown),
        "urutan": order,
        "stasiun": shown,
        "catatan": (
            "getStations tidak memuat semua stasiun aktif; kota tanpa entri di sini "
            "bisa dicek lewat /current?kota= atau /compare"
        ),
    }

@app.get("/stations/{station_id}", tags=["ispu"])
def station_detail(
    station_id: str,
    history: bool = Query(True, description="Sertakan riwayat 24 jam"),
) -> dict[str, Any]:
    """Detail stasiun: nilai terkini, rata-rata, riwayat 24 jam bersih, pengganti bila mati."""
    try:
        return _client().station_detail(station_id, history=history)
    except StationNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": str(exc),
                "saran_id": exc.saran,
                "pengganti": exc.pengganti,
                "mirip": exc.mirip,
            },
        ) from exc
    except IspuError as exc:
        raise _fail(exc) from exc

@app.get("/current", tags=["ispu"])
def current(
    lat: float | None = Query(None, ge=-90, le=90, description="Latitude"),
    lon: float | None = Query(None, ge=-180, le=180, description="Longitude"),
    kota: str | None = Query(None, description="Nama kota (alternatif lat/lon)"),
) -> dict[str, Any]:
    """Kualitas udara terkini: stasiun aktif tersegar, stasiun sekitar, dan catatan."""
    if kota is None and (lat is None or lon is None):
        raise HTTPException(status_code=422, detail="kirim lat+lon atau kota")
    try:
        return _client().current(lat, lon, kota=kota)
    except IspuError as exc:
        raise _fail(exc) from exc

@app.get("/compare", tags=["ispu"])
def compare(
    targets: str = Query(
        ...,
        description="Daftar dipisah koma: id stasiun, nama kota, atau provinsi "
                    "(mis. DKI1,Banjarmasin,Palangka Raya)",
    ),
) -> dict[str, Any]:
    """Bandingkan beberapa stasiun/kota dalam satu panggilan."""
    items = [t.strip() for t in targets.split(",") if t.strip()]
    if not items:
        raise HTTPException(status_code=422, detail="targets kosong")
    try:
        return _client().compare(items)
    except IspuError as exc:
        raise _fail(exc) from exc

@app.get("/categories", tags=["ispu"])
def categories() -> list[dict[str, Any]]:
    """5 kategori ISPU: BAIK, SEDANG, TIDAK SEHAT, SANGAT TIDAK SEHAT, BERBAHAYA."""
    try:
        return _client().categories()
    except IspuError as exc:
        raise _fail(exc) from exc
