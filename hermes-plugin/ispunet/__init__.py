"""ISPUNet Hermes plugin — tool `ispu`.

Registrasi: register(ctx) dipanggil sekali saat startup Hermes.
Handler menerima args (dict) dan WAJIB mengembalikan string JSON.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

ISPU_SCHEMA = {
    "name": "ispu",
    "description": (
        "Kualitas udara Indonesia (ISPU, resmi KLHK). Gunakan saat user bertanya "
        "udara/ISPU/polusi di Indonesia. Mode: 'current' (butuh lat/lon), "
        "'station' (butuh id_stasiun mis. DKI1), 'stations' (daftar semua stasiun), "
        "'categories' (definisi kategori ISPU)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["current", "station", "stations", "categories"],
                "description": "current=udara di koordinat, station=detail satu stasiun",
            },
            "lat": {"type": "number", "description": "Latitude (mode current)"},
            "lon": {"type": "number", "description": "Longitude (mode current)"},
            "station_id": {
                "type": "string",
                "description": "ID stasiun, mis. DKI1 (mode station)"
            },
            "limit": {
                "type": "integer",
                "description": "Batasi jumlah stasiun (mode stations)"
            },
        },
        "required": ["mode"],
    },
}

POLLUTANTS = ("pm25", "pm10", "so2", "co", "o3", "no2", "hc")

RECOMMENDATIONS = {
    1: "Sangat baik melakukan kegiatan di luar",
    2: "Kelompok sensitif: kurangi aktivitas fisik berat/lama. Semua orang masih bisa beraktivitas di luar.",
    3: "Penderita asma/jantung: ikuti petunjuk kesehatan & siapkan obat. Semua orang: kurangi aktivitas fisik lama di luar.",
    4: "Kelompok sensitif: hindari semua aktivitas di luar. Semua orang: pertimbangkan aktivitas di dalam ruangan.",
    5: "Kelompok sensitif: tetap di dalam ruangan. Semua orang: hindari semua aktivitas di luar.",
}


def _rec(kategori: dict | None) -> str:
    uid = (kategori or {}).get("nilai_uid")
    return RECOMMENDATIONS.get(int(uid), "") if uid is not None else ""


def _fetch(action: str, cache_bust: bool = True, timeout: float = 20.0) -> dict:
    """GET ke API mobile ISPUNet. Murni stdlib agar plugin tanpa python_dependencies."""
    import os
    import time
    import urllib.error
    import urllib.request

    base = (
        os.environ.get("ISPUNET_API_URL", "https://ispu.kemenlh.go.id/apimob/v1/")
        .rstrip("/")
        + "/"
    )
    url = base + action.rstrip("/")
    if cache_bust and "time?=" not in url:
        url = f"{url}/time?={int(time.time() * 1000)}"
    req = urllib.request.Request(
        url,
        headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ.get(
                "ISPUNET_API_KEY", "ispunet|NfdSdj49mb3Fo0f2MASkQ0YL60DqCpDX"
            ),
            "x-api-signature": os.environ.get(
                "ISPUNET_API_SIGNATURE",
                "3a80e6b8d484a15e726e111c03e1ea97c9b3aad8cf469a218bdb3cb70fc524f5",
            ),
        },
    )
    last_exc: Exception | None = None
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            if data.get("status", {}).get("statusCode") != 200:
                return {"error": f"API {action}: {data.get('status')}"}
            return data
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_exc = exc
            time.sleep(1.0 * attempt)
    return {"error": f"gagal menghubungi API ISPUNet: {last_exc}"}


def _mode_current(args: dict) -> str:
    lat, lon = args.get("lat"), args.get("lon")
    if lat is None or lon is None:
        return json.dumps({"error": "mode current butuh lat dan lon"})
    data = _fetch(f"getData/lat/{float(lat)}/lng/{float(lon)}")
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)
    rows = data.get("rows", [])
    if not rows:
        return json.dumps(
            {"error": f"tidak ada stasiun pemantauan di sekitar ({lat}, {lon})"},
            ensure_ascii=False,
        )
    p = rows[0]
    out = {
        "stasiun_terdekat": {
            "id_stasiun": p.get("id_stasiun"),
            "nama": p.get("nama"),
            "kota": p.get("kota"),
            "provinsi": p.get("provinsi"),
            "waktu": p.get("waktu"),
            "jarak_m": p.get("jarak"),
            "ispu": p.get("val"),
            "param": p.get("param"),
            "kategori": p.get("kategori"),
            "konsentrasi": {k: p.get(k) for k in POLLUTANTS},
            "rekomendasi": _rec(p.get("kategori")),
        },
        "jumlah_stasiun_sekitar": len(rows) - 1,
    }
    return json.dumps(out, ensure_ascii=False)


def _mode_station(args: dict) -> str:
    sid = args.get("station_id")
    if not sid:
        return json.dumps({"error": "mode station butuh station_id"})
    # getDetail menolak query tambahan — tanpa cache-buster.
    data = _fetch(f"getDetail/stasiun/{sid}", cache_bust=False)
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)
    rows = data.get("rows", [])
    if not rows:
        return json.dumps({"error": f"stasiun {sid} tidak ditemukan"}, ensure_ascii=False)
    d = rows[0]
    out = {
        "id_stasiun": d.get("id_stasiun"),
        "nama": d.get("nama"),
        "alamat": d.get("alamat"),
        "kota": d.get("kota"),
        "provinsi": d.get("provinsi"),
        "waktu": d.get("waktu"),
        "param": d.get("param"),
        "kategori": d.get("kategori"),
        "konsentrasi": {k: d.get(k) for k in POLLUTANTS},
        "riwayat_24jam": {
            "waktu": d.get("waktu_24_rev"),
            "pm25": d.get("pm25_24_rev"),
            "pm10": d.get("pm10_24_rev"),
        },
        "rekomendasi": _rec(d.get("kategori")),
    }
    return json.dumps(out, ensure_ascii=False)


def _mode_stations(args: dict) -> str:
    data = _fetch("getStations")
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)
    rows = data.get("rows", [])
    limit = args.get("limit")
    if isinstance(limit, int) and limit > 0:
        rows = rows[:limit]
    slim = [
        {
            "id_stasiun": r.get("id_stasiun"),
            "nama": r.get("nama"),
            "kota": r.get("kota"),
            "provinsi": r.get("provinsi"),
        }
        for r in rows
    ]
    return json.dumps(
        {"total": len(rows), "stasiun": slim}, ensure_ascii=False
    )


def _mode_categories(_args: dict) -> str:
    data = _fetch("statusispu")
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)
    rows = [
        {
            "uid": r.get("nilai_uid"),
            "kategori": r.get("nilai"),
            "batas": r.get("batas_teks"),
            "warna": r.get("color_text"),
            "keterangan": r.get("keterangan"),
        }
        for r in data.get("rows", [])
    ]
    return json.dumps(rows, ensure_ascii=False)


_MODES = {
    "current": _mode_current,
    "station": _mode_station,
    "stations": _mode_stations,
    "categories": _mode_categories,
}


def ispu(args: dict, **kwargs) -> str:
    """Handler tool ispu — selalu balas JSON string, termasuk saat error."""
    mode = args.get("mode", "")
    handler = _MODES.get(mode)
    if handler is None:
        return json.dumps(
            {"error": f"mode tidak dikenal: {mode!r}", "valid": sorted(_MODES)},
            ensure_ascii=False,
        )
    try:
        return handler(args)
    except Exception as exc:  # noqa: BLE001 — kontrak Hermes: JSON error, bukan raise
        logger.exception("ispu tool error (mode=%s)", mode)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def register(ctx) -> None:
    """Dipanggil Hermes sekurai startup: daftarkan tool + skill bawaan."""
    ctx.register_tool(
        name="ispu",
        toolset="ispunet",
        schema=ISPU_SCHEMA,
        handler=ispu,
    )
    # Skill bawaan (read-only, namespaced: skill_view "ispunet:ispunet").
    try:
        from pathlib import Path

        skill_md = Path(__file__).parent / "skills" / "ispunet" / "SKILL.md"
        if skill_md.exists():
            ctx.register_skill("ispunet", skill_md)
    except Exception:  # noqa: BLE001 — skill opsional; tool tetap jalan
        logger.warning("gagal register skill ispunet", exc_info=True)
