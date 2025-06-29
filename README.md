# 分散式 PTT 爬蟲系統

## 📋 專案說明

這是一個使用 Docker + RabbitMQ + Celery + MySQL 的分散式 PTT 爬蟲系統，專門爬取 PTT Drink 版文章資料。

### ✨ 主要特色

- ✅ **分散式處理**: 支援多個 Worker 同時處理 PTT 爬蟲任務
- ✅ **自動去重**: 使用 MySQL 的 `ON DUPLICATE KEY UPDATE` 避免重複資料
- ✅ **智能爬取**: 支援按日期篩選，自動爬取近30天的文章
- ✅ **容器化部署**: 使用 Docker 容器化所有服務
- ✅ **Apple Silicon 支援**: 支援 M1/M2 Mac
- ✅ **文章內容完整**: 爬取標題、內文、推文、作者等完整資訊
- ✅ **現代套件管理**: 使用 uv 進行快速且可靠的依賴管理
- ✅ **監控介面**: 提供 Flower、phpMyAdmin、RabbitMQ 管理介面

### 🔧 問題解決狀況

- ✅ **推文數據**: 推文解析邏輯已優化，正確抓取推文數據
- ✅ **爬取數量**: 停止條件已放寬，確保爬取足夠文章數量
- ✅ **連線問題**: Docker 網路配置已優化，解決服務間連線問題

## 🚀 快速開始

### 📦 步驟 1：安裝 uv

**⚠️ 重要：本專案使用 `uv` 作為 Python 套件管理工具，請先確保已安裝**

#### 🍎 macOS (推薦)
```bash
brew install uv
```

#### 🌐 官方安裝腳本 (macOS/Linux)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### 🪟 Windows
```bash
# 使用 winget (推薦)
winget install --id=astral-sh.uv -e

# 或使用 pip
pip install uv
```

#### 🐧 Linux
```bash
# 官方腳本 (推薦)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip
pip install uv
```

#### 驗證安裝
```bash
uv --version
```

### ⚡ 步驟 2：一鍵啟動系統

```bash
# 1. 進入專案目錄
cd crawler_ptt

# 2. 查看所有可用指令
make help

# 3. 一鍵完整啟動 (設定環境 + 啟動服務 + Worker + 任務)
make all
```

### 🔧 或者分步驟執行

```bash
# 1. 設定環境 (會自動檢查 uv 是否安裝)
make setup

# 2. 啟動基礎服務
make start

# 3. 啟動 Worker
make worker

# 4. 發送爬蟲任務
make producer

# 5. 停止所有服務
make stop
```

### 🔧 進階：手動逐步操作

**💡 注意：以下步驟假設您已經安裝了 uv，如需協助請參考上方的 uv 安裝指引**

#### 1. 環境設定

```bash
# 建立虛擬環境並安裝依賴
uv venv
uv sync

# 設定環境變數（可選，有預設值）
ENV=DOCKER python genenv.py
```

#### 2. 啟動基礎服務

```bash
# 建立 Docker 網路
docker network create my_network

# 啟動 MySQL 資料庫 + phpMyAdmin
docker compose -f mysql.yml up -d

# 啟動 RabbitMQ + Flower
docker compose -f rabbitmq-network.yml up -d
```

#### 3. 建立 Docker 映像檔

```bash
# 建立映像檔
docker build -f with.env.Dockerfile -t ptt_crawler:latest .
```

#### 4. 啟動 Worker 服務

```bash
# 啟動 PTT Worker
DOCKER_IMAGE_VERSION=latest docker compose -f docker-compose-worker-network-version.yml up -d
```

#### 5. 發送爬蟲任務

```bash
# 推薦：使用 Docker 容器發送任務
DOCKER_IMAGE_VERSION=latest docker compose -f docker-compose-producer-duplicate-network-version.yml up

# 替代方法：本地發送任務（需要先設定環境變數）
uv run python crawler/producer_ptt_crawler.py
```

## 🎯 常用操作指令

### 使用 Makefile
```bash
# 查看所有可用指令
make help

# 檢查 uv 是否已安裝
make check-uv

# 啟動服務流程
make setup     # 設定環境
make start     # 啟動基礎服務
make worker    # 啟動 PTT Worker
make producer  # 發送爬蟲任務

# 一鍵完整啟動
make all

# 檢查狀態
make status    # 查看容器狀態
make logs      # 查看 Worker 日誌

# 停止服務
make stop      # 停止所有服務
make clean     # 停止並清理資源
```

### 檢查狀態
```bash
# 查看所有容器狀態
docker ps
# 或使用 make
make status

# 查看 Worker 日誌
docker logs crawler_ptt-crawler_ptt-1
# 或使用 make
make logs

# 查看 Producer 日誌 (如果還在運行)
docker logs crawler_ptt-producer_ptt_crawler-1
# 或使用 make
make logs-producer
```

### 停止服務
```bash
# 停止所有服務
make stop

# 只停止 Worker
DOCKER_IMAGE_VERSION=latest docker compose -f docker-compose-worker-network-version.yml down

# 只停止 Producer
DOCKER_IMAGE_VERSION=latest docker compose -f docker-compose-producer-duplicate-network-version.yml down
```

## 🖥️ 監控介面

系統提供多個監控介面：

| 服務 | URL | 說明 | 登入資訊 |
|------|-----|------|----------|
| **Flower** | http://localhost:5555 | Celery 任務監控 | 無需登入 |
| **phpMyAdmin** | http://localhost:8000 | 資料庫管理 | root / test |
| **RabbitMQ Management** | http://localhost:15672 | 訊息佇列管理 | worker / worker |

## 🔍 檢查執行結果

### 1. 查看服務狀態
```bash
# 檢查所有容器是否正常運行
docker ps

# 應該看到以下 5 個容器都處於 "Up" 狀態：
# - crawler_ptt-crawler_ptt-1 (Worker)
# - crawler_ptt-phpmyadmin-1 (phpMyAdmin)
# - crawler_ptt-mysql-1 (MySQL)
# - crawler_ptt-flower-1 (Flower)
# - crawler_ptt-rabbitmq-1 (RabbitMQ)
```

### 2. 查看 Worker 日誌
```bash
# 查看 PTT Worker 日誌
docker logs crawler_ptt-crawler_ptt-1

# 成功運行時應該看到：
# 🌟 開始爬取 Drink 版近 30 天的文章（無頁數限制，直到找到所有指定天數內的文章）
# 正在抓資料中...[標題]...
# ✅ 推文數據: 總 X, 推 X, 噓 X
# 準備上傳 X 筆 PTT 文章資料到 MySQL...
# 成功處理 X 筆 PTT 文章資料（新增或更新）
# ✅ 批量爬取完成：Drink 版，處理 X 頁，找到 X 篇文章，上傳 X 筆
```

### 3. 查看資料庫
1. 訪問 http://localhost:8000/
2. 登入 phpMyAdmin (root/test)
3. 選擇 `mydb` 資料庫
4. 查看 `ptt_articles` 資料表

## 📁 專案結構

```
crawler_ptt/
├── Makefile                                  # 任務管理檔案 (推薦使用)
├── pyproject.toml                            # uv 專案設定與依賴管理
├── uv.lock                                   # 依賴鎖定檔案
├── genenv.py                                 # 環境變數生成器
├── local.ini                                 # 環境配置
├── crawler/                                  # 分散式爬蟲套件
│   ├── __init__.py
│   ├── config.py                            # 環境變數配置
│   ├── worker.py                            # Celery 應用程式
│   ├── tasks_ptt_crawler.py                # PTT 爬蟲任務
│   └── producer_ptt_crawler.py             # 任務發送器
├── docker-compose-worker-network-version.yml  # Worker 服務
├── docker-compose-producer-duplicate-network-version.yml  # Producer 服務
├── rabbitmq-network.yml                     # RabbitMQ + Flower
├── mysql.yml                                # MySQL + phpMyAdmin
├── Dockerfile                               # Docker 映像檔建構
├── with.env.Dockerfile                      # 含環境變數的映像檔
├── data/                                    # 資料儲存目錄
│   ├── ptt_Drink_YYYYMMDD_HHMMSS.csv      # 備份資料檔案
│   └── ptt_Drink_latest.csv               # 最新資料檔案
└── errors/                                  # 錯誤記錄目錄
    └── Drink/
        └── page_errors.log                  # 頁面錯誤記錄
```

## 📊 資料庫結構

### ptt_articles 資料表結構
```sql
CREATE TABLE ptt_articles (
    aid VARCHAR(20) PRIMARY KEY,     -- 文章編碼
    board VARCHAR(50),               -- 版名 (固定為 Drink)
    author VARCHAR(100),             -- 作者
    title VARCHAR(500),              -- 標題
    category VARCHAR(100),           -- 分類 ([問題]、[心得] 等)
    content TEXT,                    -- 內文
    date VARCHAR(100),               -- 發文日期
    ip VARCHAR(50),                  -- IP位置
    pushes_all INT,                  -- 總推文數
    pushes_like INT,                 -- 推
    pushes_boo INT,                  -- 噓
    pushes_neutral INT,              -- 中立
    pushes_score INT,                -- 文章分數 (推-噓)
    url VARCHAR(200),                -- 文章 URL
    crawl_time DATE                  -- 爬取時間
);
```

## 🎯 使用範例

```bash
$ make all
📦 設定環境...
✅ uv 已安裝
📦 安裝 Python 依賴...
⚙️  設定環境變數...
✅ 環境設定完成！
🔨 建立 PTT 爬蟲 Docker 映像檔...
🚀 啟動分散式 PTT 爬蟲系統基礎服務...
👷 啟動 PTT 爬蟲 Worker...
📤 發送 PTT 爬蟲任務...

# Worker 日誌顯示：
🌟 開始爬取 Drink 版近 30 天的文章（無頁數限制，直到找到所有指定天數內的文章）
正在抓資料中...[問題] 請問大家最近有喝到什麼好喝的飲料嗎？
✅ 推文數據: 總 15, 推 12, 噓 1
準備上傳 20 筆 PTT 文章資料到 MySQL...
成功處理 20 筆 PTT 文章資料（新增或更新）
✅ 批量爬取完成：Drink 版，處理 5 頁，找到 98 篇文章，上傳 98 筆
```

## 📊 輸出資料格式

### MySQL 資料表結構
爬取的資料會儲存到 MySQL 資料庫中，包含以下欄位：

| 欄位名稱 | 說明 | 範例 |
|---------|------|------|
| 標題 | 文章標題 | [情報] 星巴克新飲品上市 |
| 作者 | 作者 | username123 |
| 版名 | 版面名稱 | Drink |
| 日期 | 發文時間 | Mon Jan 15 14:30:25 2024 |
| 內文 | 文章內容 | 今天發現星巴克... |
| 文章編碼 | 文章唯一編碼 | M.1640420425.A.123 |
| 分類 | 文章分類 | [情報] |
| IP位置 | 發文者IP | 123.456.789.123 |
| 總留言數 | 推文總數 | 25 |
| 推 | 推文數 | 20 |
| 噓 | 噓文數 | 3 |
| 中立 | 中立推文數 | 2 |
| 文章分數（正-負） | 推噓分數 | 17 |
| 所有留言 | 完整推文內容 | 推 user1: 讚...|

### 分散式版本 (MySQL)
資料會直接儲存到 MySQL 資料庫的 `ptt_articles` 資料表中，欄位包括：
- `aid`: 文章編碼 (主鍵)
- `board`: 版名
- `author`: 作者
- `title`: 標題
- `category`: 分類
- `content`: 內文
- `date`: 發文日期
- `ip`: IP位置
- `pushes_all/like/boo/neutral/score`: 推文統計
- `url`: 文章 URL
- `crawl_time`: 爬取時間

## 🛠️ 環境需求

- **Python**: 3.8+ (推薦 3.10+)
- **套件管理**: uv (推薦)
- **Docker**: 用於分散式部署
- **依賴管理**: 使用 `pyproject.toml` 管理依賴套件

### 主要依賴套件
- `requests`: HTTP 請求
- `beautifulsoup4`: HTML 解析
- `pandas`: 資料處理
- `fake-useragent`: 請求偽裝
- `celery`: 分散式任務處理
- `pymysql`: MySQL 連接
- `sqlalchemy`: 資料庫 ORM

### 環境變數配置

系統會從 `.env` 檔案讀取以下環境變數：

```bash
WORKER_ACCOUNT=worker
WORKER_PASSWORD=worker
RABBITMQ_HOST=127.0.0.1      # 本地環境，Docker 環境為 rabbitmq
RABBITMQ_PORT=5672
MYSQL_HOST=127.0.0.1         # 本地環境，Docker 環境為 mysql
MYSQL_PORT=3306
MYSQL_ACCOUNT=root
MYSQL_PASSWORD=test
MYSQL_DATABASE=mydb
PTT_BOARD=Drink
PTT_DELAY_MIN=0.5            # 爬蟲延遲最小值（秒）
PTT_DELAY_MAX=1.5            # 爬蟲延遲最大值（秒）
PTT_TIMEOUT=10               # 連線逾時（秒）
```

## 🔧 故障排除

### 常見問題 1: Producer 連線失敗 "Connection refused"
**問題**: Producer 容器無法連接 RabbitMQ/MySQL  
**解決方法**: 確保 Docker Compose 檔案中包含正確的環境變數設定：
```yaml
environment:
  - TZ=Asia/Taipei
  - RABBITMQ_HOST=rabbitmq  # 在 Docker 網路中使用服務名稱
  - MYSQL_HOST=mysql        # 在 Docker 網路中使用服務名稱
```

### 常見問題 2: ARM64 相容性錯誤
**問題**: `no matching manifest for linux/arm64/v8 in the manifest list entries`  
**解決方案**: 所有 Docker Compose 檔案已加入 `platform: linux/amd64` 設定

### 常見問題 3: RabbitMQ 連線失敗
**問題**: `ACCESS_REFUSED - Login was refused using authentication mechanism PLAIN`  
**解決方案**: 
1. 確認 RabbitMQ 服務已啟動
2. 檢查環境變數設定
3. 等待 RabbitMQ 完全啟動後再發送任務

### 常見問題 4: Docker 映像檔未更新
**問題**: 修改程式碼後，Docker 容器仍使用舊版本  
**解決方法**: 
```bash
# 強制重建映像檔（忽略快取）
docker build -f with.env.Dockerfile -t ptt_crawler:latest . --no-cache

# 重新啟動容器
docker compose -f docker-compose-worker-network-version.yml down
docker compose -f docker-compose-worker-network-version.yml up -d --force-recreate
```

## ⚠️ 注意事項

1. **合理使用**: 請適度使用，避免過度頻繁的請求
2. **遵守規範**: 請遵守 PTT 的使用規範
3. **網路穩定**: 建議在穩定的網路環境下使用
4. **自動化爬取**: 程式會自動爬取近30天的文章，無需手動輸入
5. **智能延遲**: 系統會自動在請求間加入隨機延遲 (0.5-1.5 秒)
6. **自動去重**: 分散式版本會自動處理重複資料

## 🔄 系統特色

### 分散式架構優勢
- **高可用性**: 支援多個 Worker 同時處理任務
- **自動重試**: 失敗任務會自動重新排程
- **監控完整**: 提供多個監控介面追蹤系統狀態
- **擴展性強**: 可輕鬆增加 Worker 節點提升處理能力

### PTT 爬蟲特色
- **智能延遲**: 隨機延遲避免過度請求
- **日期篩選**: 支援只爬取近 N 天的文章
- **錯誤處理**: 自動跳過已刪除或無法存取的文章
- **完整資料**: 爬取標題、內文、推文統計、分類等
- **User-Agent 輪換**: 使用 fake-useragent 避免封鎖

## 🛠️ 自訂設定

### 更改爬取版面
修改 `local.ini` 中的 `PTT_BOARD` 設定：
```ini
PTT_BOARD = Tech_Job  # 改為其他版面
```

### 調整爬取參數
修改 `crawler/producer_ptt_crawler.py`：
```python
result = send_recent_pages_task(
    board_name='Drink',
    target_days=7,    # 爬取近 7 天
    max_pages=None    # 無頁數限制（推薦）或設定數字如 50
)
```

### 開發與測試
```bash
# 使用 Makefile (推薦)
make dev               # 格式化程式碼並檢查風格
make producer-local    # 本地測試 (不使用 Docker)

# 或使用 uv 直接執行
uv run black .          # 格式化程式碼
uv run flake8 .         # 檢查程式碼風格
uv run pytest          # 執行測試
uv run python crawler/producer_ptt_crawler.py  # 本地測試
```

## 🐛 常見問題

### Q: 爬取過程中出現錯誤怎麼辦？
A: 使用 `docker logs crawler_ptt-crawler_ptt-1` 查看 Worker 日誌，或檢查 `errors/Drink/page_errors.log` 查看詳細錯誤訊息

### Q: 可以修改爬取的天數嗎？
A: 在 `crawler/producer_ptt_crawler.py` 中修改 `target_days` 參數

### Q: 可以爬取其他版面嗎？
A: 修改 `local.ini` 中的 `PTT_BOARD` 設定，或在程式中直接指定版面名稱

### Q: 資料儲存在哪裡？
A: 儲存在 MySQL 資料庫的 `ptt_articles` 資料表，並同時備份到 `data/` 目錄下的 CSV 檔案

### Q: 如何查看爬取結果？
A: 訪問 http://localhost:8000/ 使用 phpMyAdmin 查看資料庫，或直接開啟 `data/` 目錄下的 CSV 檔案

### Q: 系統會重複爬取相同文章嗎？
A: 使用 MySQL 自動去重機制，不會產生重複資料

### Q: 如何停止正在運行的爬蟲？
A: 執行 `make stop` 停止所有服務

### Q: 推文數據顯示為 0 怎麼辦？
A: 這個問題已在分散式版本中修正，如果仍遇到問題請檢查 Worker 日誌

## 🚀 版本說明

**v1.0.0 特色**:
- ✅ 分散式架構爬蟲系統
- ✅ 完整的 PTT 爬蟲功能
- ✅ 分散式架構部署
- ✅ 自動去重機制
- ✅ Docker 容器化部署
- ✅ Apple Silicon Mac 支援
- ✅ 一鍵啟動腳本
- ✅ 完整的監控介面
- ✅ 使用 uv 進行現代化套件管理
- ✅ 智能爬取與錯誤處理優化
