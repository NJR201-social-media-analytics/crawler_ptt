"""
環境變數配置模組
支援從 .env 檔案和環境變數讀取設定，具備預設值
"""
import os
from dotenv import load_dotenv

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
