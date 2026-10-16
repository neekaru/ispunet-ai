# ispunet-py

Kualitas udara Indonesia (**ISPU** — Indeks Standar Pencemar Udara, resmi **KLHK**)
sebagai library Python, REST API, CLI, dan skill/plugin untuk **OpenClaw** & **Hermes**.

Dibangun ulang dari APK resmi `id.go.menlhk.iku.app` v1.5.5 (Ionic/Cordova):
endpoint, header, dan rekomendasi kesehatan diambil persis dari
`src/app/services/api.service.ts` hasil dekompilasi.

```
ispunet-py/
├── ispunet/            # package: client, server (FastAPI), CLI
│   ├── client.py       # IspuClient — wrapper API ispu.kemenlh.go.id/apimob/v1
│   ├── constants.py    # endpoint, kredensial publik, kategori, rekomendasi
│   ├── server.py       # REST API FastAPI
│   └── cli.py          # CLI (stations/current/station/categories/serve)
├── skills/ispunet/     # skill standalone (SKILL.md + skrip stdlib)
├── hermes-plugin/ispunet/  # plugin native Hermes: tool `ispu` + skill bawaan
├── openclaw.plugin.json    # manifest plugin OpenClaw
└── pyproject.toml
```

## Install

```bash
pip install -e .        # atau: uv pip install -e .
```

Butuh Python ≥ 3.10. Runtime: httpx, fastapi, uvicorn.
Skill (`skills/ispunet/scripts/ispunet.py`) **tanpa dependensi** — cuma stdlib.

## CLI

```bash
ispunet current -6.194790 106.822998          # udara di sekitar koordinat
ispunet station DKI1                          # detail + riwayat 24 jam stasiun
ispunet stations --limit 20                   # semua stasiun se-Indonesia
ispunet categories                            # definisi 5 kategori ISPU
ispunet serve --port 8000                     # jalankan REST API
```

Semua perintah menerima `--json` untuk output JSON.

## REST API

`ispunet serve` lalu:

| Endpoint | Deskripsi |
|---|---|
| `GET /current?lat=&lon=` | Udara terkini di sekitar koordinat (stasiun terdekat + sekitarnya + rekomendasi) |
| `GET /stations` | Semua stasiun pemantauan + nilai terkini |
| `GET /stations/{id}` | Detail stasiun + riwayat 24 jam + rekomendasi kesehatan |
| `GET /categories` | 5 kategori ISPU (BAIK … BERBAHAYA) |
| `GET /docs` | Swagger UI |

Contoh:

```bash
curl 'http://127.0.0.1:8000/current?lat=-6.2&lon=106.816'
```

## Library

```python
from ispunet import IspuClient, recommendation

c = IspuClient()
rows = c.current(-6.2, 106.816)        # list; rows[0] = stasiun terdekat
rows[0]["kategori"]["nilai"]          # 'TIDAK SEHAT'
detail = c.station_detail("DKI1")      # detail + riwayat 24 jam
recommendation(3)                      # saran kesehatan utk kategori tsb
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
keempat mode tool sudah diverifikasi lokal (stub ctx + API live); Doctor
menjalankan validasi yang sama di instalasi Hermes asli.

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
