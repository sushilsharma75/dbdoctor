"""Audit jobs: validated snapshot upload → background pipeline → review hold.

The review hold is the product's quality gate (G10): a report is generated
into status='review' and stays inaccessible to the customer until an admin
approves the job. No auto-delivery in the MVP.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.models import Snapshot
from webapp.backend.app.auth import get_current_user, require_admin
from webapp.backend.app.config import get_settings
from webapp.backend.app.db import AuditJob, User, get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: str
    status: str
    engine: str
    client_alias: str
    paid: bool
    score: str | None
    error: str | None
    created_at: datetime

    @classmethod
    def from_job(cls, job: AuditJob) -> JobOut:
        return cls(
            id=job.id,
            status=job.status,
            engine=job.engine,
            client_alias=job.client_alias,
            paid=job.paid,
            score=job.score,
            error=job.error,
            created_at=job.created_at,
        )


def _job_dir(job_id: str) -> Path:
    return Path(get_settings().data_dir) / "jobs" / job_id


def _load_job_for(job_id: str, user: User, db: Session) -> AuditJob:
    job = db.get(AuditJob, job_id)
    if job is None or (job.user_id != user.id and not user.is_admin):
        # 404 for foreign jobs: don't reveal that the id exists
        raise HTTPException(404, "job not found")
    return job


# --------------------------------------------------------------------------
# Pipeline (runs in a background task; the V1 scheduler reuses this)
# --------------------------------------------------------------------------


def run_pipeline(job_id: str) -> None:
    from webapp.backend.app.db import get_engine

    get_engine()
    from webapp.backend.app.db import _session_factory  # after engine init

    settings = get_settings()
    db = _session_factory()
    try:
        job = db.get(AuditJob, job_id)
        if job is None:
            return
        job.status = "processing"
        db.commit()
        try:
            from engine.run import run_all
            from report.ai_explain import AiExplainer
            from report.render import render_report
            from report.tasks import tasks_markdown

            job_dir = _job_dir(job.id)
            snapshot = Snapshot.model_validate(json.loads((job_dir / "snapshot.json").read_text()))
            result = run_all(snapshot)

            ai_texts: dict[str, str] = {}
            if settings.enable_ai:
                explainer = AiExplainer(cache_dir=job_dir / ".cache")
                ai_texts = explainer.explain_all(result.score.top_findings)

            html = render_report(result, snapshot, client_alias=job.client_alias, ai_texts=ai_texts)
            (job_dir / "report.html").write_text(html)
            if settings.enable_pdf:
                from report.pdf import html_to_pdf

                html_to_pdf(html, job_dir / "report.pdf")
            (job_dir / "tasks.md").write_text(tasks_markdown(result, ai_texts))
            (job_dir / "findings.json").write_text(result.model_dump_json(indent=2))

            job.report_path = str(job_dir)
            job.score = str(result.score.score)
            job.status = "review"  # held for founder approval — never auto-delivered
        except Exception as exc:  # keep the failure visible on the job
            job.status = "failed"
            job.error = str(exc)[:2000]
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    background: BackgroundTasks,
    snapshot: UploadFile = File(..., description="snapshot.json from a dbdoctor collector"),
    client_alias: str = Form("client"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    settings = get_settings()
    raw = await snapshot.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "snapshot exceeds the 50MB limit")

    # validate BEFORE accepting anything into storage
    try:
        parsed = Snapshot.model_validate(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"not valid JSON: {exc}") from None
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise HTTPException(
            422,
            f"not a valid dbdoctor snapshot (field '{loc}': {first['msg']}). "
            "Generate the file with pg_collect.py or mysql_collect.py and upload it unmodified.",
        ) from None

    job = AuditJob(user_id=user.id, engine=parsed.meta.engine, client_alias=client_alias[:120])
    db.add(job)
    db.commit()

    job_dir = _job_dir(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "snapshot.json").write_bytes(raw)

    background.add_task(run_pipeline, job.id)
    return JobOut.from_job(job)


@router.get("", response_model=list[JobOut])
def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(AuditJob).order_by(AuditJob.created_at.desc())
    if not user.is_admin:
        query = query.where(AuditJob.user_id == user.id)
    return [JobOut.from_job(j) for j in db.scalars(query)]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return JobOut.from_job(_load_job_for(job_id, user, db))


@router.get("/{job_id}/report")
def get_report(
    job_id: str,
    fmt: str = "pdf",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _load_job_for(job_id, user, db)
    # review hold: customers see nothing until an admin approved the report
    if job.status != "approved" and not user.is_admin:
        raise HTTPException(409, f"report is not available yet (status: {job.status})")
    if job.report_path is None:
        raise HTTPException(409, "report has not been generated yet")

    name = "report.pdf" if fmt == "pdf" else "report.html" if fmt == "html" else "tasks.md"
    path = Path(job.report_path) / name
    if not path.exists():
        raise HTTPException(404, f"{name} not found for this job")
    return FileResponse(path, filename=f"dbdoctor_{job.client_alias}_{name}")


@router.post("/{job_id}/approve", response_model=JobOut)
def approve_job(
    job_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.get(AuditJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.status != "review":
        raise HTTPException(409, f"only jobs in review can be approved (status: {job.status})")
    job.status = "approved"
    db.commit()
    return JobOut.from_job(job)
