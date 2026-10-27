"""Uji normalisasi + inti ISPUNet dengan data mentah yang direkam dari API live.

Fixture di `tests/fixtures/` adalah respons asli (dipotong) dari
ispu.kemenlh.go.id/apimob/v1 pada 27-Okt-2026 untuk kasus yang dilaporkan:
Palangka Raya (stasiun mati, timestamp duplikat, nilai mustahil), Sampit/KTM
(PM10 bolong di tengah), Banjar Baru + Perawang (data basi), Banjarmasin
(kota tanpa ID stasiun).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from ispunet import normalize as N

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 10, 27, 13, 10, tzinfo=dt.timezone.utc)  # 20:10 WIB

def load(name: str):
    return json.loads((FIXTURES / name).read_text())

@pytest.fixture(scope="module")
def palangka() -> dict:
    return load("palangka_raya_detail.json")

@pytest.fixture(scope="module")
def ktm() -> dict:
    return load("kotawaringin_timur_detail.json")

# ------------------------------------------------------------------ waktu
def test_parse_both_upstream_time_formats():
    a = N.parse_time("2026-10-27 20:00:00", 7)
    b = N.parse_time("27-Oktober-2026 20:00:00", 7)
    assert a == b == dt.datetime(2026, 10, 27, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=7)))

def test_parse_time_rejects_garbage():
    assert N.parse_time(None) is None
    assert N.parse_time("-") is None
    assert N.parse_time("27-Foo-2026 20:00:00") is None

def test_tz_offset_prefers_time_z_then_province():
    assert N.tz_offset("WITA", "Kalimantan Selatan") == 8
    assert N.tz_offset(None, "Kalimantan Selatan") == 8   # getData/lat/lng tanpa time_z
    assert N.tz_offset(None, "Papua") == 9
    assert N.tz_offset(None, "DKI Jakarta") == 7
    assert N.tz_offset(None, None) == 7

def test_age_hours_clamps_future_station_clock():
    moment = dt.datetime(2026, 10, 27, 14, 0, tzinfo=dt.timezone.utc)
    assert N.age_hours(moment, NOW) == 0.0

# --------------------------------------------------------------- angka
@pytest.mark.parametrize("raw,expected", [
    ("69.88", 69.88), (12, 12.0), ("", None), ("-", None), (None, None), ("N/A", None),
])
def test_to_number(raw, expected):
    assert N.to_number(raw) == expected

def test_pollutant_keys_handles_html_and_multi_param():
    assert N.pollutant_keys("PM<sub>2.5</sub>") == ["pm25"]
    assert N.pollutant_keys("PM<sub>2.5</sub>,O<sub>3</sub>") == ["pm25", "o3"]
    assert N.pollutant_keys("-") == []

def test_suspect_reason_index_vs_concentration():
    assert N.suspect_reason("pm25", 1252, kind="indeks") is not None      # > ISPU 500
    assert N.suspect_reason("pm25", 337, kind="indeks") is None
    assert N.suspect_reason("pm25", 337, kind="konsentrasi") is None      # µg/m³ wajar
    assert N.suspect_reason("pm25", 553.84, kind="konsentrasi") is not None
    assert N.suspect_reason("co", 1498.8, kind="konsentrasi") is None     # batas CO 45000
    assert N.suspect_reason("pm10", -1, kind="indeks") is not None

def test_recommendation_fallback_for_dead_station():
    assert N.recommendation(None) == "TIDAK VALID / stasiun offline"
    assert N.recommendation(3).startswith("Penderita asma")
    assert N.recommendation(99) == "Kategori tidak dikenal."

# ------------------------------------------------------------- stasiun
def test_dead_station_is_offline_with_offline_recommendation(palangka):
    s = N.normalize_station(palangka, now=NOW)
    assert s["status"] == "offline"
    assert s["ispu"] is None
    assert s["rekomendasi"] == "TIDAK VALID / stasiun offline"
    assert any("tidak melaporkan nilai ISPU" in w for w in s["peringatan"])
    # konsentrasi rata-rata tetap tersedia (bukan nol) meski ISPU tidak ada
    assert s["konsentrasi_rata_rata"]["pm25"] == 390.07

def test_station_exposes_averages_and_categories(ktm):
    s = N.normalize_station(ktm, now=NOW)
    assert s["ispu"] == 371
    assert s["indeks"]["pm25"] == 371
    assert s["konsentrasi_rata_rata"]["pm25"] == 338.48
    assert s["kategori_angka"]["pm25"] == 5
    assert s["indeks_maks_24jam"]["pm25"] == 443

def test_station_without_per_pollutant_indices_omits_null_dicts():
    raw = {
        "id_stasiun": "X", "waktu": "2026-10-27 20:00:00", "time_z": "WIB",
        "val": "96", "param": "PM<sub>2.5</sub>", "a_pm25": "52.6", "c_pm25": "2",
        "kategori": {"nilai_uid": 2, "nilai": "SEDANG"},
    }
    s = N.normalize_station(raw, now=NOW)
    assert s["indeks"] is None            # getStations tidak mengirim field ini
    assert s["konsentrasi_rata_rata"]["pm25"] == 52.6
    assert s["status"] == "aktif"

def test_impossible_values_are_flagged_not_dropped(palangka):
    s = N.normalize_station(palangka, now=NOW)
    fields = {m["field"] for m in s["mencurigakan"]}
    assert "indeks_maks_24jam.pm25" in fields      # 1252
    assert "indeks_maks_24jam.pm10" in fields      # 4091
    assert s["indeks_maks_24jam"]["pm25"] == 1252  # nilai dipertahankan

def test_stale_station_marked_usang():
    raw = {
        "id_stasiun": "PERAWANG", "waktu": "18-Desember-2024 10:00:00", "time_z": "WIB",
        "val": "52", "param": "O<sub>3</sub>", "kategori": {"nilai_uid": 2},
    }
    s = N.normalize_station(raw, now=NOW)
    assert s["usang"] is True
    assert s["umur_data_jam"] > 24 * 365
    assert any("bukan kondisi terkini" in w for w in s["peringatan"])

def test_fresh_station_not_stale(ktm):
    s = N.normalize_station(ktm, now=NOW)
    assert s["usang"] is False
    assert s["umur_data_jam"] <= N.STALE_HOURS

# -------------------------------------------------------------- riwayat
def test_history_uses_full_timestamps_and_dedupes(palangka):
    h = N.normalize_history(palangka, now=NOW)
    # waktu_24_rev hanya jam (08:00 dua kali) — timestamp dari waktu_24 harus dipakai
    assert h["duplikat"] == []
    stamps = [slot["waktu"] for slot in h["seri"]]
    assert len(stamps) == len(set(stamps))
    assert stamps[0] == "2026-10-26T07:00:00+07:00"
    assert stamps[-1] == "2026-10-27T20:00:00+07:00"

def test_history_reports_gap_between_days(palangka):
    h = N.normalize_history(palangka, now=NOW)
    assert h["celah"], "harus ada celah 17:00 -> 08:00"
    assert h["celah"][0]["jam"] == 15.0
    assert any("celah" in c for c in h["catatan"])

def test_history_coverage_flags_holes_in_middle(ktm):
    h = N.normalize_history(ktm, now=NOW)
    pm10 = h["cakupan"]["pm10"]
    assert pm10["ada"] == 7 and pm10["slot"] == 24
    assert h["hilang"]["pm10"], "PM10 bolong 04:00-16:00 harus dilaporkan"
    assert h["cakupan"]["pm25"]["persen"] == 100

def test_history_values_are_indices_not_concentrations(palangka):
    h = N.normalize_history(palangka, now=NOW)
    assert "indeks ISPU" in h["satuan"]
    assert h["seri"][0]["pm25"] == 1252.0
    assert h["mencurigakan"], "nilai >500 pada seri harus ditandai"

def test_history_falls_back_to_rev_with_dates():
    raw = {
        "time_z": "WIB",
        "tanggal_24_rev": ["2026-10-26", "2026-10-27"],
        "waktu_24_rev": ["23:00:00", "00:00:00", "01:00:00"],
        "pm25_24_rev": [{"nilai": "10"}, {"nilai": "11"}, {"nilai": "12"}],
    }
    h = N.normalize_history(raw, now=NOW)
    assert [s["waktu"] for s in h["seri"]] == [
        "2026-10-26T23:00:00+07:00",
        "2026-10-27T00:00:00+07:00",
        "2026-10-27T01:00:00+07:00",
    ]
    assert any("tanggal_24_rev" in c for c in h["catatan"])

def test_history_marks_stale_series():
    raw = {
        "waktu": "18-Desember-2024 10:00:00", "time_z": "WIB",
        "waktu_24": ["2024-12-18 09:00:00", "2024-12-18 10:00:00"],
        "pm25_24_rev": [{"nilai": "48"}, {"nilai": "48"}],
    }
    h = N.normalize_history(raw, now=NOW)
    assert h["usang"] is True
    assert any("slot terakhir" in c for c in h["catatan"])

# --------------------------------------------------------------- pilihan
def test_pick_best_skips_offline_and_stale():
    rows = [
        {"id_stasiun": "DEAD", "status": "offline", "usang": False, "jarak_m": 4.0},
        {"id_stasiun": "OLD", "status": "aktif", "usang": True, "jarak_m": 5755.0},
        {"id_stasiun": "FRESH", "status": "aktif", "usang": False, "jarak_m": 103185.0},
    ]
    best, reason = N.pick_best(rows, -2.22, 113.86)
    assert best is not None and best["id_stasiun"] == "FRESH"
    assert "terbaru" in reason

def test_pick_best_reports_when_everything_is_stale():
    rows = [{"id_stasiun": "OLD", "status": "aktif", "usang": True, "jarak_m": 100.0}]
    best, reason = N.pick_best(rows)
    assert best is not None and best["id_stasiun"] == "OLD"
    assert "usang" in reason

def test_pick_best_returns_none_when_all_offline():
    rows = [{"id_stasiun": "DEAD", "status": "offline", "usang": False, "jarak_m": 1.0}]
    best, reason = N.pick_best(rows)
    assert best is None
    assert "offline" in reason

def test_sort_is_deterministic_so_limit_is_stable():
    rows = [
        {"id_stasiun": "B", "provinsi": "X", "kota": "k", "nama": "n", "ispu": 10},
        {"id_stasiun": "A", "provinsi": "X", "kota": "k", "nama": "n", "ispu": 90},
        {"id_stasiun": "C", "provinsi": "X", "kota": "k", "nama": "n", "ispu": None},
    ]
    shuffled = [rows[2], rows[0], rows[1]]
    assert N.sort_stations(rows) == N.sort_stations(shuffled)
    assert [r["id_stasiun"] for r in N.sort_stations(rows, "ispu")] == ["A", "B", "C"]

def test_search_matches_city_and_ignores_separators():
    rows = [
        {"id_stasiun": "KABUPATEN_KOTAWARINGINTIMUR", "nama": "Sampit", "kota": "Sampit",
         "provinsi": "Kalimantan Tengah"},
        {"id_stasiun": "DKI1", "nama": "DKI 1 Bundaran HI", "kota": "Jakarta",
         "provinsi": "DKI Jakarta"},
    ]
    assert [r["id_stasiun"] for r in N.search_stations(rows, "sampit")] == [
        "KABUPATEN_KOTAWARINGINTIMUR"
    ]
    assert [r["id_stasiun"] for r in N.search_stations(rows, "kota waringin")] == [
        "KABUPATEN_KOTAWARINGINTIMUR"
    ]
    assert N.search_stations(rows, "dki1")[0]["id_stasiun"] == "DKI1"

def test_suggest_returns_close_ids():
    rows = [{"id_stasiun": "DKI1", "nama": "DKI 1", "kota": "Jakarta"}]
    assert "DKI1" in N.suggest(rows, "DKI 1")
