"""Normalisasi data mentah ISPUNet — stdlib murni, tanpa dependensi.

Modul ini SATU-SATUNYA sumber logika pembersihan data ISPUNet:

- paket `ispunet` (client/cli/server) memakainya langsung;
- `hermes-plugin/ispunet/normalize.py` dan
  `skills/ispunet/scripts/normalize.py` adalah SALINAN VERBATIM file ini,
  karena plugin dan skill harus standalone (tanpa paket `ispunet`).
  `tests/test_vendor_sync.py` gagal bila ketiganya tidak identik.

Bug upstream yang ditangani di sini (lihat README bagian "Cacat data upstream"):

1. `waktu` punya dua format (`2026-10-27 20:00:00` dan `27-Oktober-2026 20:00:00`)
   dan zona waktu hanya ada di sebagian endpoint (`time_z` WIB/WITA/WIT).
2. `waktu_24_rev` hanya jam:menit:detik sehingga 24 slot terlihat punya
   timestamp duplikat (Palangka Raya: 07:00-17:00 lalu 08:00-20:00).
   Timestamp otoritatif adalah `waktu_24` (tanggal + jam).
3. Seri 24 jam bisa bolong di tengah (PM10 Sampit null 04:00-16:00), punya
   celah antar hari, atau duplikat persis.
4. Nilai konsentrasi bisa di luar skala ISPU (Palangka Raya PM2.5 1252,
   PM10 4091 µg/m³) — ditandai, TIDAK dibuang.
5. `is_maintenance` konstan (selalu `"0"` pada 107 stasiun) sehingga tidak
   berguna; status stasiun diturunkan dari data (`aktif`/`offline`/`usang`).
6. `getStations` tidak memuat semua stasiun aktif (Palangka Raya, Banjar Baru,
   Perawang, Mobile AQMS Kalteng hanya muncul di `getData/lat/lng`) dan
   `waktu` di sana bisa sangat basi (Perawang Des-2024).
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from typing import Any

POLLUTANTS = ("pm25", "pm10", "so2", "co", "o3", "no2", "hc")

POLLUTANT_LABEL = {
    "pm25": "PM2.5",
    "pm10": "PM10",
    "so2": "SO2",
    "co": "CO",
    "o3": "O3",
    "no2": "NO2",
    "hc": "HC",
}

# Batas atas tabel konversi Permen LHK P.14/2020 (ISPU 500), µg/m³.
# Dipakai untuk field konsentrasi `a_*`; di atas ini nilai ditandai, tidak dibuang.
KONSENTRASI_MAX = {
    "pm10": 500.0,
    "pm25": 500.0,
    "so2": 1200.0,
    "co": 45000.0,
    "o3": 1000.0,
    "no2": 3000.0,
    "hc": 648.0,
}

ISPU_MAX = 500  # indeks di atas ini melampaui skala Permen LHK (tetap dilaporkan upstream)

STALE_HOURS = 3.0  # data lebih tua dari ini dianggap usang
OFFLINE_RECOMMENDATION = "TIDAK VALID / stasiun offline"

RECOMMENDATIONS: dict[int, str] = {
    1: "Sangat baik melakukan kegiatan di luar",
    2: (
        "Kelompok sensitif: kurangi aktivitas fisik yang terlalu lama atau berat. "
        "Setiap orang: masih dapat beraktivitas di luar."
    ),
    3: (
        "Penderita asma: harus mengikuti petunjuk kesehatan untuk asma dan menyimpan obat asma. "
        "Penderita penyakit jantung: gejala seperti palpitasi, sesak napas, atau kelelahan yang "
        "tidak biasa mungkin mengindikasikan masalah serius. "
        "Setiap orang: mengurangi aktivitas fisik yang terlalu lama di luar ruangan."
    ),
    4: (
        "Kelompok sensitif: hindari semua aktivitas di luar. Perbanyak aktivitas di dalam ruangan "
        "atau lakukan penjadwalan ulang pada waktu dengan kualitas udara yang baik. "
        "Setiap orang: hindari aktivitas fisik yang terlalu lama di luar ruangan, pertimbangkan "
        "untuk melakukan aktivitas di dalam ruangan."
    ),
    5: (
        "Kelompok sensitif: tetap di dalam ruangan dan hanya melakukan sedikit aktivitas. "
        "Setiap orang: hindari semua aktivitas di luar."
    ),
}

_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12,
}

_TZ_BY_NAME = {"WIB": 7, "WITA": 8, "WIT": 9}
_TZ_BY_OFFSET = {0: 7, 1: 8, 2: 9}

# Cadangan saat endpoint tidak mengirim `time_z` (getData/lat/lng tidak mengirim).
# Kunci dicocokkan sebagai substring pada provinsi (huruf kecil).
_TZ_BY_PROVINCE = {
    "kalimantan selatan": 8, "kalimantan timur": 8, "kalimantan utara": 8,
    "kalimantan barat": 7, "kalimantan tengah": 7,
    "bali": 8, "nusa tenggara barat": 8, "nusa tenggara timur": 8,
    "maluku": 9, "papua": 9,
    "sulawesi": 8,
    "sumatera": 7, "aceh": 7, "jambi": 7, "riau": 7, "bengkulu": 7,
    "lampung": 7, "bangka belitung": 7, "kepulauan riau": 7,
    "jakarta": 7, "jawa": 7, "banten": 7, "yogyakarta": 7,
}

_RE_DMY = re.compile(r"^(\d{1,2})-([A-Za-z]+)-(\d{4})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$")
_RE_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$")
_RE_TAG = re.compile(r"<[^>]+>")
_RE_SLUG = re.compile(r"[^a-z0-9]+")


# --------------------------------------------------------------------- waktu
def tz_offset(time_z: str | None = None, provinsi: str | None = None,
              time_offset: Any = None) -> int:
    """Offset jam terhadap UTC: `time_z` → `time_offset` → provinsi → WIB."""
    if time_z:
        off = _TZ_BY_NAME.get(str(time_z).strip().upper())
        if off is not None:
            return off
    try:
        off = _TZ_BY_OFFSET.get(int(time_offset))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        off = None
    if off is not None:
        return off
    prov = str(provinsi or "").strip().lower()
    for key, off in _TZ_BY_PROVINCE.items():
        if key in prov:
            return off
    return 7


def parse_time(text: Any, offset: int = 7) -> dt.datetime | None:
    """Parse `waktu` ISPUNet (kedua format) menjadi datetime aware `offset` jam."""
    if not text:
        return None
    raw = str(text).strip()
    m = _RE_YMD.match(raw)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        parts = (int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0))
    else:
        m = _RE_DMY.match(raw)
        if not m:
            return None
        d, month, y, hh, mm, ss = m.groups()
        mo = _MONTHS.get(month.lower()[:3]) or _MONTHS.get(month.lower())
        if mo is None:
            return None
        parts = (int(y), mo, int(d), int(hh), int(mm), int(ss or 0))
    try:
        naive = dt.datetime(*parts)
    except ValueError:
        return None
    return naive.replace(tzinfo=dt.timezone(dt.timedelta(hours=offset)))


def parse_clock(text: Any, tanggal: str | None, offset: int) -> dt.datetime | None:
    """Gabungkan `HH:MM:SS` (`waktu_24_rev`) dengan `YYYY-MM-DD` (`tanggal_24_rev`)."""
    if not text or not tanggal:
        return None
    clock = str(text).strip()
    date = parse_time(f"{str(tanggal).strip()} {clock}", offset)
    return date


def to_iso(moment: dt.datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def age_hours(moment: dt.datetime | None, now: dt.datetime | None = None) -> float | None:
    """Umur data dalam jam (dibulatkan 1 desimal); negatif (jam stasiun lebih maju) → 0."""
    if moment is None:
        return None
    ref = now or dt.datetime.now(dt.timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=dt.timezone.utc)
    delta = (ref - moment).total_seconds() / 3600.0
    return round(max(0.0, delta), 1)


# -------------------------------------------------------------------- angka
def to_number(value: Any) -> float | None:
    """Angka dari API (string/float) → float; `None`, `""`, `"-"` → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text or text in {"-", "--", "N/A", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    number = to_number(value)
    return int(number) if number is not None else None


def _clean_param(param: Any) -> str | None:
    text = _RE_TAG.sub("", str(param or "")).strip()
    return None if text in {"", "-", "--"} else text


def pollutant_keys(param: Any) -> list[str]:
    """`PM<sub>2.5</sub>,O<sub>3</sub>` → `["pm25", "o3"]`."""
    text = _RE_TAG.sub("", str(param or "")).upper()
    keys: list[str] = []
    for token in re.split(r"[,;/]+", text):
        token = token.replace(" ", "").replace(".", "")
        mapping = {
            "PM25": "pm25", "PM2.5": "pm25", "PM10": "pm10",
            "SO2": "so2", "CO": "co", "O3": "o3", "NO2": "no2", "HC": "hc",
        }
        key = mapping.get(token)
        if key and key not in keys:
            keys.append(key)
    return keys


def suspect_reason(pollutant: str, value: float | None, *, kind: str = "indeks") -> str | None:
    """Alasan nilai dianggap mencurigakan, atau None bila wajar.

    `kind="indeks"` untuk nilai ISPU (skala resmi 0-500), `kind="konsentrasi"`
    untuk `a_*` (µg/m³, batas atas tabel konversi Permen LHK P.14/2020).
    """
    if value is None:
        return None
    if value < 0:
        return "nilai negatif"
    if kind == "indeks":
        if value > ISPU_MAX:
            return f"melampaui skala ISPU (maks {ISPU_MAX}); nilai ekstrapolasi upstream"
        return None
    limit = KONSENTRASI_MAX.get(pollutant)
    if limit is not None and value > limit:
        return f"di luar tabel konversi ISPU (>{limit:g} µg/m³)"
    return None


def recommendation(uid: Any) -> str:
    """Rekomendasi kesehatan untuk `nilai_uid`; `None` → penanda stasiun tidak valid."""
    number = _int_or_none(uid)
    if number is None:
        return OFFLINE_RECOMMENDATION
    return RECOMMENDATIONS.get(number, "Kategori tidak dikenal.")


# ------------------------------------------------------------------ stasiun
def normalize_station(raw: dict[str, Any], *, now: dt.datetime | None = None,
                      distance: float | None = None) -> dict[str, Any]:
    """Satu baris stasiun (getStations / getData / getDetail) → bentuk seragam."""
    offset = tz_offset(raw.get("time_z"), raw.get("provinsi"), raw.get("time_offset"))
    waktu = parse_time(raw.get("waktu"), offset)
    umur = age_hours(waktu, now)

    kategori = raw.get("kategori") or {}
    uid = _int_or_none(kategori.get("nilai_uid"))
    ispu = to_number(raw.get("val"))
    aktif = uid is not None and ispu is not None

    # Semantik field upstream — diverifikasi pada 10 detail stasiun penuh,
    # 27-Okt-2026 (60 kombinasi polutan): `<pol>` = ISPU(a_<pol>) selalu cocok
    # kecuali saat a_<pol> = 0 (lubang data DKI*).
    #   a_<pol>          = KONSENTRASI rata-rata 24 jam, µg/m³ (desimal)
    #   pm25..hc         = INDEKS ISPU per polutan, dihitung dari a_<pol>
    #   val              = indeks tertinggi (polutan kritis) = max(indeks)
    #   c_<pol>          = nomor kategori (1..5) untuk indeks <pol>
    #   <pol>_24_max     = indeks maksimum 24 jam
    #   t_<pol>          = TIDAK dipakai: hanya cocok untuk PM2.5, berbeda jauh
    #                      untuk polutan lain (mis. t_pm10 KTM 1427 vs ISPU 338)
    indeks = {p: _int_or_none(raw.get(p)) for p in POLLUTANTS}
    konsentrasi_rata_rata = {p: to_number(raw.get("a_" + p)) for p in POLLUTANTS}
    kategori_angka = {p: _int_or_none(raw.get("c_" + p)) for p in POLLUTANTS}
    indeks_maks = {p: _int_or_none(raw.get(p + "_24_max")) for p in POLLUTANTS}

    # getStations/getData tidak mengirim indeks per polutan (hanya a_*); jangan
    # tampilkan dict berisi null semua — itu terbaca seperti "tidak ada data".
    if all(v is None for v in indeks.values()):
        indeks = None
    if all(v is None for v in kategori_angka.values()):
        kategori_angka = None
    if all(v is None for v in indeks_maks.values()):
        indeks_maks = None

    mencurigakan = []
    for p in POLLUTANTS:
        for label, value, kind in (
            ("indeks", (indeks or {}).get(p), "indeks"),
            ("indeks_maks_24jam", (indeks_maks or {}).get(p), "indeks"),
            ("konsentrasi_rata_rata", konsentrasi_rata_rata[p], "konsentrasi"),
        ):
            reason = suspect_reason(p, value, kind=kind)
            if reason:
                mencurigakan.append({
                    "field": f"{label}.{p}", "nilai": value, "alasan": reason,
                })
    if ispu is not None:
        reason = suspect_reason("val", ispu, kind="indeks")
        if reason:
            mencurigakan.append({"field": "ispu", "nilai": ispu, "alasan": reason})

    # Rata-rata 0 padahal ada indeks > 0 = kontradiksi (DKI1/2/4/5: a_pm25 = 0
    # sementara pm25 = 105). Jangan sajikan 0 sebagai rata-rata yang sah.
    for p in POLLUTANTS:
        avg = konsentrasi_rata_rata[p]
        idx = (indeks or {}).get(p)
        if avg == 0 and idx is not None and idx > 0:
            mencurigakan.append({
                "field": f"konsentrasi_rata_rata.{p}",
                "nilai": avg,
                "alasan": f"rata-rata 0 tetapi indeks ISPU {idx} — lubang data upstream",
            })

    peringatan: list[str] = []
    if not aktif:
        peringatan.append("stasiun tidak melaporkan nilai ISPU (offline / nilai tidak valid)")
    if umur is None:
        peringatan.append("waktu pengukuran tidak diketahui")
    elif umur > STALE_HOURS:
        peringatan.append(
            f"data terakhir {umur:g} jam lalu (ambang {STALE_HOURS:g} jam) — bukan kondisi terkini"
        )
    if mencurigakan:
        nama = sorted({m["field"].split(".")[0] for m in mencurigakan})
        peringatan.append(
            f"{len(mencurigakan)} nilai di luar batas wajar ({', '.join(nama)}) — "
            "nilai dipertahankan apa adanya, jangan dipakai tanpa verifikasi"
        )

    jarak = distance if distance is not None else to_number(raw.get("jarak"))
    return {
        "id_stasiun": raw.get("id_stasiun"),
        "nama": raw.get("nama"),
        "kota": raw.get("kota"),
        "provinsi": raw.get("provinsi"),
        "alamat": raw.get("alamat"),
        "kecamatan": raw.get("kecamatan") or None,
        "kelurahan": raw.get("kelurahan") or None,
        "lat": to_number(raw.get("lat")),
        "lon": to_number(raw.get("lon")),
        "jarak_m": jarak,
        "waktu": raw.get("waktu"),
        "waktu_iso": to_iso(waktu),
        "zona_waktu": f"UTC+{offset}",
        "umur_data_jam": umur,
        "usang": umur is None or umur > STALE_HOURS,
        "status": "aktif" if aktif else "offline",
        "ispu": int(ispu) if ispu is not None else None,
        "kategori": kategori or None,
        "cat": kategori.get("nilai") or None,
        "param": _clean_param(raw.get("param")),
        "param_polutan": pollutant_keys(raw.get("param")),
        "indeks": indeks,
        "indeks_maks_24jam": indeks_maks,
        "kategori_angka": kategori_angka,
        "konsentrasi_rata_rata": konsentrasi_rata_rata,
        "is_maintenance": raw.get("is_maintenance"),
        "rekomendasi": recommendation(uid),
        "peringatan": peringatan,
        "mencurigakan": mencurigakan,
    }


def nearest(rows: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    """Stasiun terdekat dari baris `getData/lat/lng` (sudah terurut jarak; ini pengaman)."""
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_d = float("inf")
    for row in rows:
        r_lat = to_number(row.get("lat"))
        r_lon = to_number(row.get("lon"))
        if r_lat is None or r_lon is None:
            continue
        d = (r_lat - lat) ** 2 + (r_lon - lon) ** 2
        if d < best_d:
            best, best_d = row, d
    return best or rows[0]


def pick_best(rows: list[dict[str, Any]], lat: float | None = None,
              lon: float | None = None) -> tuple[dict[str, Any] | None, str]:
    """Pilih stasiun terbaik: segar dulu, baru jarak; stasiun offline tidak pernah dipilih.

    Mengembalikan (stasiun, alasan). Alasan menjelaskan mengapa stasiun itu dipilih.
    """
    aktif = [r for r in rows if r.get("status") == "aktif"]
    if not aktif:
        return None, "semua stasiun di sekitar tidak melaporkan nilai ISPU (offline)"

    def jarak(row: dict[str, Any]) -> float:
        value = row.get("jarak_m")
        if value is not None:
            return float(value)
        r_lat, r_lon = row.get("lat"), row.get("lon")
        if lat is not None and lon is not None and r_lat is not None and r_lon is not None:
            return (float(r_lat) - lat) ** 2 + (float(r_lon) - lon) ** 2
        return float("inf")

    segar = [r for r in aktif if not r.get("usang")]
    if segar:
        return min(segar, key=jarak), "stasiun aktif dengan data terbaru"
    return min(aktif, key=jarak), "stasiun aktif terdekat, tetapi datanya usang"


def _slug(text: Any) -> str:
    return _RE_SLUG.sub("", str(text or "").lower())


def search_stations(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Cari stasiun berdasarkan id/nama/kota/provinsi/kecamatan (case & spasi longgar)."""
    q = str(query or "").strip()
    if not q:
        return list(rows)
    q_slug = _slug(q)
    q_low = q.lower()
    out = []
    for row in rows:
        fields = (
            row.get("id_stasiun"), row.get("nama"), row.get("kota"),
            row.get("provinsi"), row.get("kecamatan"), row.get("kelurahan"),
        )
        if any(q_low in str(f or "").lower() for f in fields) or any(
            q_slug and q_slug in _slug(f) for f in fields
        ):
            out.append(row)
    return out


def suggest(rows: list[dict[str, Any]], query: str, limit: int = 3) -> list[str]:
    """Saran id stasiun mirip (dipakai saat id tidak ditemukan)."""
    target = _slug(query)
    if not target:
        return []
    pool: dict[str, str] = {}
    for row in rows:
        sid = row.get("id_stasiun")
        if sid:
            pool[_slug(sid)] = sid
            pool[_slug(row.get("nama"))] = sid
            pool[_slug(row.get("kota"))] = sid
    close = difflib.get_close_matches(target, list(pool), n=limit * 2, cutoff=0.6)
    out: list[str] = []
    for key in close:
        sid = pool[key]
        if sid not in out:
            out.append(sid)
        if len(out) >= limit:
            break
    return out


def sort_stations(rows: list[dict[str, Any]], order: str = "wilayah") -> list[dict[str, Any]]:
    """Urutan deterministik supaya `limit` selalu memotong subset yang sama."""
    if order == "ispu":
        return sorted(
            rows,
            key=lambda r: (
                r.get("ispu") is None,
                -(r.get("ispu") or 0),
                str(r.get("id_stasiun") or ""),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (
            str(r.get("provinsi") or "").lower(),
            str(r.get("kota") or "").lower(),
            str(r.get("nama") or "").lower(),
            str(r.get("id_stasiun") or ""),
        ),
    )


def filter_stations(rows: list[dict[str, Any]], *, query: str | None = None,
                    provinsi: str | None = None, kota: str | None = None,
                    hanya_aktif: bool = False) -> list[dict[str, Any]]:
    """Filter stasiun: pencarian bebas, provinsi, kota, dan/atau hanya yang aktif."""
    out = search_stations(rows, query) if query else list(rows)
    if provinsi:
        out = [r for r in out if str(provinsi).lower() in str(r.get("provinsi") or "").lower()]
    if kota:
        out = [r for r in out if str(kota).lower() in str(r.get("kota") or "").lower()]
    if hanya_aktif:
        out = [r for r in out if r.get("status") == "aktif"]
    return out


def compare_stations(rows: list[dict[str, Any]], targets: list[str]) -> dict[str, Any]:
    """Bandingkan beberapa stasiun/kota sekaligus dari satu respons `getStations`.

    `targets` menerima id stasiun persis (`DKI1`) atau nama kota/provinsi (`Banjarmasin`).
    """
    hasil: list[dict[str, Any]] = []
    tidak_ditemukan: list[dict[str, Any]] = []
    dipakai: set[str] = set()

    for target in targets:
        text = str(target or "").strip()
        if not text:
            continue
        exact = [r for r in rows if str(r.get("id_stasiun") or "").lower() == text.lower()]
        match = exact or search_stations(rows, text)
        if not match:
            tidak_ditemukan.append({
                "target": text,
                "alasan": "tidak ada stasiun dengan id/nama/kota itu di daftar getStations",
                "mirip": suggest(rows, text),
                "saran": "pakai mode current dengan lat/lon kota tersebut",
            })
            continue
        for row in sort_stations(match)[:3]:
            sid = row.get("id_stasiun")
            if not sid or sid in dipakai:
                continue
            dipakai.add(sid)
            hasil.append({**row, "dicari_dengan": text})

    return {
        "jumlah": len(hasil),
        "perbandingan": sort_stations(hasil),
        "tidak_ditemukan": tidak_ditemukan,
    }


# ----------------------------------------------------------------- riwayat
def _series(raw: dict[str, Any], key: str) -> list[float | None]:
    items = raw.get(key) or []
    out: list[float | None] = []
    for item in items:
        value = item.get("nilai") if isinstance(item, dict) else item
        out.append(to_number(value))
    return out


def _history_stamps(raw: dict[str, Any], offset: int) -> tuple[list[dt.datetime | None], bool]:
    """Timestamp per slot. Utamakan `waktu_24` (tanggal+jam); `waktu_24_rev` hanya cadangan."""
    full = raw.get("waktu_24") or []
    stamps = [parse_time(item, offset) for item in full]
    if full and all(s is not None for s in stamps):
        return stamps, True

    rev = raw.get("waktu_24_rev") or []
    dates = [d for d in (raw.get("tanggal_24_rev") or []) if d]
    out: list[dt.datetime | None] = []
    date_index = 0
    prev: dt.datetime | None = None
    for clock in rev:
        current = parse_clock(clock, dates[date_index] if date_index < len(dates) else None, offset)
        if current is not None and prev is not None and current <= prev and date_index + 1 < len(dates):
            date_index += 1
            current = parse_clock(clock, dates[date_index], offset)
        out.append(current)
        prev = current
    return out, False


def normalize_history(raw: dict[str, Any], *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Seri 24 jam → slot ber-timestamp lengkap, tanpa duplikat, dengan penanda bolong."""
    offset = tz_offset(raw.get("time_z"), raw.get("provinsi"), raw.get("time_offset"))
    stamps, stamps_lengkap = _history_stamps(raw, offset)

    keys = [k for k in raw if k.endswith("_24_rev")]
    series = {k[: -len("_24_rev")]: _series(raw, k) for k in keys}
    series = {k: v for k, v in series.items() if k in POLLUTANTS}
    slots = max([len(v) for v in series.values()] + [len(stamps)])

    catatan: list[str] = []
    if not stamps_lengkap:
        catatan.append(
            "timestamp dirakit dari tanggal_24_rev + waktu_24_rev; "
            "field waktu_24 (tanggal+jam) tidak tersedia"
        )

    # Buang slot tanpa timestamp & slot dengan timestamp duplikat (simpan kemunculan pertama).
    duplikat: list[dict[str, Any]] = []
    seen: dict[dt.datetime, int] = {}
    keep: list[int] = []
    for i in range(slots):
        stamp = stamps[i] if i < len(stamps) else None
        if stamp is None:
            continue
        if stamp in seen:
            duplikat.append({"waktu": to_iso(stamp), "slot": [seen[stamp], i]})
            continue
        seen[stamp] = i
        keep.append(i)
    if duplikat:
        catatan.append(
            f"{len(duplikat)} slot punya timestamp duplikat — hanya kemunculan pertama dipakai"
        )

    keep.sort(key=lambda i: stamps[i])  # type: ignore[arg-type,return-value]
    seri: list[dict[str, Any]] = []
    for i in keep:
        entry: dict[str, Any] = {"waktu": to_iso(stamps[i])}
        for pol, values in series.items():
            entry[pol] = values[i] if i < len(values) else None
        seri.append(entry)

    celah: list[dict[str, Any]] = []
    for prev, cur in zip(keep, keep[1:]):
        a, b = stamps[prev], stamps[cur]
        if a is None or b is None:
            continue
        gap = (b - a).total_seconds() / 3600.0
        if gap > 1.5:
            celah.append({"dari": to_iso(a), "sampai": to_iso(b), "jam": round(gap, 1)})
    if celah:
        total = sum(c["jam"] for c in celah)
        catatan.append(f"{len(celah)} celah waktu pada seri (total {total:g} jam tanpa data)")

    cakupan: dict[str, Any] = {}
    hilang: dict[str, list[dict[str, Any]]] = {}
    for pol in series:
        values = [entry[pol] for entry in seri]
        ada = sum(1 for v in values if v is not None)
        cakupan[pol] = {
            "ada": ada,
            "slot": len(values),
            "persen": round(100.0 * ada / len(values)) if values else 0,
        }
        runs: list[dict[str, Any]] = []
        start = None
        for entry in seri:
            if entry[pol] is None:
                start = start or entry["waktu"]
            elif start is not None:
                runs.append({"dari": start, "sampai": entry["waktu"]})
                start = None
        if start is not None:
            runs.append({"dari": start, "sampai": seri[-1]["waktu"] if seri else start})
        if runs:
            hilang[pol] = runs

    mencurigakan: list[dict[str, Any]] = []
    for entry in seri:
        for pol in series:
            reason = suspect_reason(pol, entry[pol], kind="indeks")
            if reason:
                mencurigakan.append({
                    "waktu": entry["waktu"], "polutan": pol,
                    "nilai": entry[pol], "alasan": reason,
                })
    if mencurigakan:
        catatan.append(
            f"{len(mencurigakan)} titik seri melampaui skala ISPU 500 — nilai dipertahankan, "
            "jangan dipakai sebagai rata-rata tanpa verifikasi"
        )

    terakhir = stamps[keep[-1]] if keep else None
    umur_terakhir = age_hours(terakhir, now)
    if umur_terakhir is not None and umur_terakhir > STALE_HOURS:
        catatan.append(
            f"slot terakhir {umur_terakhir:g} jam lalu — riwayat tidak berjalan sampai sekarang"
        )

    return {
        "slot": len(seri),
        "mulai": seri[0]["waktu"] if seri else None,
        "selesai": seri[-1]["waktu"] if seri else None,
        "umur_slot_terakhir_jam": umur_terakhir,
        "usang": umur_terakhir is None or umur_terakhir > STALE_HOURS,
        "tanggal": raw.get("tanggal_24_rev") or [],
        "satuan": "indeks ISPU per polutan (bukan µg/m³)",
        "seri": seri,
        "cakupan": cakupan,
        "hilang": hilang,
        "celah": celah,
        "duplikat": duplikat,
        "mencurigakan": mencurigakan,
        "catatan": catatan,
    }


def build_station_payload(raw: dict[str, Any], *, now: dt.datetime | None = None,
                          history: bool = True) -> dict[str, Any]:
    """Detail stasiun lengkap: nilai terkini, rata-rata, riwayat, dan peringatan."""
    out = normalize_station(raw, now=now)
    if history:
        out["riwayat_24jam"] = normalize_history(raw, now=now)
    return out
