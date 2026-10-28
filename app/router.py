"""
Router — menentukan apakah query user butuh RAG (informasi/kebijakan)
atau tool call (aksi spesifik, misal cek status tiket).

Pola ini mengikuti workflow router yang sudah dipelajari di Sesi 12.4:
  user input -> intent detection -> jika butuh data -> retrieval (RAG)
                                  -> jika butuh aksi -> tool call
"""

import re

from app.rag import answer_from_knowledge_base
from app.tools import get_ticket_status

# Pendekatan keyword/regex (baseline): deterministik, cepat, tanpa biaya LLM.
# "ticket_status" jika query memuat ID tiket, ATAU menyebut tiket + kata cek status.
TICKET_ID_PATTERN = re.compile(r"\bticket[\s_-]*(\d{1,4})\b", re.IGNORECASE)
TICKET_WORDS = ("tiket", "ticket")
STATUS_WORDS = ("status", "cek", "periksa", "progres", "progress", "sudah sampai mana")


async def detect_intent(query: str) -> str:
    """
    Menentukan intent dari query user:
      - "ticket_status" -> memuat ID tiket (TICKET-XXXX), atau menyebut tiket + kata status/cek
      - "faq"           -> pertanyaan informasi/kebijakan, arahkan ke RAG
      - "unknown"       -> query kosong
    """
    q = query.lower().strip()
    if not q:
        return "unknown"
    if TICKET_ID_PATTERN.search(q):
        return "ticket_status"
    if any(w in q for w in TICKET_WORDS) and any(w in q for w in STATUS_WORDS):
        return "ticket_status"
    return "faq"


async def handle_query(query: str) -> dict:
    """
    Fungsi utama yang dipanggil oleh endpoint /ask.
    Menjalankan intent detection, lalu merutekan ke RAG atau tool call yang sesuai.
    """
    intent = await detect_intent(query)

    if intent == "ticket_status":
        ticket_id = extract_ticket_id(query)
        if ticket_id is None:
            return {
                "status": "success",
                "intent": "ticket_status",
                "data": "Mohon sebutkan ID tiket Anda (format TICKET-XXXX, contoh: TICKET-0042).",
            }
        data = get_ticket_status(ticket_id)
        return {"status": "success", "intent": "ticket_status", "data": data}

    elif intent == "faq":
        data = await answer_from_knowledge_base(query)
        return {"status": "success", "intent": "faq", "data": data}

    else:
        return {"status": "error", "intent": "unknown", "data": "Maaf, saya tidak memahami permintaan Anda."}


def extract_ticket_id(query: str) -> str | None:
    """
    Ekstrak ticket_id dari query dan normalisasi ke format 'TICKET-XXXX'
    (mis. 'ticket 42' -> 'TICKET-0042'). Mengembalikan None jika tidak ada ID.
    """
    match = TICKET_ID_PATTERN.search(query)
    if not match:
        return None
    return f"TICKET-{int(match.group(1)):04d}"
