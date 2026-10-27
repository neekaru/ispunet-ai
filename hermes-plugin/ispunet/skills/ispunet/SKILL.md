---
name: ispunet
description: Cek ISPU/kualitas udara Indonesia — pendamping tool `ispu`.
version: 2.0.0
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
- User minta riwayat 24 jam satu stasiun.
- User membandingkan beberapa kota sekaligus.

## Quick Reference

Semua mode dipanggil lewat tool `ispu`:

| Kebutuhan | args |
|---|---|
| Udara di koordinat | `{"mode": "current", "lat": -6.2, "lon": 106.816}` |
| Udara di kota (tanpa ID stasiun) | `{"mode": "current", "kota": "Palangka Raya"}` |
| Detail stasiun + riwayat 24 jam | `{"mode": "station", "station_id": "DKI1"}` |
| Cari/daftar stasiun | `{"mode": "stations", "q": "kalimantan", "hanya_aktif": true, "limit": 20}` |
| Banding beberapa kota | `{"mode": "compare", "targets": ["Banjarmasin", "Pekanbaru", "Samarinda"]}` |
| Definisi kategori ISPU | `{"mode": "categories"}` |

## Procedure

1. **Kota, bukan ID**: pakai `{"mode": "current", "kota": "<Nama Kota>"}`.
   Banyak kota besar TIDAK punya ID di `getStations` (Banjarmasin, Samarinda,
   Pekanbaru, Palangka Raya); `stations` akan kosong — itu bukan berarti tidak
   ada data.
2. **Baca hasil `current`**: `primary.ispu`, `primary.kategori.nilai`,
   `primary.param`, `primary.rekomendasi` (siap pakai), `catatan` (alasan
   pemilihan stasiun).
3. **WAJIB cek kesegaran**: `primary.usang` dan `primary.umur_data_jam`. Bila
   `usang: true`, katakan "data terakhir X jam lalu" dan JANGAN menyajikannya
   sebagai kondisi saat ini. Bila `status: "offline"` / `ispu` null, laporkan
   stasiun tidak melaporkan ISPU dan sebutkan `pengganti`.
4. **Riwayat**: `mode: station` memberi `riwayat_24jam` (slot ber-timestamp
   lengkap, `cakupan`, `hilang`, `celah`, `mencurigakan`).
5. Jawab dalam Bahasa Indonesia bila user bertanya dalam Bahasa Indonesia.

## Pitfalls

- `ispu` = indeks 0–500+, BUKAN µg/m³. `indeks` = ISPU per polutan;
  `konsentrasi_rata_rata` = µg/m³ rata-rata 24 jam. Jangan menukar keduanya.
- `kategori.nilai_uid`: 1=BAIK 2=SEDANG 3=TIDAK SEHAT 4=SANGAT TIDAK SEHAT 5=BERBAHAYA.
- `is_maintenance` upstream selalu `"0"` — abaikan. Pakai `status` + `usang`.
- `mencurigakan` menandai nilai di luar skala ISPU 500 (mis. Palangka Raya
  1252/4091). Jangan dipakai menghitung rata-rata; jangan juga disembunyikan.
- ID stasiun tidak peka huruf besar/kecil (`dki1` = `DKI1`).
- Bila hasil memuat `error`, jangan mengarang data. Untuk `station` yang tidak
  ada, gunakan `saran_id` / `pengganti`; untuk kegagalan API, laporkan API
  sedang tidak tersedia.
