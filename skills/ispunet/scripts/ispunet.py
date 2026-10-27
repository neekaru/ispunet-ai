#!/usr/bin/env python3
"""Skrip bantu skill ISPUNet — TANPA dependensi eksternal (stdlib urllib).

Pemakaian:
  ispunet.py stations [--q TEKS] [--provinsi P] [--kota K] [--aktif] [--order wilayah|ispu] [--limit N]
  ispunet.py search <teks> [--limit N]
  ispunet.py current <lat> <lon>        |  ispunet.py current --kota "Palangka Raya"
  ispunet.py station <id_stasiun> [--no-history]
  ispunet.py compare <target> [<target> ...]
  ispunet.py categories

Output JSON ke stdout. Env opsional: ISPUNET_API_URL, ISPUNET_API_KEY,
ISPUNET_API_SIGNATURE (default: kredensial publik dari APK resmi).

Logika data ada di `core.py` + `normalize.py` (salinan verbatim dari paket
`ispunet/`), jadi perilakunya identik dengan library/plugin.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from core import IspuCore, IspuError, StationNotFound

BASE_URL = os.environ.get("ISPUNET_API_URL", "https://ispu.kemenlh.go.id/apimob/v1/").rstrip("/") + "/"
API_KEY = os.environ.get("ISPUNET_API_KEY", "ispunet|NfdSdj49mb3Fo0f2MASkQ0YL60DqCpDX")
API_SIGNATURE = os.environ.get(
    "ISPUNET_API_SIGNATURE",
    "3a80e6b8d484a15e726e111c03e1ea97c9b3aad8cf469a218bdb3cb70fc524f5",
)

def fetch(action: str) -> dict:
    """GET ke API ISPUNet; cache-buster untuk semua endpoint kecuali getDetail."""
    url = BASE_URL + action.rstrip("/")
    if not action.startswith("getDetail/") and "time?=" not in url:
        url = f"{url}/time?={int(time.time() * 1000)}"
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "x-api-signature": API_SIGNATURE,
    })
    last_exc = None
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode()
            except Exception:  # noqa: BLE001
                pass
            if "too many attempts" in body.lower() and attempt < 3:
                last_exc = IspuError("rate limit upstream: Too Many Attempts.")
                time.sleep(2.5 * attempt)
                continue
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

def _dump(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False))

def _table(rows, columns) -> None:
    widths = [max([len(t)] + [len(str(r.get(k, ""))) for r in rows]) for t, k in columns]
    print("  ".join(t.ljust(w) for (t, _), w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(r.get(k, ""))[:w].ljust(w) for (_, k), w in zip(columns, widths)))

def _status(row) -> str:
    if row.get("status") != "aktif":
        return "OFFLINE"
    return f"USANG {row['umur_data_jam']}j" if row.get("usang") else f"OK {row['umur_data_jam']}j"

def _rows(rows):
    return [{**r, "ispu": "-" if r.get("ispu") is None else r["ispu"], "status_data": _status(r)}
            for r in rows]

_COLS = [("ID", "id_stasiun"), ("NAMA", "nama"), ("KOTA", "kota"), ("ISPU", "ispu"),
         ("STATUS", "status_data")]

def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    parser = argparse.ArgumentParser(prog="ispunet.py", add_help=False)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stations")
    p.add_argument("--q")
    p.add_argument("--provinsi")
    p.add_argument("--kota")
    p.add_argument("--aktif", action="store_true")
    p.add_argument("--order", choices=["wilayah", "ispu"], default="wilayah")
    p.add_argument("--limit", type=int, default=0)

    p = sub.add_parser("search")
    p.add_argument("teks")
    p.add_argument("--limit", type=int, default=0)

    p = sub.add_parser("current")
    p.add_argument("lat", type=float, nargs="?")
    p.add_argument("lon", type=float, nargs="?")
    p.add_argument("--kota")

    p = sub.add_parser("station")
    p.add_argument("station_id")
    p.add_argument("--no-history", action="store_true")

    p = sub.add_parser("compare")
    p.add_argument("targets", nargs="+")

    sub.add_parser("categories")

    args = parser.parse_args(argv)
    core = IspuCore(fetch)

    try:
        if args.cmd == "stations":
            rows = core.stations(
                q=args.q, provinsi=args.provinsi, kota=args.kota,
                hanya_aktif=args.aktif, order=args.order,
                limit=args.limit or None,
            )
            _table(_rows(rows), _COLS)
            print(f"\n{len(rows)} stasiun (urutan: {args.order})")
            return 0

        if args.cmd == "search":
            rows = core.stations(q=args.teks, limit=args.limit or None)
            if not rows:
                print(f"Tidak ada stasiun yang cocok dengan {args.teks!r}", file=sys.stderr)
                return 1
            _table(_rows(rows), _COLS + [("PROVINSI", "provinsi")])
            return 0

        if args.cmd == "current":
            out = core.current(args.lat, args.lon, kota=args.kota)
            if out["primary"] is None:
                _dump({"error": out["alasan_pemilihan"], "nearby": out["nearby"]})
                return 1
            _dump(out)
            return 0

        if args.cmd == "station":
            try:
                detail = core.station_detail(args.station_id, history=not args.no_history)
            except StationNotFound as exc:
                _dump({
                    "error": str(exc),
                    "saran_id": exc.saran,
                    "pengganti": exc.pengganti,
                    "mirip": exc.mirip,
                })
                return 1
            _dump(detail)
            return 0

        if args.cmd == "compare":
            _dump(core.compare(args.targets))
            return 0

        if args.cmd == "categories":
            _dump(core.categories())
            return 0
    except IspuError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 2

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
