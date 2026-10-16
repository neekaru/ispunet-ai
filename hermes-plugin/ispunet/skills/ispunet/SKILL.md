---
name: ispunet
description: Cek ISPU/kualitas udara Indonesia — pendamping tool `ispu`.
version: 1.0.0
metadata:
  hermes:
    tags: [Environment, Air-Quality, Indonesia, ISPU, KLHK]
---

# ISPUNet — Kualitas Udara Indonesia

Skill ini menemani tool **`ispu`** (toolset `ispunet`) yang terdaftar otomatis
saat plugin ispunet aktif.

## When to Use

- User bertanya kualitas udara / ISPU / polusi di lokasi Indonesia.
- User butuh rekomendasi aktivitas berbasis kualitas udara.
- User bertanya arti kategori ISPU.

## Quick Reference

Semua mode dipanggil lewat tool `ispu`:

| Kebutuhan | args |
|---|---|
| Udara di koordinat | `{"mode": "current", "lat": -6.2, "lon": 106.816}` |
| Detail stasiun + riwayat 24 jam | `{"mode": "station", "station_id": "DKI1"}` |
| Daftar semua stasiun | `{"mode": "stations", "limit": 20}` |
| Definisi kategori ISPU | `{"mode": "categories"}` |

## Procedure

1. User menyebut kota tanpa koordinat → cari lat/lon kota, lalu `mode: current`.
2. Jawab: kategori + angka ISPU + polutan utama + `rekomendasi` (sudah siap pakai).
3. User minta riwayat → `mode: station` dengan `id_stasiun` dari hasil current/stations.

## Pitfalls

- `ispu` = indeks 0–500+, BUKAN µg/m³; konsentrasi ada di `konsentrasi`.
- `kategori.uid`: 1=BAIK 2=SEDANG 3=TIDAK SEHAT 4=SANGAT TIDAK SEHAT 5=BERBAHAYA.
- Jika `error` di hasil, jangan mengarang data — laporkan API tidak tersedia.
- Jawab dalam Bahasa Indonesia bila user bertanya dalam Bahasa Indonesia.
