# ispunet-py

Kualitas udara Indonesia (**ISPU** — Indeks Standar Pencemar Udara, resmi **KLHK**)
sebagai library Python, REST API, CLI, dan skill/plugin untuk **OpenClaw** & **Hermes**.

Dibangun ulang dari APK resmi `id.go.menlhk.iku.app` v1.5.5 (Ionic/Cordova):
endpoint, header, dan rekomendasi kesehatan diambil persis dari
`src/app/services/api.service.ts` hasil dekompilasi.

```
ispunet-py/
├── ispunet/            # package: transport, core, normalize, server, CLI
│   ├── normalize.py    # SUMBER TUNGGAL normalisasi data (stdlib murni)
│   ├── core.py         # orkestrasi (pemilihan stasiun, pengganti, banding)
│   ├── client.py       # IspuClient — transport httpx + retry/rate-limit
│   ├── constants.py    # endpoint, kredensial publik (re-export dari normalize)
│   ├── server.py       # REST API FastAPI
│   └── cli.py          # CLI
├── skills/ispunet/     # skill standalone (SKILL.md + skrip stdlib + salinan core/normalize)
├── hermes-plugin/ispunet/  # plugin Hermes: tool `ispu` + skill + salinan core/normalize
├── tests/              # uji normalize/core + fixture respons API asli
├── openclaw.plugin.json    # manifest plugin OpenClaw
└── pyproject.toml
```

`normalize.py` dan `core.py` disalin verbatim ke plugin dan skill (keduanya harus
standalone tanpa paket `ispunet`). `tests/test_vendor_sync.py` gagal bila salinan
menyimpang — setelah mengubah salah satunya, jalankan:

```bash
cp ispunet/normalize.py hermes-plugin/ispunet/normalize.py
cp ispunet/core.py      hermes-plugin/ispunet/core.py
cp ispunet/normalize.py skills/ispunet/scripts/normalize.py
cp ispunet/core.py      skills/ispunet/scripts/core.py
```

## Install

```bash
pip install -e .        # atau: uv pip install -e .
```

Butuh Python ≥ 3.10. Runtime: httpx, fastapi, uvicorn.
Skill (`skills/ispunet/scripts/`) **tanpa dependensi** — hanya stdlib. Skrip
`ispunet.py` memakai `core.py` + `normalize.py` di folder yang sama (salinan
verbatim dari paket).

## CLI

```bash
ispunet current -6.194790 106.822998          # udara di sekitar koordinat
ispunet current --kota "Palangka Raya"        # kota tanpa ID stasiun (mis. Banjarmasin)
ispunet station DKI1                          # detail + riwayat 24 jam stasiun
ispunet station BANJARMASIN                   # 404 + daftar stasiun pengganti
ispunet stations --limit 20                   # 20 pertama, urutan deterministik
ispunet stations --q kalimantan --order ispu  # cari + urut ISPU tertinggi
ispunet search samarinda                      # cari by id/nama/kota/provinsi
ispunet compare Banjarmasin Pekanbaru Samarinda   # banding beberapa kota
ispunet categories                            # definisi 5 kategori ISPU
ispunet serve --port 8000                     # jalankan REST API
```

Semua perintah menerima `--json` untuk output JSON.

## REST API

`ispunet serve` lalu:

| Endpoint | Deskripsi |
|---|---|
| `GET /current?lat=&lon=` | Udara terkini di koordinat; `primary` = stasiun aktif tersegar |
| `GET /current?kota=` | Sama, untuk kota yang tidak punya ID stasiun (`Banjarmasin`, `Palangka Raya`) |
| `GET /stations?q=&provinsi=&kota=&hanya_aktif=&order=&limit=` | Cari/filter/urut stasiun; `total` dihitung sebelum `limit` |
| `GET /stations/{id}` | Detail + riwayat 24 jam bersih; 404 menyertakan `pengganti` |
| `GET /compare?targets=DKI1,Banjarmasin` | Banding beberapa stasiun/kota sekaligus |
| `GET /categories` | 5 kategori ISPU (BAIK … BERBAHAYA) |
| `GET /docs` | Swagger UI |

Contoh:

```bash
curl 'http://127.0.0.1:8000/current?lat=-6.2&lon=106.816'
curl 'http://127.0.0.1:8000/current?kota=Palangka%20Raya'
curl 'http://127.0.0.1:8000/compare?targets=Banjarmasin,Pekanbaru,Samarinda'
```

### Arti field

| Field | Arti |
|---|---|
| `ispu` | indeks ISPU stasiun (polutan kritis), sama dengan `val` upstream |
| `kategori` / `cat` | pita kategori dari upstream (BAIK … BERBAHAYA) |
| `param` | polutan kritis, mis. `PM2.5` |
| `indeks` | indeks ISPU **per polutan** (`pm25`, `pm10`, `so2`, `co`, `o3`, `no2`, `hc`) |
| `indeks_maks_24jam` | indeks maksimum 24 jam per polutan |
| `konsentrasi_rata_rata` | konsentrasi rata-rata 24 jam, **µg/m³** (field `a_*` upstream) |
| `kategori_angka` | nomor kategori (1..5) per polutan (`c_*` upstream) |
| `umur_data_jam`, `usang` | kesegaran data; `usang` = lebih tua dari 3 jam |
| `status` | `aktif` (melaporkan ISPU) atau `offline` |
| `mencurigakan` | nilai di luar batas wajar (indeks >500 / konsentrasi di luar tabel) |
| `peringatan` | ringkasan masalah data siap tampil |
| `rekomendasi` | saran kesehatan; `TIDAK VALID / stasiun offline` bila ISPU tidak ada |
| `pengganti` | stasiun aktif & segar terdekat (saat stasiun mati / tidak ditemukan) |

## Library

```python
from ispunet import IspuClient, StationNotFound, recommendation

c = IspuClient()
out = c.current(kota="Palangka Raya")
out["primary"]["id_stasiun"]           # stasiun aktif tersegar (offline dilewati)
out["primary"]["usang"]                # True = data >3 jam, jangan klaim real-time
out["catatan"]                         # kenapa stasiun itu yang dipilih

detail = c.station_detail("DKI1")      # detail + riwayat 24 jam bersih
detail["riwayat_24jam"]["cakupan"]     # kelengkapan per polutan
detail["konsentrasi_rata_rata"]        # µg/m³ rata-rata 24 jam
detail["indeks"]                       # ISPU per polutan
recommendation(3)                      # saran kesehatan utk kategori tsb

c.compare(["Banjarmasin", "Pekanbaru", "Samarinda"])["perbandingan"]
c.stations(q="banjar", order="ispu", limit=5)
c.current(-6.2, 106.816)["primary"]["kategori"]["nilai"]

try:
    c.station_detail("BANJARMASIN")
except StationNotFound as exc:
    exc.pengganti                      # stasiun aktif & segar di sekitar kota
    exc.saran                          # ID stasiun mirip
```

## Skill vs Plugin — mana yang dipakai

| | Skill | Plugin |
|---|---|---|
| Bentuk | `SKILL.md` + skrip (instruksi utk agent) | manifest + kode Python (tool terdaftar di runtime) |
| Kapan dipakai | Agent cuma perlu tahu *cara* query data via terminal | Butuh *tool* first-class: schema parameter, langsung dipanggil LLM tanpa shell |
| Keandalan | Tergantung agent mengeksekusi perintah dengan benar | Deterministik — handler dieksekusi langsung, error selalu JSON |
| Setup | Copy folder, tanpa install | `hermes plugins enable` / install plugin OpenClaw |

**Rekomendasi:** pakai **skill** untuk agen pemakai (OpenClaw/Hermes) yang
sudah punya terminal — lebih ringan dan portable. Pakai **plugin** bila mau
tool `ispu` muncul sebagai fungsi native (dipanggil LLM langsung dengan
schema parameter, tanpa lewat shell).

## OpenClaw

- **Skill**: `skills/ispunet/` — format ClawHub (`SKILL.md` frontmatter
  `metadata.openclaw` + skrip stdlib). Salin folder ke skills dir OpenClaw,
  atau publish via CLI ClawHub.
- **Plugin**: `openclaw.plugin.json` di root repo — manifest native OpenClaw
  (`id` + `configSchema` wajib, skill dir dideklarasikan di `skills`).
  Install sebagai plugin, skill ispunet ikut termuat.

## Hermes

- **Skill standalone**: `SKILL.md` di `skills/ispunet/` memakai frontmatter
  `metadata.hermes`. Salin ke `~/.hermes/skills/environment/ispunet/`.
  Tanpa env wajib (kredensial default publik) — tidak memicu `setup_needed`.
- **Plugin native**: `hermes-plugin/ispunet/` — `plugin.yaml` +
  `register(ctx)` mendaftarkan **tool `ispu`** (mode `current`/`station`/
  `stations`/`categories`) plus skill bawaan namespaced. Install:

```bash
cp -r hermes-plugin/ispunet ~/.hermes/plugins/ispunet
hermes plugins doctor ispunet    # validasi
hermes plugins enable ispunet
```

Plugin murni stdlib — tidak ada `python_dependencies`. `register(ctx)` dan
kelima mode tool (`current`, `station`, `stations`, `compare`, `categories`)
sudah diverifikasi lokal (stub ctx + API live); Doctor menjalankan validasi yang
sama di instalasi Hermes asli.

## Cacat data upstream yang ditangani

API KLHK tidak konsisten; `ispunet/normalize.py` memperbaikinya sekali untuk
library, CLI, REST, plugin, dan skill.

| # | Cacat upstream | Penanganan |
|---|---|---|
| 1 | `waktu` dua format (`2026-10-27 20:00:00` dan `27-Oktober-2026 20:00:00`), `time_z` hanya di sebagian endpoint | `waktu_iso` + `zona_waktu`; offset dari `time_z` → `time_offset` → provinsi |
| 2 | `waktu_24_rev` hanya jam → 24 slot tampak duplikat (Palangka Raya 07:00-17:00 lalu 08:00-20:00) | timestamp dari `waktu_24` (tanggal+jam), duplikat dibuang & dicatat |
| 3 | Seri 24 jam bolong di tengah (PM10 Sampit null 04:00-16:00) dan celah antar hari | `cakupan`, `hilang`, `celah`, `catatan` per seri |
| 4 | Nilai di luar skala (Palangka Raya PM2.5 indeks 1252, PM10 4091) | `mencurigakan` + `peringatan`; nilai TIDAK dibuang |
| 5 | `is_maintenance` konstan `"0"` di 107 stasiun | tidak dipakai; `status` diturunkan dari data |
| 6 | `getStations` tidak memuat semua stasiun aktif (Palangka Raya, Banjar Baru, Perawang, Mobile AQMS Kalteng) | mode `current`/`compare` memakai `getData/lat/lng` |
| 7 | `waktu` bisa sangat basi (Perawang Des-2024, Banjar Baru 28 hari) | `umur_data_jam` + `usang`; peringkat `current` mengutamakan data segar |
| 8 | `getDetail/stasiun/<id>` balas `rows: null` untuk ID tak dikenal, tanpa saran | 404 + `saran_id` + `pengganti` |
| 9 | Rate limit `HTTP 400 "Too Many Attempts."` | retry + backoff, lalu error jelas (bukan "stasiun tidak ditemukan") |

## Konfigurasi

Semua opsional (env):

| Env | Default | Keterangan |
|---|---|---|
| `ISPUNET_API_URL` | `https://ispu.kemenlh.go.id/apimob/v1/` | Base URL API |
| `ISPUNET_API_KEY` | kredensial publik APK | Header `x-api-key` |
| `ISPUNET_API_SIGNATURE` | kredensial publik APK | Header `x-api-signature` |

## Kategori ISPU

| uid | Kategori | Batas | Warna |
|---|---|---|---|
| 1 | BAIK | 0–50 | hijau `#00cc00` |
| 2 | SEDANG | 51–100 | biru `#0000cc` |
| 3 | TIDAK SEHAT | 101–200 | kuning `#cccc00` |
| 4 | SANGAT TIDAK SEHAT | 201–300 | merah `#cc0000` |
| 5 | BERBAHAYA | >300 | hitam `#000000` |

## Catatan legal

Klien ini mengakses API publik yang sama dengan aplikasi resmi ISPUNet.
Kredensial bawaan adalah kredensial yang didistribusikan ke semua perangkat
dalam APK resmi (statis di bundle JS), bukan kredensial privat.
Data tetap milik KLHK — gunakan dengan bijak.
