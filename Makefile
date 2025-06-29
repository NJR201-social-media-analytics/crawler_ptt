# 分散式 PTT 爬蟲系統 Makefile

.PHONY: help check-uv setup start stop worker producer logs clean status

# 預設目標
.DEFAULT_GOAL := help

# Docker 映像檔版本
DOCKER_IMAGE_VERSION ?= latest

help: ## 顯示可用的指令
	@echo "🚀 分散式 PTT 爬蟲系統"
	@echo ""
	@echo "可用指令："
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

check-uv: ## 檢查 uv 是否已安裝
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "❌ uv 未安裝！"; \
		echo ""; \
		echo "📦 uv 安裝指引："; \
		echo ""; \
		echo "🍎 macOS (推薦):"; \
		echo "  brew install uv"; \
		echo ""; \
		echo "🌐 官方安裝腳本 (macOS/Linux):"; \
		echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo ""; \
		echo "🪟 Windows:"; \
		echo "  winget install --id=astral-sh.uv -e"; \
		echo ""; \
		echo "🐧 Linux:"; \
		echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo ""; \
		echo "💡 安裝完成後執行 'make setup' 繼續設定環境"; \
		exit 1; \
	else \
		echo "✅ uv 已安裝: $$(uv --version)"; \
	fi

setup: check-uv ## 安裝依賴並初始化環境
	@echo "📦 設定環境..."
	@echo "📦 安裝 Python 依賴..."
	uv sync
	@echo "⚙️  設定環境變數..."
	ENV=DOCKER python genenv.py
	@echo "✅ 環境設定完成！"

build: ## 建立 Docker 映像檔
	@echo "🔨 建立 PTT 爬蟲 Docker 映像檔..."
	docker build -f with.env.Dockerfile -t ptt_crawler:$(DOCKER_IMAGE_VERSION) .

start: build ## 啟動基礎服務 (MySQL, RabbitMQ, Flower, phpMyAdmin)
	@echo "🚀 啟動分散式 PTT 爬蟲系統基礎服務..."
	@echo "🗄️  啟動 MySQL 資料庫..."
	docker compose -f mysql.yml up -d
	@echo "🐰 啟動 RabbitMQ 和 Flower..."
	docker compose -f rabbitmq-network.yml up -d
	@echo "⏳ 等待服務啟動完成..."
	sleep 10
	@echo ""
	@echo "✅ 基礎服務啟動完成！"
	@echo ""
	@echo "📊 監控介面："
	@echo "- RabbitMQ 管理: http://127.0.0.1:15672/ (worker/worker)"
	@echo "- Flower 監控:   http://127.0.0.1:5555/"
	@echo "- phpMyAdmin:    http://127.0.0.1:8000/ (root/test)"
	@echo ""
	@echo "🚀 接下來請執行："
	@echo "  make worker    # 啟動 PTT Worker"
	@echo "  make producer  # 發送爬蟲任務"

worker: ## 啟動 PTT Worker
	@echo "👷 啟動 PTT 爬蟲 Worker..."
	DOCKER_IMAGE_VERSION=$(DOCKER_IMAGE_VERSION) docker compose -f docker-compose-worker-network-version.yml up -d
	@echo "✅ Worker 啟動完成！"

producer: ## 發送爬蟲任務
	@echo "📤 發送 PTT 爬蟲任務..."
	DOCKER_IMAGE_VERSION=$(DOCKER_IMAGE_VERSION) docker compose -f docker-compose-producer-duplicate-network-version.yml up

producer-local: ## 本地發送爬蟲任務 (不使用 Docker)
	@echo "📤 本地發送 PTT 爬蟲任務..."
	uv run python crawler/producer_ptt_crawler.py

stop: ## 停止所有服務
	@echo "🛑 停止分散式 PTT 爬蟲系統..."
	@echo "📤 停止 Producer 服務..."
	-DOCKER_IMAGE_VERSION=$(DOCKER_IMAGE_VERSION) docker compose -f docker-compose-producer-duplicate-network-version.yml down 2>/dev/null
	@echo "👷 停止 Worker 服務..."
	-DOCKER_IMAGE_VERSION=$(DOCKER_IMAGE_VERSION) docker compose -f docker-compose-worker-network-version.yml down
	@echo "🐰 停止 RabbitMQ 和 Flower..."
	-docker compose -f rabbitmq-network.yml down
	@echo "🗄️  停止 MySQL 資料庫..."
	-docker compose -f mysql.yml down
	@echo "✅ 所有服務已停止！"

logs: ## 查看 Worker 日誌
	@echo "📋 查看 PTT Worker 日誌..."
	docker logs crawler_ptt-crawler_ptt-1

logs-producer: ## 查看 Producer 日誌
	@echo "📋 查看 Producer 日誌..."
	docker logs crawler_ptt-producer_ptt_crawler-1

status: ## 查看服務狀態
	@echo "📊 查看容器狀態..."
	docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

clean: stop ## 清理所有容器和映像檔
	@echo "🧹 清理 Docker 資源..."
	-docker rmi ptt_crawler:$(DOCKER_IMAGE_VERSION)
	-docker system prune -f
	@echo "✅ 清理完成！"

dev: ## 開發模式：格式化程式碼並檢查
	@echo "🔧 執行開發工具..."
	uv run black .
	uv run flake8 .
	@echo "✅ 程式碼檢查完成！"

all: setup start worker producer ## 一鍵完整啟動 (設定環境 + 啟動服務 + Worker + 任務)
