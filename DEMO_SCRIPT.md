# DEMO_SCRIPT.md · Naskah Video Demo (5:43, Bahasa Indonesia)

Setiap klaim teknis di bawah sudah diverifikasi terhadap kode. Jangan menambah
angka atau nama teknologi yang tidak ada di sini.

**Fakta yang sudah terverifikasi:**
- Speedup Monte Carlo: **61,2×** pada 100.000 simulasi. Angka ini yang tersimpan
  di `evidence/benchmark.json` dan bisa dibuka juri. Ucapkan angka itu, bukan
  hasil run lain. (Antar-run wajar berkisar 57–62×; kalau ditanya, sebutkan
  rentangnya dan tunjuk file buktinya.)
- Perangkat: `AMD GPU (gfx1100)`, 48 GB, ROCm 7.2
- Briefing & opsi kebijakan: Fireworks (`gpt-oss-120b`), karena `SIM_BACKEND=fireworks`
- Sumber live: USGS, GDACS, BMKG, BMKG-RAIN, OPEN-METEO, GDELT
- 153 tes otomatis

**Arti warna & bentuk marker** (dari `frontend/src/lib/api.js`, jangan dikarang):

| Tampilan | Arti sebenarnya |
|---|---|
| Merah | severity ≥ 0,70 (bahaya apa pun) |
| Kuning / amber | severity 0,40–0,69 (bahaya apa pun) |
| Teal | severity < 0,40 (bahaya apa pun) |
| Berlian ungu | `kind = tension` (sinyal berita), berapa pun severity-nya |
| Radius lingkaran | melebar sesuai severity |

Warna **tidak** menandakan jenis bencana atau sumber datanya. Kekeringan di
Brasil dan gempa M5.5 sama-sama kuning kalau severity-nya menengah. Sinyal
prakiraan banjir dikenali dari **judulnya** ("Flood risk signal (forecast)")
dan sumbernya (OPEN-METEO / BMKG-RAIN), bukan dari warnanya.

**Yang TIDAK boleh diucapkan** (tidak benar untuk konfigurasi ini):
- ❌ "MI300X" atau "192GB HBM". Kartunya gfx1100, 48GB
- ❌ "vLLM melayani penalaran skenario". Jalur itu ada di kode, tapi demo ini memakai Fireworks
- ❌ "Titik kuning artinya prakiraan banjir". Kuning artinya severity menengah
- ❌ Menyebut nama opsi respons dari hafalan. LLM menulisnya ulang tiap simulasi

---

## [0:00–0:26] Pembuka: masalahnya, bukan produknya

> "Ketika bencana terjadi, seorang pengambil keputusan punya waktu beberapa jam.
> Dan alat yang tersedia hari ini, Crisis24, Dataminr, dashboard GDACS,
> semuanya menjawab pertanyaan yang sama: *apa yang sedang terjadi.*
>
> Tidak satu pun menjawab pertanyaan yang sebenarnya ia butuhkan: *kalau saya
> evakuasi sekarang, berapa nyawa yang terselamatkan, dan berapa biayanya?*
>
> Itu lapisan keputusan. Dan itu yang kami bangun. Namanya CrisisCommand."

*(Globe berputar, marker berdenyut.)*

---

## [0:26–0:59] Data live: ini bukan mockup

> "Setiap titik di sini kejadian nyata, masuk beberapa menit lalu. Gempa dari
> USGS. Peringatan multi-bahaya dari GDACS, sistem PBB. Gempa Indonesia langsung
> dari BMKG.
>
> **Warnanya menandakan tingkat keparahan**, bukan jenis bencananya. Berlian ungu
> adalah sinyal ketegangan geopolitik dari kepadatan pemberitaan, dan kami tandai
> *confidence rendah*, karena memang begitu adanya."

*(Tunjuk kartu "Flood risk signal (forecast)" di feed.)*

> "Yang ini bahkan bukan bencana yang sedang terjadi, melainkan **prakiraan risiko
> banjir**: prakiraan hujan resmi disilangkan dengan riwayat banjir daerah itu."

---

## [0:59–1:23] Drill: kenapa event historis, bukan live

*(Klik filter DRILLS → banjir Jakarta.)*

> "Perhatikan label ini: **HISTORICAL DRILL, documented 2020 event**.
>
> Kenapa kami simulasikan banjir 2020, bukan gempa yang baru masuk tadi?
> Karena simulasi butuh **basis populasi tervalidasi**. Event ini punya:
> 400 ribu orang terpapar, 397 ribu mengungsi. Angka terdokumentasi.
>
> Event live tidak punya itu. Dan kami menolak mengarangnya."

---

## [1:23–1:47] Briefing AI: dan kenapa ada jeda

*(Panel briefing memuat. Spinner "ANALYZING FEED DATA" terlihat.)*

> "Sekilas tulisan *analyzing feed data* ini. Datanya sudah ada sejak awal.
> Yang sedang berjalan adalah **model AI di Fireworks**, yang berjalan di atas
> infrastruktur AMD, sedang menulis briefing situasi. Sekitar tujuh detik.
>
> Dan lihat strukturnya. Bukan cuma ringkasan."

---

## [1:47–2:15] Confirmed vs Key Unknowns: inti kredibilitas

> "**CONFIRMED**: fakta yang benar-benar ada di data. Banjir dimulai 1 Januari
> 2020 pukul 03:00 UTC. Severity 0,75. Koordinatnya ini.
>
> **KEY UNKNOWNS**: yang *tidak* kami ketahui. Tinggi muka air saat ini.
> Kerusakan infrastruktur. Jumlah pengungsi terkini.
>
> Ini pembeda paling penting dari seluruh produk ini. Dalam krisis, AI yang
> terdengar yakin padahal tidak tahu, itu berbahaya. Kami memaksa modelnya
> memisahkan mana yang fakta, mana yang lubang informasi."

---

## [2:15–3:10] RUN SIMULATION: di sinilah GPU-nya bekerja

*(Tekan RUN SIMULATION. Readout GPU naik.)*

> "Sekarang dua mesin bekerja berurutan.
>
> **Pertama, GPU AMD.** Sepuluh ribu simulasi stokastik, untuk tiga horizon
> waktu sekaligus: enam, dua puluh empat, tujuh puluh dua jam. Tiga puluh ribu
> skenario, dijalankan sebagai **satu operasi tensor batched** di PyTorch/ROCm.
> Tidak ada perulangan Python.
>
> Di CPU: 201 milidetik. Di GPU AMD ini: 3,3 milidetik. **Enam puluh satu kali
> lebih cepat.** Dan makin besar batch-nya, makin lebar jaraknya: 12× pada
> sepuluh ribu, 39× pada lima puluh ribu, 61× pada seratus ribu. Itu bukti
> kernelnya benar-benar paralel, bukan perulangan yang menyamar.
>
> Perhatikan readout ini: `AMD GPU (gfx1100)`, 48 gigabyte. Aplikasi ini tidak
> pernah menebak nama kartunya. Ia melaporkan perangkat yang benar-benar dipakai."

---

## [3:10–4:13] Hasil: rentang, bukan angka tunggal

> "Hasilnya bukan satu angka. **51 ribu sampai 336 ribu orang terpapar**,
> persentil 10 sampai 90. Karena presisi palsu dalam krisis itu berbahaya.
>
> **Kedua, LLM menyusun tiga opsi respons.** Tapi perhatikan: model ini
> **tidak boleh mengarang angka**. Ia hanya mengalikan keluaran Monte Carlo
> dengan faktor mitigasi tervalidasi. Narasinya dari AI; angkanya dari mesin.
>
> **Evakuasi cepat**: paparan turun menjadi **5 sampai 109 ribu**. Biaya 10
> sampai 30 juta dolar, respons dua jam. Trade-off-nya: beban anggaran, dan
> perpindahan massal berisiko memicu keresahan sosial.
>
> **Pemantauan intensif**: paparan hampir tidak berubah, **48 sampai 336 ribu**,
> dengan biaya seperseratusnya. Faktor mitigasinya paling banyak memangkas lima
> persen, dan kami tidak berpura-pura sebaliknya.
>
> **AI tidak memutuskan. Manusia yang memutuskan**, dan sekarang ia melihat harga
> dari tiap pilihan."

> ⚠ **Nama ketiga opsi ditulis oleh LLM dan berubah setiap kali simulasi
> dijalankan** (mis. "Rapid Urban Flood Evacuation" vs "Immediate Staged
> Evacuation"). Jangan menghafal namanya. Yang tetap adalah **posturnya**:
> agresif, bertahap, pantau. Bacalah dari layar saat merekam.

*(Klik satu opsi → zona evakuasi tergambar di globe.)*

---

## [4:13–5:30] Event live: segmen yang paling menentukan di mata juri

*(Klik filter **LIVE**. Pilih gempa yang baru masuk, mis. M4.7 dekat Tadine,
New Caledonia. Kamera terbang. Briefing mengetik dirinya sendiri.)*

> "Sekarang gempa yang baru masuk beberapa jam lalu, langsung dari USGS.
> Magnitudo empat koma tujuh, lepas pantai New Caledonia.
>
> Briefing-nya tetap ditulis. Lihat baris terakhir **CONFIRMED**:
> *'No population context provided in the feed.'* Modelnya **mengakui data
> populasinya tidak ada.** Ia tidak menebak.
>
> Dan **KEY UNKNOWNS**: apakah guncangannya terasa, apakah ada kerusakan, apakah
> bisa memicu tsunami. Pertanyaan yang benar untuk gempa lepas pantai, tidak satu
> pun dijawab dengan karangan."

*(Tunjuk catatan abu-abu di bawah panel.)*

> "Dan di sini **tidak ada tombol RUN SIMULATION.** Hanya satu kalimat:
> *live event, no vetted population data yet, so no simulation.*
>
> Ini keputusan desain, bukan keterbatasan. Kami bisa saja mengarang basis
> populasi dari peta kepadatan global, lalu menampilkan angka korban yang
> terlihat meyakinkan. Kami memilih tidak.
>
> Presisi palsu di alat krisis bukan sekadar salah, ia berbahaya. Seorang pejabat
> bisa mengevakuasi kota yang keliru karena angka yang terdengar pasti padahal
> dikarang.
>
> Aturannya sederhana: **tidak ada basis populasi tervalidasi, tidak ada
> simulasi.** Alat komersial menampilkan kejadian ini lalu berhenti. Kami
> menampilkannya, mengakui apa yang belum kami tahu, dan menolak berpura-pura."

---

## [5:30–5:43] Penutup

> "Dibangun di AMD Developer Cloud dengan ROCm, PyTorch, dan Fireworks AI.
> Seratus lima puluh tiga tes otomatis. Bekerja penuh secara offline.
>
> Alat komersial menunjukkan krisisnya.
> **CrisisCommand mensimulasikan keputusanmu.**"

---

## Kalau perlu versi lebih pendek

Versi penuh terukur **5:43**. Kalau kamu ingin lebih ringkas, ini urutan
pemangkasan dari yang paling aman ke yang paling menyakitkan:

| Potong | Hemat | Jadi |
|---|---|---|
| Paragraf kedua "Data live" (prakiraan banjir) | ~12s | 5:31 |
| Rincian biaya di "Hasil"; cukup sebut rentang paparan | ~20s | 5:11 |
| Segmen "Briefing AI", gabungkan ke Confirmed/Unknowns | ~24s | 4:47 |
| Rincian "12x / 39x / 61x"; cukup sebut 61x | ~15s | 4:32 |
| Paragraf KEY UNKNOWNS di segmen event live | ~15s | 4:17 |

**Jangan pernah potong**: segmen event live yang menunjukkan tidak adanya tombol
RUN SIMULATION, dan kalimat "AI tidak memutuskan, manusia yang memutuskan". Dua
hal itu yang membedakanmu dari ratusan submission lain. Lebih baik membuang
angka benchmark daripada membuang argumen kejujuran.

---

## Catatan pengambilan gambar

- Rekam dari URL tunnel (footer menampilkan GPU AMD), **bukan** localhost
- Sebelum merekam: pastikan badge kanan atas berbunyi `LIVE`
- Total durasi terukur **±5:43** (150 kata/menit + jeda aksi). Formulir menyebut "3 menit" sebagai
  panduan, bukan batas keras. Kalau kamu perlu memangkas, potong bagian
  [0:25–0:50] (penjelasan warna marker) menjadi satu kalimat, **jangan** potong
  segmen event live: itu argumen kredibilitas terkuatmu.
- **Briefing tampil dengan animasi mengetik.** Kalau videomu memperlihatkan
  kalimat terpotong di tengah, itu animasi yang belum selesai, bukan bug.
  Tunggu sampai kursornya berhenti sebelum melanjutkan narasi.
- Event live yang muncul saat kamu merekam **tidak akan sama** dengan contoh di
  naskah ini (feed-nya hidup). Sebutkan magnitudo dan lokasi yang benar-benar
  ada di layarmu.
- Kalau Wi-Fi tempat acara mati: `SEED_MODE=true` di laptop, demo tetap jalan
  penuh. Yang hilang cuma readout GPU-nya.
