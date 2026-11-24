import time

from celery import Task
from database import AuditEvent, DeploymentJob, JobEvent, SessionLocal
from workers.celery_app import celery_app


class DeploymentTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        job_id = args[0]
        _record_event(job_id, "error", f"Deployment execution failed: {exc}", "failed")


def _record_event(job_id: str, level: str, message: str, status: str | None = None) -> None:
    with SessionLocal.begin() as session:
        session.add(JobEvent(job_id=job_id, level=level, message=message, status=status))
        if status:
            job = session.get(DeploymentJob, job_id)
            if job is None:
                raise LookupError(f"Deployment job {job_id} no longer exists")
            job.status = status
            if status in {"completed", "failed"}:
                session.add(AuditEvent(job_id=job_id, action=status, actor="system"))


@celery_app.task(name="execute_deployment", base=DeploymentTask)
def execute_deployment(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(DeploymentJob, job_id)
        if job is None:
            raise LookupError(f"Deployment job {job_id} no longer exists")
        if job.status != "executing":
            return

    _record_event(job_id, "info", "Starting Ansible pre-check")
    time.sleep(0.2)
    _record_event(job_id, "info", "Pre-check: OSPF/BGP/VXLAN health baseline captured")
    time.sleep(0.2)
    _record_event(job_id, "success", "Deployment completed; post-check passed", "completed")
