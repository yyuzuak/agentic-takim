# Build context = repo kökü. node (npm/dev) + python (FastAPI).
FROM node:20-bookworm-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY services/preview/ /app/
RUN pip install --break-system-packages . && rm -rf /root/.cache

# Non-root — dev server LLM kodunu sandbox kullanıcısı altında koşar; yazma yalnız /tmp + home.
RUN useradd -m -u 1002 preview && mkdir -p /tmp/preview && chown -R preview:preview /tmp/preview /home/preview
USER preview
ENV HOME=/home/preview PREVIEW_TMP=/tmp/preview

EXPOSE 8005 3100
CMD ["uvicorn", "preview.api:app", "--host", "0.0.0.0", "--port", "8005"]
