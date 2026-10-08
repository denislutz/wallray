from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.adapters.email.resend import ResendAdapter
from app.adapters.persistence.pg_job_repo import PostgresJobRepository
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.adapters.storage.s3 import S3StorageAdapter
from app.adapters.vision_llm.anthropic import AnthropicAdapter
from app.api.deps import (
    current_user,
    get_email,
    get_job_repo,
    get_renderer,
    get_storage,
    get_user_repo,
    get_vision_llm,
)
from app.api.schemas import UploadResponse
from app.application.run_assessment import RunAssessment
from app.application.upload_job import FreeTierLimitError, UploadJob, ValidationError
from app.core.config import settings

router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload(
    user: Annotated[dict[str, object], Depends(current_user)],
    background_tasks: BackgroundTasks,
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
    vision_llm: Annotated[AnthropicAdapter, Depends(get_vision_llm)],
    renderer: Annotated[Xhtml2pdfAdapter, Depends(get_renderer)],
    email: Annotated[ResendAdapter, Depends(get_email)],
    files: Annotated[list[UploadFile], File()],
    description: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    language: Annotated[str, Form()] = "en",
) -> UploadResponse:
    try:
        job_id = await UploadJob(storage, job_repo, user_repo).execute(
            str(user["sub"]),
            files,
            description,
            name=name or None,
            language=language,
        )
    except FreeTierLimitError as exc:
        raise HTTPException(
            status_code=402, detail={"message": "Free tier limit reached", "limit": exc.limit}
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run_assessment = RunAssessment(
        storage=storage,
        job_repo=job_repo,
        user_repo=user_repo,
        vision_llm=vision_llm,
        renderer=renderer,
        email=email,
        fe_base_url=settings.fe_base_url,
    )
    background_tasks.add_task(run_assessment.run, job_id, str(user["sub"]))
    return UploadResponse(job_id=job_id)
