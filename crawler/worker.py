"""
Celery 應用程式配置
設定 RabbitMQ 連線和任務佇列
"""
from celery import Celery
from crawler.config import WORKER_ACCOUNT, WORKER_PASSWORD, RABBITMQ_HOST, RABBITMQ_PORT

# 建立 Celery 應用程式
app = Celery('ptt_crawler')

# Celery 配置
app.conf.update(
    # RabbitMQ 連線設定
    broker_url=f'amqp://{WORKER_ACCOUNT}:{WORKER_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}//',
    result_backend=None,  # 不需要結果後端
    
    # 任務設定
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Taipei',
    enable_utc=True,
    
    # 任務路由設定
    task_routes={
        'crawler.tasks_ptt_crawler.crawl_ptt_page_task': {'queue': 'ptt'},
        'crawler.tasks_ptt_crawler.crawl_ptt_recent_pages_task': {'queue': 'ptt'},
        'crawler.tasks_ptt_crawler.crawl_single_article_task': {'queue': 'ptt'},
    },
    
    # Worker 設定
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
)

# 導入任務模組，確保任務被註冊
from crawler import tasks_ptt_crawler

print(f"Celery 應用程式已初始化 - Broker: {RABBITMQ_HOST}:{RABBITMQ_PORT}")
print(f"已註冊任務: {list(app.tasks.keys())}")
