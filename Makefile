.PHONY: help dev up down build logs clean proto test lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Development ─────────────────────────────────────────────────────────────

dev: ## Start all services in development mode
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Build all services
	docker compose build

logs: ## Tail logs for all services
	docker compose logs -f

logs-%: ## Tail logs for a specific service (e.g., make logs-stt-service)
	docker compose logs -f $*

restart-%: ## Restart a specific service (e.g., make restart-llm-agent)
	docker compose restart $*

# ─── Proto Generation ────────────────────────────────────────────────────────

proto: ## Generate gRPC stubs from proto files
	bash tools/generate-proto.sh

# ─── Testing ─────────────────────────────────────────────────────────────────

test: ## Run all tests
	@echo "Running Python tests..."
	cd shared/python && python -m pytest tests/ -v
	@for svc in audio-gateway stt-service llm-agent tool-orchestrator tts-service session-manager; do \
		echo "Testing $$svc..."; \
		cd services/$$svc && python -m pytest tests/ -v && cd ../..; \
	done
	@echo "Running Node.js tests..."
	@for svc in api-gateway appointment-scheduler patient-memory campaign-engine; do \
		echo "Testing $$svc..."; \
		cd services/$$svc && npm test && cd ../..; \
	done

test-%: ## Run tests for a specific service (e.g., make test-llm-agent)
	@if [ -f services/$*/requirements.txt ]; then \
		cd services/$* && python -m pytest tests/ -v; \
	else \
		cd services/$* && npm test; \
	fi

test-integration: ## Run integration tests
	python -m pytest tests/integration/ -v

test-load: ## Run k6 load tests
	bash infrastructure/scripts/load-test.sh

# ─── Linting ─────────────────────────────────────────────────────────────────

lint: ## Lint all services
	@echo "Linting Python..."
	ruff check services/audio-gateway services/stt-service services/llm-agent services/tool-orchestrator services/tts-service services/session-manager shared/python
	@echo "Linting TypeScript..."
	@for svc in api-gateway appointment-scheduler patient-memory campaign-engine; do \
		cd services/$$svc && npx eslint src/ && cd ../..; \
	done

# ─── Database ────────────────────────────────────────────────────────────────

db-seed: ## Seed database with sample data
	docker compose exec mongodb mongosh clinic_db /docker-entrypoint-initdb.d/seed.js

db-backup: ## Backup MongoDB
	bash infrastructure/scripts/backup-db.sh

# ─── Utilities ───────────────────────────────────────────────────────────────

clean: ## Remove all containers, volumes, and build artifacts
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true

status: ## Show status of all services
	docker compose ps

health: ## Check health of all services
	@echo "API Gateway:"; curl -s http://localhost:3000/health | python3 -m json.tool 2>/dev/null || echo "DOWN"
	@echo "Audio Gateway:"; curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "DOWN"
	@echo "LLM Agent:"; curl -s http://localhost:8090/health | python3 -m json.tool 2>/dev/null || echo "DOWN"
	@echo "Session Manager:"; curl -s http://localhost:6380/health | python3 -m json.tool 2>/dev/null || echo "DOWN"
	@echo "Appointment Scheduler:"; curl -s http://localhost:3010/health | python3 -m json.tool 2>/dev/null || echo "DOWN"
	@echo "Patient Memory:"; curl -s http://localhost:3020/health | python3 -m json.tool 2>/dev/null || echo "DOWN"
	@echo "Campaign Engine:"; curl -s http://localhost:3030/health | python3 -m json.tool 2>/dev/null || echo "DOWN"

setup: ## One-time setup for local development
	bash tools/dev-setup.sh
