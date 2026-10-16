#!/usr/bin/env python3
"""Skrip bantu skill ISPUNet — TANPA dependensi eksternal (stdlib urllib).

Pemakaian:
  ispunet.py stations [--limit N]
  ispunet.py current <lat> <lon>
  ispunet.py station <id_stasiun>
  ispunet.py categories

Output JSON ke stdout. Env opsional: ISPUNET_API_URL, ISPUNET_API_KEY,
ISPUNET_API_SIGNATURE (default: kredensial publik dari APK resmi).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("ISPUNET_API_URL", "https://ispu.kemenlh.go.id/apimob/v1/").rstrip("/") + "/"
API_KEY = os.environ.get("ISPUNET_API_KEY", "ispunet|NfdSdj49mb3Fo0f2MASkQ0YL60DqCpDX")
API_SIGNATURE = os.environ.get(
    "ISPUNET_API_SIGNATURE",
    "3a80e6b8d484a15e726e111c03e1ea97c9b3aad8cf469a218bdb3cb70fc524f5",
)

RECOMMENDATIONS = {
    1: "Sangat baik melakukan kegiatan di luar",
    2: "Kelompok sensitif: kurangi aktivitas fisik berat/lama. Semua orang masih bisa beraktivitas di luar.",
    3: "Penderita asma/jantung: ikuti petunjuk kesehatan & siapkan obat. Semua orang: kurangi aktivitas fisik lama di luar.",
    4: "Kelompok sensitif: hindari semua aktivitas di luar. Semua orang: pertimbangkan aktivitas di dalam ruangan.",
    5: "Kelompok sensitif: tetap di dalam ruangan. Semua orang: hindari semua aktivitas di luar.",
}


def fetch(action: str, cache_bust: bool = True) -> dict:
    url = BASE_URL + action.rstrip("/")
    if cache_bust and "time?=" not in url:
        url = f"{url}/time?={int(time.time() * 1000)}"
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "x-api-signature": API_SIGNATURE,
    })
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            if data.get("status", {}).get("statusCode") != 200:
                raise SystemExit(f"API error ({action}): {data.get('status')}")
            return data
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if attempt == 3:
                raise SystemExit(f"Gagal menghubungi API ISPUNet: {exc}") from exc
            time.sleep(1.5 * attempt)


def rec(uid) -> str:
    return RECOMMENDATIONS.get(int(uid), "Kategori tidak dikenal") if uid is not None else ""


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, *rest = argv

    if cmd == "stations":
        rows = fetch("getStations")["rows"]
        if "--limit" in rest:
            rows = rows[: int(rest[rest.index("--limit") + 1])]
        print(json.dumps(rows, ensure_ascii=False))
        return 0

    if cmd == "current":
        if len(rest) < 2:
            print("Pemakaian: ispunet.py current <lat> <lon>", file=sys.stderr)
            return 2
        rows = fetch(f"getData/lat/{float(rest[0])}/lng/{float(rest[1])}")["rows"]
        if not rows:
            print(json.dumps({"error": "tidak ada stasiun di sekitar koordinat"}))
            return 1
        primary = rows[0]
        out = {
            "stasiun_terdekat": {
                "id_stasiun": primary.get("id_stasiun"),
                "nama": primary.get("nama"),
                "kota": primary.get("kota"),
                "provinsi": primary.get("provinsi"),
                "waktu": primary.get("waktu"),
                "ispu": primary.get("val"),
                "param": primary.get("param"),
                "kategori": primary.get("kategori"),
                "konsentrasi": {p: primary.get(p) for p in ("pm25", "pm10", "so2", "co", "o3", "no2", "hc")},
                "rekomendasi": rec(primary.get("kategori", {}).get("nilai_uid")),
            },
            "jumlah_stasiun_sekitar": len(rows) - 1,
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    if cmd == "station":
        if not rest:
            print("Pemakaian: ispunet.py station <id_stasiun>", file=sys.stderr)
            return 2
        rows = fetch(f"getDetail/stasiun/{rest[0]}", cache_bust=False)["rows"]
        if not rows:
            print(json.dumps({"error": f"stasiun {rest[0]} tidak ditemukan"}))
            return 1
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
            "konsentrasi": {p: d.get(p) for p in ("pm25", "pm10", "so2", "co", "o3", "no2", "hc")},
            "riwayat_24jam": {
                "waktu": d.get("waktu_24_rev"),
                "pm25": d.get("pm25_24_rev"),
                "pm10": d.get("pm10_24_rev"),
            },
            "rekomendasi": rec(d.get("kategori", {}).get("nilai_uid")),
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    if cmd == "categories":
        print(json.dumps(fetch("statusispu")["rows"], ensure_ascii=False))
        return 0

    print(f"Perintah tidak dikenal: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
