"""
環境變數配置模組
支援從 .env 檔案和環境變數讀取設定，具備預設值
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Table, Text, Integer, Date, MetaData

# 載入環境變數
load_dotenv()
print("Loading .env environment variables...")

# RabbitMQ 設定
WORKER_ACCOUNT = os.getenv('WORKER_ACCOUNT', 'worker')
WORKER_PASSWORD = os.getenv('WORKER_PASSWORD', 'worker')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', '127.0.0.1')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))

# MySQL 設定
MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_ACCOUNT = os.getenv('MYSQL_ACCOUNT', 'root')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'test')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'mydb')

# PTT 爬蟲設定
PTT_BOARD = os.getenv('PTT_BOARD', 'Drink')
PTT_DELAY_MIN = float(os.getenv('PTT_DELAY_MIN', 0.5))
PTT_DELAY_MAX = float(os.getenv('PTT_DELAY_MAX', 1.5))
PTT_TIMEOUT = int(os.getenv('PTT_TIMEOUT', 10))

print(f"配置完成 - RabbitMQ: {RABBITMQ_HOST}:{RABBITMQ_PORT}, MySQL: {MYSQL_HOST}:{MYSQL_PORT}")


# ============================================================================
# 資料庫連接和表格結構（自動初始化模式）
# ============================================================================

# 建立資料庫連接和表格結構
address = f"mysql+pymysql://{MYSQL_ACCOUNT}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
engine = create_engine(address)
metadata = MetaData()

# PTT 文章資料表結構 - 使用複合主鍵 (board, aid)
ptt_articles_table = Table(
    "ptt_articles",
    metadata,
    Column("board", String(50), primary_key=True),  # 版名，複合主鍵之一
    Column("aid", String(20), primary_key=True),  # 文章編碼，複合主鍵之一
    Column("author", String(100)),  # 作者
    Column("title", String(500)),  # 標題
    Column("category", String(100)),  # 分類
    Column("content", Text),  # 內文
    Column("date", String(100)),  # 日期（原始格式）
    Column("ip", String(50)),  # IP位置
    Column("pushes_all", Integer),  # 總留言數
    Column("pushes_like", Integer),  # 推
    Column("pushes_boo", Integer),  # 噓
    Column("pushes_neutral", Integer),  # 中立
    Column("pushes_score", Integer),  # 文章分數
    Column("url", String(200)),  # 文章 URL
    Column("crawl_time", Date),  # 爬取時間
)

# 自動初始化：在模組載入時就完成資料表初始化
# 避免多 Worker 競爭建立資料表
print("🛠️  正在初始化 PTT 文章資料表...")
metadata.create_all(engine)
print("✅ PTT 文章資料表初始化完成（自動初始化模式）")
