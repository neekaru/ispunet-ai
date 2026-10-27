"""ISPUNet Hermes plugin — tool `ispu`.

Registrasi: register(ctx) dipanggil sekali saat startup Hermes.
Handler menerima args (dict) dan WAJIB mengembalikan string JSON.

Logika data ada di `normalize.py` + `core.py` (salinan verbatim dari paket
`ispunet/`); modul ini hanya transport stdlib + skema tool.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .core import IspuCore, IspuError, StationNotFound, resolve_city
from .normalize import OFFLINE_RECOMMENDATION, POLLUTANTS, STALE_HOURS

logger = logging.getLogger(__name__)

_MODE_HELP = {
    "current": "udara di koordinat / nama kota (lat+lon ATAU kota)",
    "station": "detail satu stasiun + riwayat 24 jam bersih (station_id)",
    "stations": "daftar stasiun; bisa q/provinsi/kota/hanya_aktif/limit",
    "compare": "bandingkan beberapa stasiun/kota sekaligus (targets)",
    "categories": "definisi 5 kategori ISPU",
}

ISPU_SCHEMA = {
    "name": "ispu",
    "description": (
        "Kualitas udara Indonesia (ISPU, resmi KLHK). Gunakan saat user bertanya "
        "udara/ISPU/polusi di Indonesia. Mode: 'current' (lat+lon atau kota), "
        "'station' (detail + riwayat 24 jam, station_id), 'stations' (cari/daftar "
        "stasiun), 'compare' (bandingkan beberapa kota/stasiun sekaligus), "
        "'categories'. Data selalu menyertakan umur_data_jam/usang — JANGAN "
        "sajikan data usang sebagai kondisi terkini."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": sorted(_MODE_HELP),
                "description": "; ".join(f"{k}={v}" for k, v in _MODE_HELP.items()),
            },
            "lat": {"type": "number", "description": "Latitude (mode current)"},
            "lon": {"type": "number", "description": "Longitude (mode current)"},
            "kota": {
                "type": "string",
                "description": (
                    "Nama kota, mis. 'Palangka Raya'. mode current: dicari koordinatnya "
                    "lalu stasiun terdekat dipilih. mode stations: filter kota."
                ),
            },
            "station_id": {
                "type": "string",
                "description": "ID stasiun, mis. DKI1 (mode station). Huruf besar/kecil bebas.",
            },
            "q": {
                "type": "string",
                "description": "Cari id/nama/kota/provinsi (mode stations)",
            },
            "provinsi": {"type": "string", "description": "Filter provinsi (mode stations)"},
            "hanya_aktif": {
                "type": "boolean",
                "description": "Hanya stasiun yang melaporkan ISPU (mode stations)",
            },
            "order": {
                "type": "string",
                "enum": ["wilayah", "ispu"],
                "description": "Urutan deterministik (mode stations)",
            },
            "limit": {
                "type": "integer",
                "description": "Batasi jumlah stasiun (mode stations), dipotong setelah diurutkan",
            },
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Daftar id stasiun / nama kota (mode compare)",
            },
            "history": {
                "type": "boolean",
                "description": "Sertakan riwayat 24 jam (mode station, default true)",
            },
        },
        "required": ["mode"],
    },
}

def _fetch(action: str, timeout: float = 20.0) -> dict[str, Any]:
    """GET ke API mobile ISPUNet. Murni stdlib agar plugin tanpa python_dependencies."""
    base = (
        os.environ.get("ISPUNET_API_URL", "https://ispu.kemenlh.go.id/apimob/v1/")
        .rstrip("/")
        + "/"
    )
    url = base + action.rstrip("/")
    # getDetail menolak query tambahan; endpoint lain diberi cache-buster seperti app asli.
    if not action.startswith("getDetail/") and "time?=" not in url:
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
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode()
            except Exception:  # noqa: BLE001
                pass
            # Upstream: HTTP 400 {"statusDesc": "Too Many Attempts."} saat terlalu rapat.
            if "too many attempts" in body.lower():
                last_exc = IspuError("rate limit upstream: Too Many Attempts.")
                if attempt < 3:
                    time.sleep(2.5 * attempt)
                    continue
                raise IspuError(
                    f"API {action}: rate limit upstream (Too Many Attempts) — coba lagi nanti"
                ) from exc
            raise IspuError(f"API {action}: HTTP {exc.code} {body[:200]}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_exc = exc
            time.sleep(1.0 * attempt)
            continue
        status = data.get("status") or {}
        if status.get("statusCode") != 200:
            raise IspuError(f"API {action}: {status}")
        return data
    raise IspuError(f"gagal menghubungi API ISPUNet: {last_exc}")

_CORE = IspuCore(_fetch)

def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)

def _error(message: str, **extra: Any) -> str:
    return _dump({"error": message, **extra})

def _mode_current(args: dict) -> str:
    lat, lon = args.get("lat"), args.get("lon")
    kota = args.get("kota")
    if lat is None or lon is None:
        if not kota:
            return _error(
                "mode current butuh lat+lon, atau 'kota' (mis. 'Palangka Raya')",
                kota_dikenal=sorted({"palangka raya", "banjarmasin", "pekanbaru", "samarinda"}),
            )
        if resolve_city(kota) is None:
            return _error(
                f"kota {kota!r} tidak ada di tabel koordinat bawaan",
                saran="kirim lat/lon eksplisit",
            )
    out = _CORE.current(lat, lon, kota=kota)
    if out["primary"] is None:
        return _error(out["alasan_pemilihan"], nearby=out["nearby"], catatan=out["catatan"])
    return _dump(out)

def _mode_station(args: dict) -> str:
    sid = str(args.get("station_id") or "").strip()
    if not sid:
        return _error("mode station butuh station_id (mis. DKI1)")
    try:
        detail = _CORE.station_detail(sid, history=bool(args.get("history", True)))
    except StationNotFound as exc:
        return _dump({
            "error": str(exc),
            "saran_id": exc.saran,
            "pengganti": exc.pengganti,
            "mirip": exc.mirip,
            "catatan": (
                "jangan mengarang data: laporkan stasiun tidak ada, lalu tawarkan "
                "pengganti di atas atau mode current dengan lat/lon kota"
            ),
        })
    return _dump(detail)

def _mode_stations(args: dict) -> str:
    limit = args.get("limit")
    order = str(args.get("order") or "wilayah")
    rows = _CORE.stations(
        q=args.get("q"),
        provinsi=args.get("provinsi"),
        kota=args.get("kota") or None,
        hanya_aktif=bool(args.get("hanya_aktif", False)),
        order=order,
    )
    total = len(rows)
    shown = rows[:limit] if isinstance(limit, int) and limit > 0 else rows
    payload: dict[str, Any] = {
        "total": total,
        "ditampilkan": len(shown),
        "urutan": order,
        "stasiun": shown,
        "catatan": (
            "getStations tidak memuat semua stasiun aktif (mis. Palangka Raya, "
            "Banjar Baru, Perawang); untuk kota itu pakai mode current atau compare"
        ),
    }
    query = args.get("q")
    if total == 0 and query and resolve_city(str(query)):
        payload["saran"] = (
            f"{query!r} dikenal sebagai kota, tetapi tidak ada stasiun ber-ID itu di "
            f"getStations — pakai mode current dengan kota={query!r}"
        )
    return _dump(payload)

def _mode_compare(args: dict) -> str:
    targets = args.get("targets")
    if isinstance(targets, str):
        targets = [t.strip() for t in targets.split(",") if t.strip()]
    if not targets:
        return _error("mode compare butuh 'targets' (daftar id stasiun atau nama kota)")
    return _dump(_CORE.compare([str(t) for t in targets]))

def _mode_categories(_args: dict) -> str:
    return _dump(_CORE.categories())

_MODES = {
    "current": _mode_current,
    "station": _mode_station,
    "stations": _mode_stations,
    "compare": _mode_compare,
    "categories": _mode_categories,
}

def ispu(args: dict, **kwargs) -> str:
    """Handler tool ispu — selalu balas JSON string, termasuk saat error."""
    mode = args.get("mode", "")
    handler = _MODES.get(mode)
    if handler is None:
        return _error(f"mode tidak dikenal: {mode!r}", valid=sorted(_MODES))
    try:
        return handler(args)
    except IspuError as exc:
        return _error(str(exc))
    except Exception as exc:  # noqa: BLE001 — kontrak Hermes: JSON error, bukan raise
        logger.exception("ispu tool error (mode=%s)", mode)
        return _error(str(exc))

def register(ctx) -> None:
    """Dipanggil Hermes sekali saat startup: daftarkan tool + skill bawaan."""
    ctx.register_tool(
        name="ispu",
        toolset="ispunet",
        schema=ISPU_SCHEMA,
        handler=ispu,
    )
    try:
        from pathlib import Path

        skill_md = Path(__file__).parent / "skills" / "ispunet" / "SKILL.md"
        if skill_md.exists():
            ctx.register_skill("ispunet", skill_md)
    except Exception:  # noqa: BLE001 — skill opsional; tool tetap jalan
        logger.warning("gagal register skill ispunet", exc_info=True)

__all__ = [
    "ISPU_SCHEMA", "ispu", "register",
    "POLLUTANTS", "STALE_HOURS", "OFFLINE_RECOMMENDATION",
]
