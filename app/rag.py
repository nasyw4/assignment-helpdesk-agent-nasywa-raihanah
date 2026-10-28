"""
Modul RAG — mengubah knowledge base menjadi embedding, menyimpannya ke FAISS,
melakukan semantic search, lalu menghasilkan jawaban menggunakan LLM.

Alur ini serupa dengan yang sudah dibangun di Assignment 3 (Semantic Search &
LLM Application) dan Sesi 11 (Building a Simple RAG System) — di assignment ini,
alur tersebut dibungkus menjadi fungsi yang dipanggil oleh router.py.
"""

import os
import time
from dotenv import load_dotenv
load_dotenv()  # memuat GEMINI_API_KEY dari .env
import pandas as pd
import numpy as np
import faiss
from google import genai  # sesuaikan dengan library Gemini API yang digunakan

_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

KNOWLEDGE_BASE_PATH = "data/it_helpdesk_knowledge_base.csv"

# 🔧 TODO: muat knowledge base dan bangun index FAISS saat aplikasi startup
# (bukan di setiap request), agar lebih efisien. Pertimbangkan menggunakan
# FastAPI startup event atau lazy-loading dengan cache sederhana.

EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-flash-lite-latest"
#LLM_MODEL = "gemini-3.8-flash"

# Index dibangun sekali saat startup (lihat lifespan di main.py), bukan per request.
_index = None
_documents = None


def _get_embedding(text: str, retries: int = 3, delay: float = 2):
    for attempt in range(retries):
        try:
            result = _client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
            return result.embeddings[0].values
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


def build_index(path: str = KNOWLEDGE_BASE_PATH):
    """Muat knowledge base, buat embedding, simpan ke index FAISS (cosine via inner product)."""
    global _index, _documents
    df = pd.read_csv(path)
    documents = ("Q: " + df["question"] + " A: " + df["answer"]).tolist()
    embeddings = np.array([_get_embedding(d) for d in documents], dtype="float32")
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    _index, _documents = index, documents


def semantic_search(query: str, top_k: int = 3):
    """Kembalikan top_k dokumen paling relevan sebagai list of (dokumen, skor)."""
    if _index is None:
        build_index()
    q = np.array([_get_embedding(query)], dtype="float32")
    faiss.normalize_L2(q)
    scores, idxs = _index.search(q, top_k)
    return [(_documents[i], float(s)) for i, s in zip(idxs[0], scores[0]) if i != -1]


async def answer_from_knowledge_base(query: str) -> str:
    """
    Fungsi yang dipanggil router.py ketika intent = 'faq'.
    semantic_search -> susun prompt (Persona/Task/Context/Format) -> panggil LLM.
    """
    results = semantic_search(query)
    context = "\n".join(f"- {doc}" for doc, _ in results)

    prompt = f"""Persona: Kamu adalah asisten IT Helpdesk internal perusahaan yang ramah dan ringkas.

    Task: Jawab pertanyaan karyawan HANYA berdasarkan context di bawah. Jika context tidak memuat jawabannya, katakan bahwa kamu tidak memiliki informasinya dan sarankan menghubungi tim IT/HR. Jangan mengarang.

    Context:
    {context}

    Format: Jawab dalam Bahasa Indonesia, maksimal 3 kalimat, tanpa markdown.

    Pertanyaan: {query}
    Jawaban:"""

    response = await _client.aio.models.generate_content(model=LLM_MODEL, contents=prompt)
    return (response.text or "").strip()
