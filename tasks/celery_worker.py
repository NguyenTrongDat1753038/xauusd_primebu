# d:\Code\XAU_Bot_Predict\tasks\celery_worker.py
import os
from celery import Celery

# Cấu hình từ environment variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))

# Kết nối đến Redis (hỗ trợ cả Docker và localhost)
BROKER_URL = os.environ.get('CELERY_BROKER_URL', f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}')
RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB + 1}')

celery_app = Celery(
    'tasks',
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=['tasks.bot_tasks']
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
