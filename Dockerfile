FROM python:3.11-slim

WORKDIR /app

# Copy requirements dulu agar layer install dependencies ter-cache
# selama requirements.txt tidak berubah.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code dan data (.env dikecualikan lewat .dockerignore)
COPY app/ app/
COPY data/ data/

EXPOSE 8000

# 0.0.0.0 agar bisa diakses dari luar container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
