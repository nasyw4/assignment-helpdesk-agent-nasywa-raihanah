"""
Entry point aplikasi FastAPI — IT Helpdesk Assistant.

Alur endpoint utama:
  1. Menerima pertanyaan/permintaan dari user
  2. Meneruskan ke router (router.py) untuk menentukan intent
  3. Router memanggil RAG (rag.py) atau tool (tools.py) sesuai intent
  4. Mengembalikan response terstruktur ke client
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.rag import build_index
from app.router import handle_query


@asynccontextmanager
async def lifespan(app: FastAPI):
    build_index()  # bangun index FAISS sekali saat startup
    yield


app = FastAPI(title="IT Helpdesk Assistant API", lifespan=lifespan)


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    status: str
    intent: str
    data: str


@app.get("/health")
async def health():
    """Endpoint sederhana untuk memastikan service berjalan."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Endpoint utama. Menerima pertanyaan bebas dari user (bisa berupa
    pertanyaan informasi/kebijakan ATAU permintaan cek status tiket),
    lalu meneruskannya ke router untuk diproses.

    Error handling: query kosong -> 400, LLM/embedding gagal -> 503.
    Intent tidak dikenali ditangani router (status "error", intent "unknown").
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query tidak boleh kosong.")
    try:
        result = await handle_query(request.query)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Layanan AI gagal merespons: {e}")
    return AskResponse(**result)
