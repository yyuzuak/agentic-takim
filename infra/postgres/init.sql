-- Tek Postgres instance, iki database.
-- agentic_os: ana uygulama (control-plane, agent-runner checkpointer).
-- langfuse:   observability profili (Langfuse).
-- agentic_os, POSTGRES_DB env'i ile zaten oluşturulur; langfuse'ü burada ekliyoruz.

SELECT 'CREATE DATABASE langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
