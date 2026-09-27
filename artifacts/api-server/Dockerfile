# Optional container build for the FastAPI backend. The native dev flow
# (py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000) remains
# the primary, documented way to run this locally — this Dockerfile exists
# so the backend CAN be run via `docker compose --profile full up` alongside
# n8n/Postgres, not as a replacement for the native flow.

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
