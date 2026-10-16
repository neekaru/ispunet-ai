"""CLI ISPUNet: stations | current | station | categories | serve.

Penggunaan:
  ispunet stations [--limit N] [--json]
  ispunet current <lat> <lon> [--json]
  ispunet station <id_stasiun> [--json]
  ispunet categories [--json]
  ispunet serve [--host H] [--port P]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .client import IspuClient, IspuError, nearest, recommendation


def _print_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    widths = [
        max(len(title), *(len(str(r.get(key, ""))) for r in rows))
        for title, key in columns
    ]
    print("  ".join(title.ljust(w) for (title, _), w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(r.get(key, ""))[:w].ljust(w) for (_, key), w in zip(columns, widths)))


def _out(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data)


def cmd_stations(client: IspuClient, args: argparse.Namespace) -> int:
    rows = client.stations()
    if args.limit:
        rows = rows[: args.limit]
    if args.json:
        _out(rows, True)
        return 0
    _print_table(
        rows,
        [("ID", "id_stasiun"), ("NAMA", "nama"), ("KOTA", "kota"), ("PARAM", "param"), ("ISPU", "val")],
    )
    print(f"\n{len(rows)} stasiun ditampilkan")
    return 0


def cmd_current(client: IspuClient, args: argparse.Namespace) -> int:
    rows = client.current(args.lat, args.lon)
    if not rows:
        print(f"Tidak ada stasiun di sekitar ({args.lat}, {args.lon})", file=sys.stderr)
        return 1
    primary = nearest(rows, args.lat, args.lon) or rows[0]
    if args.json:
        _out({"primary": primary, "nearby": rows}, True)
        return 0
    kategori = primary.get("kategori", {})
    print(f"Stasiun terdekat : {primary.get('nama')} ({primary.get('id_stasiun')})")
    print(f"Lokasi           : {primary.get('kota')}, {primary.get('provinsi')}")
    print(f"Jarak            : {primary.get('jarak')} m")
    print(f"Waktu            : {primary.get('waktu')}")
    print(f"ISPU             : {primary.get('val')} — {kategori.get('nilai')} ({kategori.get('color')})")
    print(f"Parameter utama  : {primary.get('param')}")
    pol = {p: primary.get(p) for p in ("pm25", "pm10", "so2", "co", "o3", "no2", "hc")}
    print(f"Konsentrasi      : {pol}")
    uid = kategori.get("nilai_uid")
    if uid:
        print(f"Rekomendasi      : {recommendation(uid)}")
    print(f"\n{len(rows) - 1} stasiun lain di sekitarnya")
    return 0


def cmd_station(client: IspuClient, args: argparse.Namespace) -> int:
    detail = client.station_detail(args.station_id)
    if args.json:
        _out(detail, True)
        return 0
    kategori = detail.get("kategori", {})
    print(f"Stasiun          : {detail.get('nama')} ({detail.get('id_stasiun')})")
    print(f"Alamat           : {detail.get('alamat')}")
    print(f"Waktu            : {detail.get('waktu')}")
    print(f"ISPU             : {detail.get('pm25')} (param {detail.get('param')}) — {kategori.get('nilai')}")
    pol = {p: detail.get(p) for p in ("pm25", "pm10", "so2", "co", "o3", "no2", "hc")}
    print(f"Konsentrasi      : {pol}")
    uid = kategori.get("nilai_uid")
    if uid:
        print(f"Rekomendasi      : {recommendation(uid)}")
    return 0


def cmd_categories(client: IspuClient, args: argparse.Namespace) -> int:
    rows = client.categories()
    if args.json:
        _out(rows, True)
        return 0
    _print_table(
        rows,
        [("KATEGORI", "nilai"), ("BATAS", "batas_teks"), ("WARNA", "color_text")],
    )
    return 0


def cmd_serve(_client: IspuClient, args: argparse.Namespace) -> int:
    import uvicorn

    from .server import app

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ispunet",
        description="Kualitas udara Indonesia (ISPU KLHK) — CLI.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--json", action="store_true", help="output JSON mentah")
        return p

    p = add("stations", "Daftar semua stasiun pemantauan")
    p.add_argument("--limit", type=int, default=0)

    p = add("current", "Kualitas udara di sekitar koordinat")
    p.add_argument("lat", type=float)
    p.add_argument("lon", type=float)

    p = add("station", "Detail satu stasiun")
    p.add_argument("station_id")

    add("categories", "Definisi kategori ISPU")

    p = sub.add_parser("serve", help="Jalankan REST API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    client = IspuClient()
    try:
        handler = {
            "stations": cmd_stations,
            "current": cmd_current,
            "station": cmd_station,
            "categories": cmd_categories,
            "serve": cmd_serve,
        }[args.cmd]
        return handler(client, args)
    except IspuError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
