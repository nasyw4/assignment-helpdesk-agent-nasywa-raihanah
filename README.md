# IT Helpdesk Assistant — RAG & Mini-Agent API

Backend API (FastAPI) yang menggabungkan **RAG** dan **workflow routing sederhana (mini-agent)** dalam satu endpoint `/ask`, dikemas dalam container Docker.

## 1. Problem Statement

### Objective
Tim People & IT Operations menerima banyak pertanyaan repetitif dari karyawan setiap hari. Proyek ini membangun asisten AI internal yang menjawab dua jenis permintaan tersebut secara otomatis dalam satu sistem.

### Dua jenis permintaan user

| Jenis | Intent | Contoh | Ditangani oleh |
|---|---|---|---|
| Pertanyaan informasi / kebijakan | `faq` | "Berapa jatah cuti tahunan saya?", "Bagaimana cara reset password VPN?" | RAG (semantic search + LLM) |
| Permintaan cek data spesifik | `ticket_status` | "Apa status TICKET-0002 saya?" | Tool call (lookup eksak di data tiket) |

Status tiket tidak dijawab lewat RAG karena sifatnya data spesifik yang butuh pencarian eksak berdasarkan ID, bukan kemiripan makna. Menjawabnya lewat retrieval semantik berisiko menghasilkan jawaban yang salah atau dikarang.

### Batasan dan asumsi
- Knowledge base berasal dari `data/it_helpdesk_knowledge_base.csv` (31 entri FAQ). Data tiket berasal dari `data/mock_tickets.csv` (15 tiket) dan merupakan data mock.
- Format ID tiket: `TICKET-XXXX` (4 digit).
- Bahasa yang didukung: Bahasa Indonesia.
- Setiap request berdiri sendiri (tanpa riwayat percakapan).
- Tidak ada autentikasi; sistem diasumsikan dipakai di lingkungan internal.
- Aplikasi hanya dijalankan lokal (termasuk di container), tidak di-deploy ke cloud.

## 2. Desain Workflow

```
            POST /ask {"query": "..."}
                      │
                      ▼
              ┌───────────────┐
              │ Intent        │   router.py → detect_intent()
              │ Detection     │
              └───────┬───────┘
          ┌───────────┴────────────┐
          ▼                        ▼
   intent = faq             intent = ticket_status
          │                        │
          ▼                        ▼
 ┌──────────────────┐     ┌──────────────────────┐
 │ RAG (rag.py)     │     │ Tool call (tools.py) │
 │ 1. embed query   │     │ 1. extract_ticket_id │
 │ 2. FAISS top-3   │     │ 2. cari di CSV       │
 │ 3. prompt + LLM  │     │ 3. format jawaban    │
 └────────┬─────────┘     └──────────┬───────────┘
          └───────────┬──────────────┘
                      ▼
      {"status": "...", "intent": "...", "data": "..."}
```

### Kriteria intent

| Intent | Kriteria (baseline berbasis keyword / regex) |
|---|---|
| `ticket_status` | Query memuat ID tiket berpola `ticket` + angka (mis. `TICKET-0002`, `ticket 0005`), **atau** menyebut kata "tiket/ticket" bersama kata status ("status", "cek", "periksa", "progres", dst.) |
| `faq` | Semua query lainnya, termasuk yang di luar cakupan (ditolak oleh RAG berdasarkan instruksi di prompt) |
| `unknown` | Query kosong |

Jika intent `ticket_status` tetapi ID tiket tidak ada di query, sistem meminta user menyebutkan ID tiketnya.

### Komponen

| File | Peran |
|---|---|
| `app/main.py` | Endpoint FastAPI (`/ask`, `/health`), membangun index FAISS saat startup, error handling |
| `app/router.py` | Intent detection, ekstraksi ID tiket, routing ke RAG atau tool |
| `app/rag.py` | Embedding (`gemini-embedding-001`), index FAISS (cosine via inner product), semantic search, prompt Persona/Task/Context/Format, LLM (`gemini-2.5-flash`) |
| `app/tools.py` | `get_ticket_status()`: lookup tiket di CSV, tidak crash jika ID tidak ditemukan |

### Error handling
- Query kosong → HTTP 400.
- LLM / embedding gagal → HTTP 503 dengan pesan error.
- Tiket tidak ditemukan atau ID tidak disebutkan → response sukses berisi pesan informatif.
- Index FAISS dibangun sekali saat startup (bukan per request).

## 3. Cara Menjalankan

### Prasyarat
- Python 3.11+
- API key Gemini
- Docker (opsional, untuk menjalankan via container)

### Konfigurasi API key
```bash
cp .env.example .env
# isi GEMINI_API_KEY di dalam .env
```
File `.env` tidak boleh di-commit (sudah ada di `.gitignore`). API key hanya dibaca dari environment variable.

### Lokal (tanpa Docker)
Jalankan dari root project (path data bersifat relatif):

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Buka `http://localhost:8000/docs` untuk mencoba endpoint lewat Swagger UI.

> Startup membutuhkan waktu beberapa saat karena seluruh knowledge base di-embed lewat API saat server dinyalakan.

### Dengan Docker
```bash
docker build -t it-helpdesk-assistant .
docker run -p 8000:8000 --env-file .env it-helpdesk-assistant
```

API key disuntikkan lewat `--env-file`, tidak ikut masuk ke dalam image (`.env` dikecualikan lewat `.dockerignore`). Jika port 8000 sudah terpakai oleh server lokal, hentikan server lokal atau gunakan `-p 8001:8000`.

### Contoh request
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "apa status TICKET-0002?"}'
```

Contoh response:
```json
{
  "status": "success",
  "intent": "ticket_status",
  "data": "Tiket TICKET-0002 (Permintaan akses Google Analytics) berstatus 'Diproses'. ..."
}
```

## 4. Hasil Pengujian

Pengujian dilakukan lewat endpoint `/ask`. Lima skenario pertama adalah skenario wajib; skenario 6–8 adalah pengujian tambahan untuk menguji batas router.

| # | Query | Intent diharapkan | Intent terdeteksi | Router tepat? | Response (ringkas) |
|---|---|---|---|---|---|
| 1 | `pengen tau slip gaji ku dongsss!` | `faq` | `faq` | ✅ | Slip gaji dapat diunduh setiap tanggal 25 lewat portal HR, menu Payroll. |
| 2 | `Boleh gak sih WFH setiap hari?` | `faq` | `faq` | ✅ | Tidak boleh; WFH maksimal 2 hari per minggu sesuai kesepakatan dengan atasan. |
| 3 | `gmn kabarnya ticket 0005?` | `ticket_status` | `ticket_status` | ✅ | TICKET-0005 (Reset password VPN gagal terus) berstatus "Diproses", pemohon Dedi Kurniawan, update 2026-08-27. |
| 4 | `gmn kabarnya ticket 1000?` | `ticket_status` | `ticket_status` | ✅ | "Tiket TICKET-1000 tidak ditemukan. Pastikan ID tiket benar." (tidak crash) |
| 5 | `Sekarang gimana keadaan kalimantan?` | di luar cakupan | `faq` | ✅ (ditolak RAG) | "Maaf, saya tidak memiliki informasi ... hubungi tim IT atau HR." |
| 6 | `laptop saya gak bisa nyala, gimana status tiket saya` | `ticket_status` | `ticket_status` | ✅ | Meminta user menyebutkan ID tiket (format TICKET-XXXX). |
| 7 | `gmn kabarnya tiket 0005?` | `ticket_status` | `faq` | ❌ | RAG menjawab tidak punya informasi tentang status tiket 0005. |
| 8 | `tiket saya udah di proses belum ya?` | `ticket_status` | `faq` | ❌ | RAG menjawab tidak punya informasi status tiket; user diarahkan menghubungi tim IT/HR. |

**Ringkasan:** 6 dari 8 query diarahkan ke komponen yang tepat. Seluruh skenario wajib (1–5) tepat.

### Observasi
- **RAG (skenario 1–2):** Semantic search menemukan FAQ yang relevan meskipun query memakai bahasa santai/slang ("dongsss", "gak sih"). Jawaban sesuai isi knowledge base. Pada skenario 2, jawaban ditambah saran "hubungi tim IT atau HR" yang sebenarnya tidak diperlukan.
- **Tool call (skenario 3–4):** Ekstraksi ID bekerja, termasuk normalisasi `ticket 0005` → `TICKET-0005`. ID yang tidak ada ditangani dengan pesan informatif tanpa membuat aplikasi crash.
- **Di luar cakupan (skenario 5):** Instruksi "jawab hanya dari context dan jangan mengarang" pada prompt berhasil membuat model mengaku tidak tahu, bukan mengarang jawaban.
- **Kegagalan router (skenario 7–8):** Keduanya adalah permintaan cek tiket yang diarahkan ke `faq`. Router memiliki dua aturan, dan kedua query gagal memenuhi keduanya, dengan penyebab berbeda:
  - **Aturan 1 (regex ID tiket):** hanya mengenali kata `ticket` (dengan "c") diikuti angka. Skenario 7 menulis "tiket 0005" (tanpa "c"), sehingga regex tidak cocok. Skenario 8 tidak memuat angka sama sekali.
  - **Aturan 2 (kata "tiket/ticket" + kata status):** mengenali "tiket" maupun "ticket", tetapi mewajibkan adanya kata status seperti "status", "cek", atau "progres". Skenario 7 hanya memakai kata "kabarnya" dan skenario 8 memakai "di proses"; keduanya tidak ada di daftar kata status.
  - Sebagai pembanding, skenario 3 (`gmn kabarnya ticket 0005?`) berhasil karena memakai "ticket" (dengan "c"), sehingga lolos aturan 1.
- **Dampak kegagalan:** Meskipun salah rute, sistem tidak mengarang status tiket; RAG mengaku tidak punya informasinya. Kegagalan terjadi secara aman, tetapi user tidak mendapat jawaban yang seharusnya tersedia.
- **Latensi:** Beberapa request terasa lambat saat diuji (satu panggilan ke API embedding untuk query, lalu satu panggilan LLM). Waktu respons tidak diukur secara formal.

## 5. Keterbatasan Sistem

1. **Intent detection berbasis keyword/regex.** Rapuh terhadap variasi bahasa. Terbukti pada skenario 7 dan 8: "tiket 0005" gagal karena regex ID hanya mengenali ejaan "ticket" (dengan "c"), dan "tiket saya udah di proses belum" gagal karena kata "proses" tidak ada di daftar kata status. Perbaikan: ubah regex agar menerima "tiket" dan "ticket", tambah variasi kata status (mis. "proses", "kabar", "udah"), atau gunakan intent detection berbasis LLM.
2. **Satu intent per query.** Query yang berisi dua permintaan sekaligus (mis. pertanyaan kebijakan sekaligus cek tiket) hanya diarahkan ke satu jalur.
3. **Query di luar cakupan tidak punya jalur sendiri.** Semuanya masuk `faq`, dan penolakan hanya bergantung pada instruksi prompt, tanpa ambang batas skor kemiripan. Model bisa saja tetap menjawab jika context yang ter-retrieve tampak relevan.
4. **Respons LLM kurang konsisten.** Terkadang menambahkan saran "hubungi tim IT/HR" yang tidak relevan (skenario 2).
5. **Tidak ada memori percakapan.** Jika user menyebut ID tiket di pesan berikutnya setelah diminta, sistem tidak mengaitkannya dengan pesan sebelumnya.
6. **Index dibangun ulang setiap startup.** Seluruh knowledge base di-embed lewat API setiap server dinyalakan (tidak disimpan ke disk), sehingga startup lambat dan bergantung pada ketersediaan API serta kuota.
7. **Panggilan embedding bersifat sinkron.** `semantic_search` memanggil API secara blocking di dalam handler async, sehingga dapat menghambat request lain saat beban tinggi.
8. **Tidak ada autentikasi atau pengecekan kepemilikan tiket.** Siapa pun yang mengetahui ID tiket dapat melihat statusnya.
9. **Data mock.** Data tiket berasal dari CSV statis, bukan sistem tiket sungguhan.
