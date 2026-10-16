---
name: ispunet
description: Cek kualitas udara / ISPU Indonesia — data resmi KLHK.
version: 1.0.0
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
| Cari/detail stasiun by ID | `python3 {baseDir}/scripts/ispunet.py station DKI1` |
| Semua stasiun se-Indonesia | `python3 {baseDir}/scripts/ispunet.py stations --limit 20` |
| Definisi kategori ISPU | `python3 {baseDir}/scripts/ispunet.py categories` |

## Procedure

1. **Koordinat**: Jika user menyebut nama tempat tapi bukan koordinat, cari
   latitude/longitude kota tsb (geocoding internal), lalu jalankan `current`.
   Kota besar umumnya punya stasiun; jika `jumlah_stasiun_sekitar` 0, beri tahu
   user bahwa tidak ada stasiun pemantauan resmi di sekitar lokasi itu.
2. **Baca hasil `current`**: `stasiun_terdekat.kategori.nilai` = kategori ISPU,
   `ispu` = angka indeks, `param` = polutan kritis (biasanya PM2.5),
   `rekomendasi` = saran kesehatan siap pakai.
3. **Detail stasiun**: bila user ingin riwayat, gunakan `station <id_stasiun>`
   — hasilnya memuat `riwayat_24jam`.
4. **Jawab dalam Bahasa Indonesia** bila user bertanya dalam Bahasa Indonesia.
   Format jawaban: kategori + angka ISPU + polutan utama + rekomendasi.

## Pitfalls

- ID stasiun peka huruf besar (mis. `DKI1`, bukan `dki1`). Daftar ID valid ada
  di output `stations` (field `id_stasiun`).
- Endpoint upstream kadaluarsa/lambat — skrip sudah retry 3x; jika tetap gagal,
  laporkan API sedang tidak tersedia, jangan mengarang data.
- Angka `ispu` adalah indeks (0-500+), BUKAN konsentrasi µg/m³. Konsentrasi ada
  di field `konsentrasi`.
- `kategori.nilai_uid`: 1=BAIK, 2=SEDANG, 3=TIDAK SEHAT, 4=SANGAT TIDAK SEHAT, 5=BERBAHAYA.

## Verification

- `current` mengembalikan `stasiun_terdekat.ispu` berupa angka dan
  `kategori.nilai` salah satu dari 5 kategori di atas.
- `station DKI1` mengembalikan objek berisi `riwayat_24jam` non-kosong.
- Semua perintah exit code 0 saat sukses.
