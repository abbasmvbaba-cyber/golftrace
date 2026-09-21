"""
Celery Beat schedule for maintenance jobs: reconciler and cleanup.
"""
from .celery_app import celery_app
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'reconcile-abandoned-jobs-every-5-min': {
        'task': 'app.workers.tasks.reconcile_task',
        'schedule': 300.0,  # every 5 minutes
    },
    'cleanup-deleted-projects-daily': {
        'task': 'app.workers.tasks.cleanup_task',
        'schedule': crontab(hour=2, minute=0),  # daily at 2am
        'args': ('all',)  # placeholder, actual cleanup iterates over deleted projects
    }
}

celery_app.conf.timezone = 'UTC'
