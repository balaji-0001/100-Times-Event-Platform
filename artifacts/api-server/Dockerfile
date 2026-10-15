# Optional container build for the FastAPI backend. The native dev flow
# (py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000) remains
# the primary, documented way to run this locally — this Dockerfile exists
# so the backend CAN be run via `docker compose --profile full up` alongside
# n8n/Postgres, not as a replacement for the native flow.

FROM python:3.14-slim

WORKDIR /app

# Ensure curl/build tools if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PYTHONPATH=/app

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

