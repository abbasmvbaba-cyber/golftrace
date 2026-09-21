"""
Celery app with Redis broker. Falls back to memory if Redis not available.
"""
from celery import Celery
from ..config import settings

celery_app = Celery(
    "golftrace",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,  # Use Redis as result backend as well, or rpc
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_routes={
        "app.workers.tasks.prepare_video_task": {"queue": "video"},
        "app.workers.tasks.tracking_task": {"queue": "cpu_tracking"},
        "app.workers.tasks.render_task": {"queue": "rendering"},
        "app.workers.tasks.cleanup_task": {"queue": "maintenance"},
        "app.workers.tasks.reconcile_task": {"queue": "maintenance"},
    },
    task_default_queue="video",
)

# For sandbox without Redis, we can run tasks synchronously via direct calls in API layer
# But Celery app still defined

try:
    # Test Redis connection
    import redis
    r = redis.from_url(settings.REDIS_URL)
    r.ping()
    print(f"Celery broker connected: {settings.REDIS_URL}")
except Exception as e:
    print(f"Redis not available ({e}), Celery tasks will run synchronously fallback")
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
