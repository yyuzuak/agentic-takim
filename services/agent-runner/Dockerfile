# Build context = repo kökü
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY packages/schemas /tmp/schemas
RUN pip install /tmp/schemas

COPY services/agent-runner/ /app/
RUN pip install .

CMD ["python", "-m", "runner.main"]
