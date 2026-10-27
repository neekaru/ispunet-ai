"""CLI ISPUNet: stations | search | current | station | compare | categories | serve.

Penggunaan:
  ispunet stations [--q TEKS] [--provinsi P] [--kota K] [--aktif] [--order wilayah|ispu] [--limit N] [--json]
  ispunet search <teks> [--limit N] [--json]
  ispunet current <lat> <lon> [--json]   |   ispunet current --kota "Palangka Raya"
  ispunet station <id_stasiun> [--no-history] [--json]
  ispunet compare <target> [<target> ...] [--json]
  ispunet categories [--json]
  ispunet serve [--host H] [--port P]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .client import IspuClient, IspuError, StationNotFound, resolve_city

def _print_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    widths = [
        max([len(title)] + [len(str(r.get(key, ""))) for r in rows])
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

def _status(row: dict[str, Any]) -> str:
    if row.get("status") != "aktif":
        return "OFFLINE"
    if row.get("usang"):
        return f"USANG {row.get('umur_data_jam')}j"
    return f"OK {row.get('umur_data_jam')}j"

def _ispu_line(row: dict[str, Any]) -> str:
    if row.get("ispu") is None:
        return "TIDAK VALID — stasiun tidak melaporkan ISPU (offline)"
    kategori = row.get("kategori") or {}
    return f"{row['ispu']} — {kategori.get('nilai')} ({kategori.get('color_text')})"

def _station_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **r,
            "ispu": "-" if r.get("ispu") is None else r.get("ispu"),
            "kategori_nama": (r.get("kategori") or {}).get("nilai") or "-",
            "status_data": _status(r),
        }
        for r in rows
    ]

def cmd_stations(client: IspuClient, args: argparse.Namespace) -> int:
    rows = client.stations(
        q=args.q, provinsi=args.provinsi, kota=args.kota,
        hanya_aktif=args.aktif, order=args.order, limit=args.limit,
    )
    if args.json:
        _out(rows, True)
        return 0
    _print_table(
        _station_rows(rows),
        [("ID", "id_stasiun"), ("NAMA", "nama"), ("KOTA", "kota"),
         ("ISPU", "ispu"), ("STATUS", "status_data")],
    )
    print(f"\n{len(rows)} stasiun ditampilkan (urutan: {args.order})")
    if args.limit:
        print("catatan: getStations tidak memuat semua stasiun aktif — pakai `current --kota` untuk kota lain")
    return 0

def cmd_search(client: IspuClient, args: argparse.Namespace) -> int:
    rows = client.stations(q=args.teks, limit=args.limit)
    if args.json:
        _out(rows, True)
        return 0
    if not rows:
        print(f"Tidak ada stasiun yang cocok dengan {args.teks!r}", file=sys.stderr)
        if resolve_city(args.teks):
            print(
                f"catatan: {args.teks!r} dikenal sebagai kota, tetapi getStations tidak "
                f'memuat stasiun ber-ID itu — pakai: ispunet current --kota "{args.teks}"',
                file=sys.stderr,
            )
        return 1
    _print_table(
        _station_rows(rows),
        [("ID", "id_stasiun"), ("NAMA", "nama"), ("KOTA", "kota"),
         ("PROVINSI", "provinsi"), ("ISPU", "ispu"), ("STATUS", "status_data")],
    )
    return 0

def cmd_current(client: IspuClient, args: argparse.Namespace) -> int:
    if args.kota:
        result = client.current(kota=args.kota)
    elif args.lat is not None and args.lon is not None:
        result = client.current(args.lat, args.lon)
    else:
        print('Pemakaian: ispunet current <lat> <lon>  |  ispunet current --kota "Nama Kota"',
              file=sys.stderr)
        return 2
    if args.json:
        _out(result, True)
        return 0

    primary = result["primary"]
    if primary is None:
        print("Tidak ada stasiun aktif di sekitar titik ini", file=sys.stderr)
        for note in result["catatan"]:
            print(f"catatan: {note}", file=sys.stderr)
        return 1
    print(f"Stasiun          : {primary.get('nama')} ({primary.get('id_stasiun')})")
    print(f"Lokasi           : {primary.get('kota')}, {primary.get('provinsi')}")
    print(f"Jarak            : {primary.get('jarak_m')} m")
    print(f"Waktu            : {primary.get('waktu')} ({primary.get('umur_data_jam')} jam lalu)")
    print(f"ISPU             : {_ispu_line(primary)}")
    print(f"Parameter utama  : {primary.get('param')}")
    print(f"Indeks polutan   : {primary.get('indeks')}")
    print(f"Konsentrasi rata : {primary.get('konsentrasi_rata_rata')} µg/m³ (24 jam)")
    print(f"Rekomendasi      : {primary.get('rekomendasi')}")
    for warning in primary.get("peringatan") or []:
        print(f"PERINGATAN       : {warning}")
    for note in result["catatan"]:
        print(f"catatan          : {note}")
    print(f"\n{result['jumlah_stasiun_sekitar']} stasiun lain di sekitarnya")
    return 0

def cmd_station(client: IspuClient, args: argparse.Namespace) -> int:
    try:
        detail = client.station_detail(args.station_id, history=not args.no_history)
    except StationNotFound as exc:
        if args.json:
            _out({
                "error": str(exc),
                "saran_id": exc.saran,
                "pengganti": exc.pengganti,
                "mirip": exc.mirip,
            }, True)
        else:
            print(f"Error: {exc}", file=sys.stderr)
            if exc.pengganti:
                print("\nStasiun pengganti (aktif & terdekat):", file=sys.stderr)
                _print_table(
                    _station_rows(exc.pengganti),
                    [("ID", "id_stasiun"), ("NAMA", "nama"), ("KOTA", "kota"),
                     ("ISPU", "ispu"), ("STATUS", "status_data")],
                )
        return 1
    if args.json:
        _out(detail, True)
        return 0

    print(f"Stasiun          : {detail.get('nama')} ({detail.get('id_stasiun')})")
    print(f"Alamat           : {detail.get('alamat')}")
    print(f"Waktu            : {detail.get('waktu')} ({detail.get('umur_data_jam')} jam lalu)")
    print(f"ISPU             : {_ispu_line(detail)}")
    print(f"Parameter utama  : {detail.get('param')}")
    print(f"Indeks polutan   : {detail.get('indeks')}")
    print(f"Indeks maks 24j  : {detail.get('indeks_maks_24jam')}")
    print(f"Kategori angka   : {detail.get('kategori_angka')}")
    print(f"Konsentrasi rata : {detail.get('konsentrasi_rata_rata')} µg/m³ (24 jam)")
    print(f"Rekomendasi      : {detail.get('rekomendasi')}")
    for warning in detail.get("peringatan") or []:
        print(f"PERINGATAN       : {warning}")
    history = detail.get("riwayat_24jam")
    if history:
        print(
            f"\nRiwayat 24 jam   : {history['slot']} slot, "
            f"{history['mulai']} → {history['selesai']}"
        )
        print(f"Cakupan          : {history['cakupan']}")
        for note in history["catatan"]:
            print(f"catatan riwayat  : {note}")
    for alt in detail.get("pengganti") or []:
        print(
            f"pengganti        : {alt['id_stasiun']} ({alt['nama']}) ISPU {alt['ispu']} "
            f"— {alt['umur_data_jam']} jam"
        )
    return 0

def cmd_compare(client: IspuClient, args: argparse.Namespace) -> int:
    result = client.compare(args.targets)
    if args.json:
        _out(result, True)
        return 0
    if not result["perbandingan"]:
        print("Tidak ada target yang ditemukan", file=sys.stderr)
        for miss in result["tidak_ditemukan"]:
            print(f"  {miss['target']}: {miss['alasan']}", file=sys.stderr)
        return 1
    _print_table(
        _station_rows(result["perbandingan"]),
        [("DICARI", "dicari_dengan"), ("ID", "id_stasiun"), ("KOTA", "kota"),
         ("ISPU", "ispu"), ("KATEGORI", "kategori_nama"), ("STATUS", "status_data")],
    )
    for miss in result["tidak_ditemukan"]:
        print(f"\ntidak ditemukan: {miss['target']} — {miss['alasan']}", file=sys.stderr)
    return 0

def cmd_categories(client: IspuClient, args: argparse.Namespace) -> int:
    rows = client.categories()
    if args.json:
        _out(rows, True)
        return 0
    _print_table(
        rows,
        [("KATEGORI", "kategori"), ("BATAS", "batas"), ("WARNA", "warna")],
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
        p.add_argument("--json", action="store_true", help="output JSON")
        return p

    p = add("stations", "Daftar semua stasiun pemantauan")
    p.add_argument("--q", help="cari id/nama/kota/provinsi")
    p.add_argument("--provinsi", help="filter provinsi")
    p.add_argument("--kota", help="filter kota")
    p.add_argument("--aktif", action="store_true", help="hanya stasiun yang melaporkan ISPU")
    p.add_argument("--order", choices=["wilayah", "ispu"], default="wilayah")
    p.add_argument("--limit", type=int, default=0)

    p = add("search", "Cari stasiun berdasarkan nama/kota/provinsi")
    p.add_argument("teks")
    p.add_argument("--limit", type=int, default=0)

    p = add("current", "Kualitas udara di sekitar koordinat / kota")
    p.add_argument("lat", type=float, nargs="?")
    p.add_argument("lon", type=float, nargs="?")
    p.add_argument("--kota", help="nama kota, mis. 'Palangka Raya'")

    p = add("station", "Detail satu stasiun + riwayat 24 jam")
    p.add_argument("station_id")
    p.add_argument("--no-history", action="store_true", help="lewati riwayat 24 jam")

    p = add("compare", "Bandingkan beberapa stasiun/kota sekaligus")
    p.add_argument("targets", nargs="+", help="id stasiun atau nama kota")

    add("categories", "Definisi kategori ISPU")

    p = sub.add_parser("serve", help="Jalankan REST API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    client = IspuClient()
    try:
        handler = {
            "stations": cmd_stations,
            "search": cmd_search,
            "current": cmd_current,
            "station": cmd_station,
            "compare": cmd_compare,
            "categories": cmd_categories,
            "serve": cmd_serve,
        }[args.cmd]
        return handler(client, args)
    except IspuError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
