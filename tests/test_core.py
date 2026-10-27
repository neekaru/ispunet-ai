"""Uji `IspuCore` (orkestrasi) dengan transport palsu — tanpa jaringan."""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from ispunet.core import IspuCore, IspuError, StationNotFound, resolve_city

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 10, 27, 13, 10, tzinfo=dt.timezone.utc)

def _load(name: str):
    return json.loads((FIXTURES / name).read_text())

NEARBY_PALANGKA = [
    # urutan upstream: jarak naik
    {"id_stasiun": "PALANGKARAYA", "nama": "Palangkaraya Jekan Raya",
     "kota": "Palangkaraya", "provinsi": "Kalimantan Tengah",
     "lat": "-2.2215", "lon": "113.86", "jarak": 4, "val": "-", "param": "-",
     "waktu": "27-Oktober-2026 20:00:00", "time_z": "WIB",
     "kategori": {"nilai_uid": None, "nilai": "-"}, "a_pm25": "390.07"},
    {"id_stasiun": "MOBILE_AQMS_BPBD_KALTENG", "nama": "Mobile AQMS",
     "kota": "Palangkaraya", "provinsi": "Kalimantan Tengah",
     "lat": "-2.1697", "lon": "113.861", "jarak": 5755, "val": "414",
     "param": "PM<sub>2.5</sub>", "waktu": "11-Oktober-2026 18:00:00",
     "time_z": "WIB", "kategori": {"nilai_uid": 5, "nilai": "BERBAHAYA"},
     "a_pm25": "392.7"},
    {"id_stasiun": "KABUPATEN_KAPUAS", "nama": "Kabupaten Kapuas",
     "kota": "Kabupaten Kapuas", "provinsi": "Kalimantan Tengah",
     "lat": "-3.0", "lon": "114.38", "jarak": 103185, "val": "370",
     "param": "PM<sub>2.5</sub>", "waktu": "27-Oktober-2026 20:00:00",
     "time_z": "WIB", "kategori": {"nilai_uid": 5, "nilai": "BERBAHAYA"},
     "a_pm25": "337.31"},
]

def make_core(*, stations=None, detail=None, nearby=None, fail: str | None = None):
    """Transport palsu: `detail`/`nearby` berupa dict id→baris mentah."""
    def fetch(action: str) -> dict:
        if fail and action.startswith(fail):
            raise IspuError(f"API {action}: rate limit upstream (Too Many Attempts)")
        if action.startswith("getStations"):
            return {"rows": stations if stations is not None else _load("stations_subset.json")}
        if action.startswith("getDetail/stasiun/"):
            sid = action.rsplit("/", 1)[-1]
            rows = (detail or {}).get(sid, [])
            return {"rows": rows}
        if action.startswith("getData/lat/"):
            return {"rows": nearby if nearby is not None else NEARBY_PALANGKA}
        if action.startswith("statusispu"):
            return {"rows": [{"nilai_uid": 1, "nilai": "BAIK", "batas_teks": "0-50"}]}
        raise AssertionError(f"action tak terduga: {action}")

    return IspuCore(fetch)

def test_resolve_city_accepts_prefixes_and_case():
    assert resolve_city("Palangka Raya") == resolve_city("kota palangka raya")
    assert resolve_city("KABUPATEN_KATINGAN") == (-2.0667, 113.4)
    assert resolve_city("Atlantis") is None

def test_current_prefers_fresh_station_over_offline_nearest():
    out = make_core().current(kota="Palangka Raya", now=NOW)
    assert out["primary"]["id_stasiun"] == "KABUPATEN_KAPUAS"
    assert out["primary"]["usang"] is False
    assert any("PALANGKARAYA" in c and "offline" in c for c in out["catatan"])
    assert any("MOBILE_AQMS" not in c for c in out["catatan"])

def test_current_marks_all_stale_neighbourhood():
    nearby = [row for row in NEARBY_PALANGKA if row["id_stasiun"] != "KABUPATEN_KAPUAS"]
    out = make_core(nearby=nearby).current(-2.22, 113.86, now=NOW)
    assert out["primary"]["usang"] is True
    assert any("semua stasiun" in c for c in out["catatan"])

def test_current_errors_when_every_station_offline():
    nearby = [NEARBY_PALANGKA[0]]
    out = make_core(nearby=nearby).current(-2.22, 113.86, now=NOW)
    assert out["primary"] is None
    assert "offline" in out["alasan_pemilihan"]

def test_current_requires_coordinates_or_known_city():
    with pytest.raises(IspuError, match="lat/lon"):
        make_core().current()
    with pytest.raises(IspuError, match="tidak ada di tabel"):
        make_core().current(kota="Atlantis")

def test_station_not_found_suggests_replacements_for_city():
    core = make_core()
    with pytest.raises(StationNotFound) as excinfo:
        core.station_detail("BANJARMASIN", now=NOW)
    err = excinfo.value
    assert err.pengganti, "kota tanpa ID harus menawarkan stasiun pengganti"
    assert all(r["status"] == "aktif" for r in err.pengganti)
    assert all(not r["usang"] for r in err.pengganti)
    assert "114.5944" in str(err)

def test_station_not_found_suggests_similar_id():
    core = make_core()
    with pytest.raises(StationNotFound) as excinfo:
        core.station_detail("DKI", now=NOW)
    assert "DKI1" in excinfo.value.saran

def test_station_offline_attaches_replacements():
    detail = {"PALANGKARAYA": [_load("palangka_raya_detail.json")]}
    out = make_core(detail=detail).station_detail("PALANGKARAYA", history=False, now=NOW)
    assert out["status"] == "offline"
    assert out["rekomendasi"] == "TIDAK VALID / stasiun offline"
    assert out["pengganti"][0]["id_stasiun"] == "KABUPATEN_KAPUAS"

def test_station_history_can_be_skipped():
    detail = {"KABUPATEN_KOTAWARINGINTIMUR": [_load("kotawaringin_timur_detail.json")]}
    core = make_core(detail=detail)
    assert "riwayat_24jam" not in core.station_detail(
        "KABUPATEN_KOTAWARINGINTIMUR", history=False, now=NOW
    )
    assert core.station_detail("KABUPATEN_KOTAWARINGINTIMUR", now=NOW)["riwayat_24jam"]["slot"] == 24

def test_stations_limit_does_not_change_prefix_order():
    core = make_core()
    full = [r["id_stasiun"] for r in core.stations(now=NOW)]
    small = [r["id_stasiun"] for r in core.stations(limit=3, now=NOW)]
    assert small == full[:3]

def test_stations_search_and_filters():
    core = make_core()
    assert [r["id_stasiun"] for r in core.stations(q="banjar", now=NOW)] == [
        "KABUPATEN_BANJAR"
    ]
    assert all(
        r["provinsi"] == "DKI Jakarta" for r in core.stations(provinsi="dki", now=NOW)
    )
    assert core.stations(hanya_aktif=True, now=NOW), "semua fixture aktif"

def test_compare_handles_ids_cities_and_unknown_targets():
    core = make_core()
    out = core.compare(["DKI1", "Palangka Raya", "Atlantis"], now=NOW)
    ids = [r["id_stasiun"] for r in out["perbandingan"]]
    assert "DKI1" in ids
    assert "KABUPATEN_KAPUAS" in ids          # lewat koordinat kota + stasiun segar
    assert out["tidak_ditemukan"][0]["target"] == "Atlantis"

def test_compare_never_duplicates_station():
    core = make_core()
    out = core.compare(["KABUPATEN_BANJAR", "banjar"], now=NOW)
    ids = [r["id_stasiun"] for r in out["perbandingan"]]
    assert ids.count("KABUPATEN_BANJAR") == 1

def test_transport_failure_is_not_reported_as_missing_station():
    with pytest.raises(IspuError, match="rate limit"):
        make_core(fail="getDetail/").station_detail("DKI1", now=NOW)
    with pytest.raises(IspuError, match="rate limit"):
        make_core(fail="getStations").stations(now=NOW)

def test_categories_shape():
    rows = make_core().categories()
    assert rows[0]["uid"] == 1 and rows[0]["batas"] == "0-50"
