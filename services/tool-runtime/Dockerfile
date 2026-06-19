# Build context = repo kökü
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY packages/schemas /tmp/schemas
RUN pip install /tmp/schemas

COPY services/tool-runtime/ /app/
RUN pip install .

# Tool kataloğu
COPY config /app/config

# v1.1-b: HTTP API + NATS consumer birlikte (api.py lifespan → main.run())
EXPOSE 8001
CMD ["uvicorn", "toolrt.api:app", "--host", "0.0.0.0", "--port", "8001"]
