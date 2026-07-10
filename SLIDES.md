# SLIDES.md — Slide Presentation (PDF) untuk formulir submission

## Bingung: video atau slide?

Formulirnya meminta **dua artefak berbeda**. Bukan salah satunya.

| Field | Isinya | Sumber |
|---|---|---|
| **Video Presentation** | Rekaman layar demo, ±3 menit | naskah di [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| **Slide Presentation (PDF)** | Deck 8 halaman, dibaca juri **tanpa kamu di sana** | `pitch/CrisisCommand-Pitch.pdf` |

Bedanya penting. **Video menunjukkan produknya bekerja.** **Slide menjawab
pertanyaan yang tidak sempat kamu jawab di video**: siapa pembelinya, kenapa
tidak ada pesaing open-source, apa buktinya klaim AMD-mu, apa yang sudah jadi
dan apa yang belum.

Juri sering membaca deck lebih dulu, memutuskan apakah idemu menarik, baru
menonton videonya. Deck harus berdiri sendiri.

## File PDF-nya sudah ada

```
pitch/CrisisCommand-Pitch.pdf     # 8 halaman, 16:9, 1.1 MB
```

Langsung unggah file itu. Tidak perlu PowerPoint, tidak perlu Canva.

## Isi 8 slide

| # | Slide | Menjawab pertanyaan juri |
|---|---|---|
| 1 | *Dashboards show the crisis. We simulate your decision.* | Ini apa, dalam satu kalimat? |
| 2 | The gap | Kenapa belum ada yang membuatnya? |
| 3 | One globe. Three modes. A decision. | Demonya seperti apa? |
| 4 | Three compute paths on one AMD GPU | **Kenapa butuh GPU?** ← kriteria penilaian #3 |
| 5 | Honest by design | Kenapa saya harus percaya angkamu? |
| 6 | The buyers already own the dashboards | Ada pasarnya? ← kriteria #4 |
| 7 | Shipped, end to end | Selesai atau cuma mockup? ← kriteria #2 |
| 8 | Penutup | Siapa kalian? |

## Regenerasi PDF (kalau deck-nya diubah)

Deck-nya adalah `pitch/index.html` — satu file HTML, tanpa build, buka di
browser mana pun. Untuk mencetak ulang PDF-nya:

**Cara termudah** — buka `pitch/index.html` di Chrome/Edge → `Ctrl+P` →
Destination: *Save as PDF* → Layout: *Landscape* → More settings → centang
**Background graphics** (wajib, kalau tidak latar gelapnya hilang) → Save.

**Cara presisi** (yang dipakai menghasilkan file ini) — headless Chrome pada
1600×900, satu slide per halaman:

```bash
chrome --headless --print-to-pdf="pitch/CrisisCommand-Pitch.pdf" \
       --print-to-pdf-no-header --no-pdf-header-footer \
       "file:///path/to/pitch/index.html"
```

CSS `@media print` di dalam file sudah mengatur `page-break-after` per slide,
jadi hasilnya persis 8 halaman.

## Aturan kejujuran untuk deck ini

Sama seperti angka korban jiwa, **klaim tentang diri sendiri tidak boleh
dilebih-lebihkan**. Yang sudah dibersihkan dari deck ini:

- ❌ ~~"192 GB HBM3"~~ → kartu yang benar-benar dipakai punya **48 GB (gfx1100)**
- ❌ ~~"MI300X"~~ / ~~"AMD Instinct"~~ → RDNA3, bukan Instinct
- ❌ ~~chip "vLLM"~~ pada slide judul → demo berjalan dengan `SIM_BACKEND=fireworks`;
  vLLM ada di kode dan siap dipakai, tapi **tidak dijalankan** saat demo

Slide 4 sekarang menyatakannya apa adanya: opsi kebijakan dihasilkan oleh
**Fireworks** (yang berjalan di infrastruktur AMD), dan klien OpenAI-compatible
yang sama bisa diarahkan ke vLLM di GPU dengan satu variabel environment.

Angka speedup di deck (**61×**) sama persis dengan `evidence/benchmark.json`.
Kalau kamu menjalankan benchmark ulang dan angkanya bergeser, perbarui
keduanya — jangan biarkan deck dan bukti berbeda.
