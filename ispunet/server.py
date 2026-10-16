"""REST API FastAPI untuk ISPUNet.

Jalankan:  uvicorn ispunet.server:app  (atau  ispunet serve)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from . import __version__
from .client import IspuClient, IspuError, nearest, recommendation

app = FastAPI(
    title="ISPUNet API",
    description="Kualitas udara Indonesia (ISPU) — dibangun ulang dari API mobile resmi KLHK.",
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
            "/stations",
            "/stations/{station_id}",
            "/categories",
            "/current?lat=&lon=",
        ],
    }


@app.get("/stations", tags=["ispu"])
def stations() -> list[dict[str, Any]]:
    """Semua stasiun pemantauan se-Indonesia beserta nilai ISPU terkini."""
    try:
        return _client().stations()
    except IspuError as exc:
        raise _fail(exc) from exc


@app.get("/stations/{station_id}", tags=["ispu"])
def station_detail(station_id: str) -> dict[str, Any]:
    """Detail stasiun: nilai terkini, kategori, riwayat 24 jam, dan rekomendasi kesehatan."""
    try:
        detail = _client().station_detail(station_id)
    except IspuError as exc:
        raise _fail(exc) from exc
    uid = detail.get("kategori", {}).get("nilai_uid")
    return {**detail, "rekomendasi": recommendation(uid) if uid else None}


@app.get("/categories", tags=["ispu"])
def categories() -> list[dict[str, Any]]:
    """5 kategori ISPU: BAIK, SEDANG, TIDAK SEHAT, SANGAT TIDAK SEHAT, BERBAHAYA."""
    try:
        return _client().categories()
    except IspuError as exc:
        raise _fail(exc) from exc


@app.get("/current", tags=["ispu"])
def current(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
) -> dict[str, Any]:
    """Kualitas udara terkini untuk koordinat: stasiun terdekat + daftar sekitarnya."""
    try:
        rows = _client().current(lat, lon)
    except IspuError as exc:
        raise _fail(exc) from exc
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada stasiun pemantauan di sekitar ({lat}, {lon})",
        )
    primary = nearest(rows, lat, lon) or rows[0]
    uid = primary.get("kategori", {}).get("nilai_uid")
    return {
        "primary": {**primary, "rekomendasi": recommendation(uid) if uid else None},
        "nearby": rows,
    }
