"""
Modul Tools — fungsi-fungsi "aksi" yang dipanggil router ketika intent
BUKAN pertanyaan informasi/kebijakan, melainkan permintaan spesifik
yang butuh pengecekan data langsung (bukan retrieval semantik).

Pola ini mengikuti konsep Tool Integration di Sesi 12.3.
"""

import pandas as pd

MOCK_TICKETS_PATH = "data/mock_tickets.csv"


def get_ticket_status(ticket_id: str) -> str:
    """
    Mencari status tiket berdasarkan ticket_id pada data mock_tickets.csv.
    Tidak pernah raise: tiket tidak ada / data tidak terbaca -> pesan informatif.
    """
    try:
        df = pd.read_csv(MOCK_TICKETS_PATH)
    except Exception:
        return "Maaf, data tiket sedang tidak dapat diakses. Silakan coba lagi nanti."

    ticket_id = (ticket_id or "").strip().upper()
    row = df[df["ticket_id"].str.upper() == ticket_id]
    if row.empty:
        return (
            f"Tiket {ticket_id} tidak ditemukan. "
            "Pastikan ID tiket benar (format TICKET-XXXX)."
        )

    t = row.iloc[0]
    return (
        f"Tiket {t['ticket_id']} ({t['subject']}) berstatus '{t['status']}'. "
        f"Kategori: {t['category']}, pemohon: {t['employee_name']}, "
        f"update terakhir: {t['last_update']}."
    )
