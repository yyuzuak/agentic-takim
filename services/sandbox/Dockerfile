# Build context = repo kökü. node (npm/npx) + python (FastAPI) tek imajda.
FROM node:20-bookworm-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

# Python + pip (FastAPI servisi için)
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY services/sandbox/ /app/
RUN pip install --break-system-packages . && rm -rf /root/.cache

# Non-root user — build subprocess'leri root değil sandbox kullanıcısı altında koşar.
# Yazma yalnız /tmp + /home/sandbox (workspace read-only mount).
RUN useradd -m -u 1001 sandbox && mkdir -p /tmp/run && chown -R sandbox:sandbox /tmp/run /home/sandbox
USER sandbox
ENV HOME=/home/sandbox SANDBOX_TMP=/tmp/run

EXPOSE 8004
CMD ["uvicorn", "sandbox.api:app", "--host", "0.0.0.0", "--port", "8004"]
