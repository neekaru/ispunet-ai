---
name: ispunet
description: Cek kualitas udara / ISPU Indonesia — data resmi KLHK.
version: 2.0.0
author: hanafi
license: MIT
platforms: [linux, macos, windows]
metadata:
  openclaw:
    requires:
      bins:
        - python3
    emoji: "\U0001F32B\uFE0F"
    homepage: https://github.com/hanafi/ispunet-py
  hermes:
    tags: [Environment, Air-Quality, Indonesia, ISPU, KLHK]
    related_skills: []
---

# ISPUNet — Kualitas Udara Indonesia

Cek ISPU (Indeks Standar Pencemar Udara) resmi KLHK Indonesia melalui skrip
`scripts/ispunet.py` (murni Python stdlib, tanpa dependensi).

## When to Use

- User bertanya kualitas udara di kota/lokasi Indonesia ("gimana udara di Jakarta?").
- User minta ISPU stasiun tertentu ("udara di DKI1 sekarang berapa?").
- User butuh rekomendasi aktivitas berbasis kualitas udara.
- User bertanya arti kategori ISPU (BAIK / SEDANG / TIDAK SEHAT / dst).

## Quick Reference

Semua perintah output JSON. Skrip ada di folder skill ini — gunakan path
absolut, jangan andalkan cwd:
OpenClaw: `{baseDir}/scripts/ispunet.py`, Hermes: `${HERMES_SKILL_DIR}/scripts/ispunet.py`.

| Kebutuhan | Perintah |
|---|---|
| Udara di koordinat (lat lon) | `python3 {baseDir}/scripts/ispunet.py current -6.2 106.816` |
| Udara di kota tanpa ID stasiun | `python3 {baseDir}/scripts/ispunet.py current --kota "Palangka Raya"` |
| Detail stasiun by ID | `python3 {baseDir}/scripts/ispunet.py station DKI1` |
| Cari stasiun by nama/kota | `python3 {baseDir}/scripts/ispunet.py search samarinda` |
| Daftar stasiun + filter | `python3 {baseDir}/scripts/ispunet.py stations --q kalimantan --aktif --limit 20` |
| Banding beberapa kota | `python3 {baseDir}/scripts/ispunet.py compare Banjarmasin Pekanbaru Samarinda` |
| Definisi kategori ISPU | `python3 {baseDir}/scripts/ispunet.py categories` |

## Procedure

1. **Kota, bukan ID**: pakai `current --kota "<Nama Kota>"`. Banyak kota besar
   TIDAK punya ID di `getStations` (Banjarmasin, Samarinda, Pekanbaru, Palangka
   Raya) — `search` akan kosong, dan itu bukan berarti tidak ada data.
2. **Baca hasil `current`**: `primary.ispu` = angka ISPU, `primary.kategori.nilai`
   = kategori, `primary.param` = polutan kritis, `primary.rekomendasi` = saran
   kesehatan siap pakai, `catatan` = alasan pemilihan stasiun.
3. **WAJIB cek kesegaran**: `primary.usang` / `primary.umur_data_jam`. Bila
   `usang: true`, sampaikan terus terang ("data terakhir X jam lalu") dan JANGAN
   menyajikannya sebagai kondisi saat ini. Bila `status: "offline"` atau `ispu`
   null, laporkan stasiun tidak melaporkan ISPU dan sebutkan `pengganti`.
4. **Detail stasiun**: `station <id_stasiun>` memuat `riwayat_24jam` (slot
   ber-timestamp lengkap, `cakupan`, `hilang`, `celah`, `mencurigakan`).
   Bila ID tidak ada, skrip membalas `error` + `saran_id` + `pengganti` — pakai
   itu, jangan mengarang.
5. **Jawab dalam Bahasa Indonesia** bila user bertanya dalam Bahasa Indonesia.
   Format jawaban: kategori + angka ISPU + polutan utama + rekomendasi
   (+ peringatan kesegaran data bila ada).

## Pitfalls

- **Jangan pakai `konsentrasi`** — field itu sudah tidak ada. `indeks` = ISPU per
  polutan, `konsentrasi_rata_rata` = µg/m³ rata-rata 24 jam. Jangan menukar keduanya.
- `ispu` = indeks (0-500+), BUKAN µg/m³.
- `kategori.nilai_uid`: 1=BAIK, 2=SEDANG, 3=TIDAK SEHAT, 4=SANGAT TIDAK SEHAT, 5=BERBAHAYA.
- `is_maintenance` upstream selalu `"0"` (tidak berguna). Status nyata ada di
  `status` (`aktif`/`offline`) dan `usang`.
- Nilai bertanda di `mencurigakan` (mis. Palangka Raya indeks 1252/4091) adalah
  data upstream yang melampaui skala ISPU 500 — jangan dipakai menghitung
  rata-rata, dan jangan disembunyikan.
- ID stasiun tidak peka huruf besar/kecil (`dki1` = `DKI1`). Daftar ID valid ada
  di output `stations`/`search`.
- Endpoint upstream lambat dan bisa membalas `Too Many Attempts` — skrip sudah
  retry 3x; jika tetap gagal, laporkan API sedang tidak tersedia, jangan mengarang data.

## Verification

- `current` mengembalikan `primary.ispu` berupa angka dan `primary.kategori.nilai`
  salah satu dari 5 kategori di atas — atau `primary` null dengan `alasan_pemilihan`.
- `station DKI1` mengembalikan objek berisi `riwayat_24jam.seri` non-kosong dan
  `riwayat_24jam.cakupan`.
- `station BANJARMASIN` exit code 1 dengan `error`, `saran_id`, dan `pengganti`.
- Semua perintah exit code 0 saat sukses.
