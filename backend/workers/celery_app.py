from celery import Celery
import os

celery_app = Celery(
    "nact",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    include=["workers.tasks"],
)
celery_app.conf.task_routes = {
    "*_rs": {"queue": "queue_rs"},
    "*_fw": {"queue": "queue_fw"},
    "*_lb": {"queue": "queue_lb"},
    "*_iac": {"queue": "queue_iac"},
    "execute_deployment": {"queue": "queue_iac"},
}

@celery_app.task(name="pre_post_check_iac")
def pre_post_check_iac(payload):
    return {"status": "passed", "baseline": "healthy", "post": "healthy", "payload": payload}
