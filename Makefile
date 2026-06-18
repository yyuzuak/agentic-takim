# Agentic Takım — geliştirme komutları
# Kullanım: `make setup` (core) | `make setup-full` (tüm profiller)

SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml --env-file .env
CORE_PROFILES := --profile core
FULL_PROFILES := --profile core --profile ai --profile memory --profile observability

.DEFAULT_GOAL := help

.PHONY: help doctor env setup setup-full up up-full down reset logs migrate seed init-nats init-qdrant validate test

help: ## Komutları listele
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

doctor: ## Ön-koşulları kontrol et (docker, node, python, pnpm, uv)
	@bash scripts/bootstrap.sh doctor

env: ## .env yoksa .env.example'dan oluştur
	@if [ ! -f .env ]; then cp .env.example .env && echo "✓ .env oluşturuldu (.env.example'dan)"; else echo "• .env zaten var"; fi

setup: ## Core profili kur (postgres, redis, nats, control-plane, agent-runner, worker, web)
	@bash scripts/bootstrap.sh setup core

setup-full: ## Tüm profilleri kur (core + ai + memory + observability)
	@bash scripts/bootstrap.sh setup full

up: ## Core servisleri başlat (kurulu varsayar)
	$(COMPOSE) $(CORE_PROFILES) up -d

up-full: ## Tüm servisleri başlat
	$(COMPOSE) $(FULL_PROFILES) up -d

down: ## Tüm servisleri durdur
	$(COMPOSE) $(FULL_PROFILES) down

reset: ## Her şeyi durdur ve volume'leri sil (sıfırdan kurulum için)
	$(COMPOSE) $(FULL_PROFILES) down -v
	@echo "✓ Sıfırlandı. 'make setup' ile yeniden kurabilirsiniz."

logs: ## Servis loglarını takip et (örn. make logs S=control-plane)
	$(COMPOSE) $(FULL_PROFILES) logs -f $(S)

migrate: ## Veritabanı migration'larını uygula
	$(COMPOSE) exec control-plane alembic upgrade head

seed: ## Registry'yi (agents/skills) ve örnek veriyi yükle
	$(COMPOSE) exec control-plane python -m app.seed

init-nats: ## ACP JetStream stream'lerini oluştur
	@bash scripts/init-nats.sh

init-qdrant: ## Qdrant collection'ını oluştur (memory profili)
	@bash scripts/init-qdrant.sh

validate: ## Şema + agent registry doğrulaması (CI ile aynı)
	$(COMPOSE) exec control-plane python -m app.validate

test: ## Testleri çalıştır
	$(COMPOSE) exec control-plane pytest -q
