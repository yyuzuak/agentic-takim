# Build context = repo kökü
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY services/observer/ /app/
RUN pip install .

# v1.3: Observer — sidecar analytics plane, read-only DB consumer
EXPOSE 8002
CMD ["uvicorn", "observer.api:app", "--host", "0.0.0.0", "--port", "8002"]
