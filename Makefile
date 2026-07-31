.PHONY: help install dev backend frontend build test lint docker

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend and frontend dependencies
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

backend:  ## Run the API with autoreload on :8000
	cd backend && uvicorn app.main:app --reload --port 8000

frontend: ## Run the Vite dev server on :5173
	cd frontend && npm run dev

build:    ## Build the SPA into backend/app/static
	cd frontend && npm run build

test:     ## Run the backend test suite
	cd backend && python -m pytest -q

lint:     ## Type-check the frontend
	cd frontend && npx tsc --noEmit

docker:   ## Build and start the docker compose stack
	docker compose up -d --build
