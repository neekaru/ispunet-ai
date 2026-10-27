"""Inti ISPUNet — stdlib murni, tanpa transport HTTP.

`IspuCore` menerima fungsi `fetch(action) -> dict` (respons JSON mentah upstream)
sehingga paket (`client.py` via httpx), plugin Hermes, dan skrip skill (via
urllib) memakai LOGIKA YANG SAMA: pemilihan stasiun, pengganti, banding, dan
normalisasi data.

File ini di-vendor verbatim ke `hermes-plugin/ispunet/core.py` dan
`skills/ispunet/scripts/core.py`; `tests/test_vendor_sync.py` menjaga ketiganya
identik.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover - hanya untuk type checker
    from . import normalize as N
else:
    def _load_normalize():
        """Impor `normalize` baik sebagai paket maupun sebagai modul datar.

        Salinan file ini dipakai plugin Hermes (paket) dan skrip skill (modul
        datar), jadi jalur impor harus tahan dua konteks tanpa mengubah isi file.
        """
        try:
            from . import normalize as module  # type: ignore[import-not-found]
            return module
        except ImportError:
            import importlib.util
            import pathlib
            import sys

            name = "_ispunet_normalize"
            if name in sys.modules:
                return sys.modules[name]
            path = pathlib.Path(__file__).with_name("normalize.py")
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:  # pragma: no cover
                raise ImportError(f"normalize.py tidak ditemukan di {path}") from None
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

    N = _load_normalize()

class IspuError(Exception):
    """Kegagalan akses API ISPUNet (transport atau status != 200)."""

class StationNotFound(IspuError):
    """ID stasiun tidak ada di upstream; membawa saran pengganti."""

    def __init__(
        self,
        message: str,
        *,
        saran: list[str],
        pengganti: list[dict[str, Any]],
        mirip: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.saran = saran
        self.pengganti = pengganti
        self.mirip = mirip

# --------------------------------------------------------------------- kota
# Titik pusat kota (perkiraan) untuk kota yang TIDAK punya entri di getStations
# atau namanya berbeda dari id stasiun. Dipakai hanya untuk mencari stasiun
# terdekat lewat getData/lat/lng — bukan sumber data kualitas udara.
CITY_COORDS: dict[str, tuple[float, float]] = {
    "banda aceh": (5.5483, 95.3238),
    "medan": (3.5952, 98.6722),
    "padang": (-0.9471, 100.4172),
    "pekanbaru": (0.5071, 101.4478),
    "jambi": (-1.6101, 103.6131),
    "palembang": (-2.9761, 104.7754),
    "bengkulu": (-3.7928, 102.2608),
    "bandar lampung": (-5.3971, 105.2668),
    "pangkalpinang": (-2.1316, 106.1169),
    "batam": (1.0456, 104.0305),
    "jakarta": (-6.2088, 106.8456),
    "bandung": (-6.9175, 107.6191),
    "semarang": (-6.9932, 110.4203),
    "yogyakarta": (-7.7956, 110.3695),
    "solo": (-7.5755, 110.8243),
    "surabaya": (-7.2575, 112.7521),
    "malang": (-7.9666, 112.6326),
    "denpasar": (-8.6705, 115.2126),
    "mataram": (-8.5833, 116.1167),
    "kupang": (-10.1772, 123.6070),
    "pontianak": (-0.0263, 109.3425),
    "palangka raya": (-2.2215, 113.8600),
    "palangkaraya": (-2.2215, 113.8600),
    "banjarmasin": (-3.3186, 114.5944),
    "banjarbaru": (-3.4572, 114.8103),
    "samarinda": (-0.5022, 117.1536),
    "balikpapan": (-1.2379, 116.8529),
    "bontang": (0.1247, 117.4925),
    "tarakan": (3.3273, 117.5759),
    "tanjung selor": (2.8375, 117.3667),
    "manado": (1.4748, 124.8421),
    "palu": (-0.8917, 119.8707),
    "makassar": (-5.1477, 119.4327),
    "kendari": (-3.9985, 122.5128),
    "gorontalo": (0.5435, 123.0568),
    "ambon": (-3.6954, 128.1814),
    "ternate": (0.7900, 127.3840),
    "jayapura": (-2.5916, 140.6690),
    "manokwari": (-0.8615, 134.0620),
    "sampit": (-2.5333, 112.9500),
    "katingan": (-2.0667, 113.4000),
    "kasongan": (-1.8833, 113.3833),
    "kuala kapuas": (-3.0000, 114.3833),
    "muara teweh": (-0.9500, 114.8833),
    "puruk cahu": (-0.6333, 114.5667),
    "buntok": (-1.7333, 114.8333),
    "tamiang layang": (-2.1167, 115.1667),
}

def resolve_city(name: str) -> tuple[float, float] | None:
    """Koordinat kota dari tabel bawaan (case/spasi/tanda hubung longgar)."""
    key = " ".join(str(name or "").lower().replace("-", " ").replace("_", " ").split())
    if not key:
        return None
    if key in CITY_COORDS:
        return CITY_COORDS[key]
    for prefix in ("kota ", "kabupaten ", "kab. ", "kab "):
        if key.startswith(prefix):
            stripped = key[len(prefix):].strip()
            if stripped in CITY_COORDS:
                return CITY_COORDS[stripped]
    return None

def rank_replacements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calon pengganti: hanya stasiun aktif yang datanya segar, terdekat dulu.

    Stasiun aktif tapi usang sengaja TIDAK ditawarkan sebagai pengganti — kalau
    semua yang ada usang, lebih baik pengguna tahu tidak ada data terkini
    daripada disodori angka berumur berhari-hari.
    """
    segar = [r for r in rows if r.get("status") == "aktif" and not r.get("usang")]
    return sorted(
        segar,
        key=lambda r: float(r["jarak_m"]) if r.get("jarak_m") is not None else float("inf"),
    )

def recommendation(uid: Any) -> str:
    """Rekomendasi kesehatan untuk nilai_uid kategori (1..5)."""
    return N.recommendation(uid)

def nearest(rows: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    """Stasiun terdekat dari baris `current()["nearby"]` (sudah terurut jarak)."""
    return N.nearest(rows, lat, lon)

# --------------------------------------------------------------------- inti
class IspuCore:
    """Orkestrasi endpoint ISPUNet di atas satu fungsi transport `fetch`."""

    def __init__(self, fetch: Callable[[str], dict[str, Any]]) -> None:
        self._fetch = fetch

    # -------------------------------------------------------------- raw
    def stations_raw(self) -> list[dict[str, Any]]:
        """Baris mentah `getStations` (107 stasiun; TIDAK memuat semua stasiun aktif)."""
        return self._fetch("getStations").get("rows") or []

    def detail_raw(self, station_id: str) -> list[dict[str, Any]]:
        """Baris mentah `getDetail/stasiun/<id>`; endpoint ini menolak query tambahan."""
        return self._fetch(f"getDetail/stasiun/{station_id}").get("rows") or []

    def nearby_raw(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Baris mentah `getData/lat/<lat>/lng/<lon>` (terurut jarak dari upstream)."""
        return self._fetch(f"getData/lat/{lat}/lng/{lon}").get("rows") or []

    def categories(self) -> list[dict[str, Any]]:
        """Definisi 5 kategori ISPU: BAIK .. BERBAHAYA, batas, warna."""
        rows = self._fetch("statusispu").get("rows") or []
        return [
            {
                "uid": r.get("nilai_uid"),
                "kategori": r.get("nilai"),
                "batas": r.get("batas_teks"),
                "batas_bawah": r.get("batas_bawah"),
                "batas_atas": r.get("batas_atas"),
                "warna": r.get("color_text"),
                "warna_hex": r.get("color"),
                "keterangan": r.get("keterangan"),
            }
            for r in rows
        ]

    # ------------------------------------------------------- normalized
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

        `q` mencari id/nama/kota/provinsi; urutan (`order`) diterapkan SEBELUM
        `limit` dipotong, jadi subset selalu sama untuk limit berbeda.
        """
        rows = [N.normalize_station(r, now=now) for r in self.stations_raw()]
        rows = N.filter_stations(
            rows, query=q, provinsi=provinsi, kota=kota, hanya_aktif=hanya_aktif
        )
        rows = N.sort_stations(rows, order)
        if limit and limit > 0:
            rows = rows[:limit]
        return rows

    def station_detail(
        self, station_id: str, *, history: bool = True, now: dt.datetime | None = None
    ) -> dict[str, Any]:
        """Detail satu stasiun + riwayat 24 jam bersih + pengganti bila stasiun mati."""
        key = str(station_id or "").strip()
        if not key:
            raise StationNotFound("station_id kosong", saran=[], pengganti=[], mirip=[])

        rows = self.detail_raw(key)
        if not rows:
            return self._not_found(key, now=now)

        out = N.build_station_payload(rows[0], now=now, history=history)
        out["sumber"] = "getDetail/stasiun"
        if out["status"] != "aktif":
            out["pengganti"] = self._replacements(out, now=now)
            out["saran"] = (
                "stasiun ini tidak melaporkan ISPU; nilai konsentrasi/rata-rata di atas "
                "adalah data mentah terakhir, bukan ISPU terkini"
            )
        return out

    def current(
        self, lat: float | None = None, lon: float | None = None, *,
        kota: str | None = None, now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        """Udara di sekitar koordinat (atau nama kota) + stasiun sekitar + catatan.

        Peringkat: stasiun aktif yang datanya segar dulu, baru jarak. Stasiun
        offline tidak pernah dipilih sebagai `primary`.
        """
        if kota and (lat is None or lon is None):
            coords = resolve_city(kota)
            if coords is None:
                raise IspuError(
                    f"kota {kota!r} tidak ada di tabel koordinat bawaan; "
                    "kirim lat/lon eksplisit"
                )
            lat, lon = coords
        if lat is None or lon is None:
            raise IspuError("current() butuh lat/lon atau nama kota yang dikenal")

        raw_rows = self.nearby_raw(lat, lon)
        if not raw_rows:
            raise IspuError(f"tidak ada stasiun pemantauan di sekitar ({lat}, {lon})")

        rows = [N.normalize_station(r, now=now) for r in raw_rows]
        rows.sort(key=lambda r: (r["jarak_m"] if r["jarak_m"] is not None else float("inf")))
        primary, alasan = N.pick_best(rows, lat, lon)

        catatan: list[str] = []
        terdekat = rows[0]
        if primary is None:
            catatan.append(alasan)
        else:
            if terdekat["id_stasiun"] != primary["id_stasiun"]:
                if terdekat["status"] != "aktif":
                    catatan.append(
                        f"stasiun terdekat {terdekat['id_stasiun']} sedang offline; "
                        f"dipakai {primary['id_stasiun']} ({primary['jarak_m']} m)"
                    )
                elif terdekat["usang"]:
                    catatan.append(
                        f"stasiun terdekat {terdekat['id_stasiun']} datanya "
                        f"{terdekat['umur_data_jam']} jam; dipakai yang lebih segar "
                        f"{primary['id_stasiun']} ({primary['jarak_m']} m)"
                    )
            if primary["usang"]:
                catatan.append(
                    f"PERINGATAN: semua stasiun di sekitar memakai data usang "
                    f"(terbaru {primary['umur_data_jam']} jam lalu)"
                )

        return {
            "titik": {"lat": lat, "lon": lon},
            "primary": primary,
            "alasan_pemilihan": alasan,
            "nearby": rows,
            "jumlah_stasiun_sekitar": len(rows) - 1,
            "catatan": catatan,
        }

    def compare(
        self, targets: list[str], *, now: dt.datetime | None = None
    ) -> dict[str, Any]:
        """Bandingkan beberapa stasiun/kota sekaligus.

        Tiap target boleh: ID stasiun (`DKI1`), nama kota/provinsi yang ada di
        `getStations` (`Jakarta`, `Kalimantan Selatan`), atau nama kota di tabel
        koordinat bawaan (`Banjarmasin`, `Pekanbaru`, `Samarinda`, `Palangka Raya`).
        """
        rows = [N.normalize_station(r, now=now) for r in self.stations_raw()]
        hasil: list[dict[str, Any]] = []
        tidak_ditemukan: list[dict[str, Any]] = []
        dipakai: set[str] = set()

        for target in targets:
            text = str(target or "").strip()
            if not text:
                continue
            exact = [r for r in rows if str(r.get("id_stasiun") or "").lower() == text.lower()]
            match = exact or N.search_stations(rows, text)
            if match:
                for row in N.sort_stations(match)[:3]:
                    sid = row.get("id_stasiun")
                    if not sid or sid in dipakai:
                        continue
                    dipakai.add(sid)
                    hasil.append({**row, "dicari_dengan": text})
                continue

            coords = resolve_city(text)
            if coords is not None:
                around = self.current(coords[0], coords[1], now=now)
                primary = around["primary"]
                if primary is None:
                    tidak_ditemukan.append({
                        "target": text,
                        "alasan": around["alasan_pemilihan"],
                        "saran": "tidak ada stasiun aktif di sekitar kota ini",
                    })
                    continue
                if primary["id_stasiun"] not in dipakai:
                    dipakai.add(primary["id_stasiun"])
                    hasil.append({
                        **primary,
                        "dicari_dengan": text,
                        "sumber": "getData/lat/lng (kota tidak ada di getStations)",
                        "catatan_pemilihan": around["catatan"],
                    })
                continue

            tidak_ditemukan.append({
                "target": text,
                "alasan": "tidak ada stasiun/kota dengan nama itu",
                "mirip": N.suggest(rows, text),
                "saran": "kirim id_stasiun dari mode stations, atau lat/lon eksplisit",
            })

        hasil = N.sort_stations(hasil)
        return {
            "jumlah": len(hasil),
            "perbandingan": hasil,
            "tidak_ditemukan": tidak_ditemukan,
            "catatan": (
                "stasiun bertanda usang=true tidak boleh disajikan sebagai kondisi terkini"
                if any(r.get("usang") for r in hasil)
                else []
            ),
        }

    # ---------------------------------------------------------- internal
    def _not_found(self, key: str, *, now: dt.datetime | None) -> dict[str, Any]:
        rows = [N.normalize_station(r, now=now) for r in self.stations_raw()]
        mirip_ids = N.suggest(rows, key)
        mirip = [r for r in rows if r.get("id_stasiun") in mirip_ids]

        # Nama kota yang dikenal tapi tidak punya ID stasiun (mis. Banjarmasin).
        coords = resolve_city(key)
        if coords is not None:
            around = self.current(coords[0], coords[1], now=now)
            pengganti = rank_replacements(around["nearby"])[:4]
            raise StationNotFound(
                f"stasiun {key!r} tidak ada di getDetail; kota ini tidak punya stasiun "
                f"dengan ID tersebut — pakai mode current ({coords[0]}, {coords[1]})",
                saran=[r["id_stasiun"] for r in pengganti],
                pengganti=pengganti,
                mirip=mirip,
            )

        raise StationNotFound(
            f"stasiun {key!r} tidak ditemukan"
            + (f"; maksud Anda: {', '.join(mirip_ids)}?" if mirip_ids else ""),
            saran=mirip_ids,
            pengganti=[],
            mirip=mirip,
        )

    def _replacements(self, station: dict[str, Any], *,
                      now: dt.datetime | None) -> list[dict[str, Any]]:
        lat, lon = station.get("lat"), station.get("lon")
        if lat is None or lon is None:
            return []
        try:
            around = self.current(lat, lon, now=now)
        except IspuError:
            return []
        lain = [r for r in around["nearby"] if r["id_stasiun"] != station["id_stasiun"]]
        return rank_replacements(lain)[:4]
