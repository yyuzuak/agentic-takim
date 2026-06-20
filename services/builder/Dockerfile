# Build context = repo kökü
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY services/builder/ /app/
RUN pip install .

# Stack scaffold şablonları (assembler bunları kullanır)
COPY config /app/config

# v2.1: Builder — assemble + validate + persist (exec YOK; sandbox v2.2 ayrı servis)
EXPOSE 8003
CMD ["uvicorn", "builder.api:app", "--host", "0.0.0.0", "--port", "8003"]
