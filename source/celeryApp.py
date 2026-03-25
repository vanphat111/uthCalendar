# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# celery.py

from celery import Celery
import os

REDIS_URL = os.getenv('CELERY_BROKER_URL', 'redis://uth_redis:6379/0')

app = Celery('uth_bot', broker=REDIS_URL, backend=REDIS_URL)

app.conf.update(
    task_serializer='json',
    timezone='Asia/Ho_Chi_Minh',
    enable_utc=True,
    task_routes={
        'tasks.portalTask': {'queue': 'high_priority'},
        'tasks.deadlineTask': {'queue': 'high_priority'},
        'tasks.registrationTask': {'queue': 'high_priority'},
        'tasks.systemStatusTask': {'queue': 'high_priority'},
        
        'tasks.periodicPortalTask': {'queue': 'low_priority'},
        'tasks.periodicCourseTask': {'queue': 'low_priority'},
    }
)