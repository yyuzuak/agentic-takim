# Build context = repo kökü (compose: context: ../..)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Paylaşılan şema paketi önce kurulur
COPY packages/schemas /tmp/schemas
RUN pip install /tmp/schemas

# Servis kodu + bağımlılıklar
COPY services/control-plane/ /app/
RUN pip install .

# Registry seed kaynağı
COPY config /app/config

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
