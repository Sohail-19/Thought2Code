import pathlib
import os
import re
import stat
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import RateLimitError
from pydantic import BaseModel, ConfigDict, StringConstraints

from agent.graph import agent
from agent.tools import use_project_root


PROJECTS_ROOT = pathlib.Path(__file__).resolve().parents[1] / "generated_project" / "jobs"
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_VIEWABLE_FILE_BYTES = 1_048_576
MAX_JOB_FILE_COUNT = 1_000
TEXT_FILE_LANGUAGES = {
    ".c": "c",
    ".cpp": "cpp",
    ".css": "css",
    ".html": "html",
    ".htm": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".sh": "shell",
    ".sql": "sql",
    ".svg": "xml",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".txt": "text",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}

RATE_LIMIT_DETAIL = "The AI provider's usage limit has been reached. Please wait and try again later."


app = FastAPI(title="Thought2Code Local API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=4000),
    ]


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    project: dict
    generated_files: list[str]


class GeneratedFileInfo(BaseModel):
    path: str
    size_bytes: int
    language: str
    viewable: bool


class JobFilesResponse(BaseModel):
    job_id: str
    files: list[GeneratedFileInfo]


class GeneratedFileResponse(BaseModel):
    job_id: str
    path: str
    language: str
    content: str


def _job_output_dir(job_id: str) -> pathlib.Path:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job identifier")

    jobs_root = PROJECTS_ROOT.resolve()
    candidate = PROJECTS_ROOT / job_id
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        raise HTTPException(status_code=404, detail="Completed job not found") from None

    if resolved.parent != jobs_root or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Completed job not found")

    completed_root = PROJECTS_ROOT / ".completed"
    try:
        resolved_completed_root = completed_root.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        raise HTTPException(status_code=404, detail="Completed job not found") from None
    if resolved_completed_root.parent != jobs_root:
        raise HTTPException(status_code=404, detail="Completed job not found")
    marker = resolved_completed_root / f"{job_id}.done"
    if marker.is_symlink() or not marker.is_file():
        raise HTTPException(status_code=404, detail="Completed job not found")
    return resolved


def _safe_job_file(job_root: pathlib.Path, requested_path: str) -> pathlib.Path:
    if (
        not requested_path
        or "\x00" in requested_path
        or "\\" in requested_path
        or re.match(r"^[a-zA-Z]:", requested_path)
    ):
        raise HTTPException(status_code=400, detail="Invalid generated file path")

    relative = PurePosixPath(requested_path)
    if relative.is_absolute() or any(part in {"..", "."} for part in relative.parts):
        raise HTTPException(status_code=400, detail="Invalid generated file path")

    candidate = job_root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise HTTPException(status_code=400, detail="Invalid generated file path")

    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        raise HTTPException(status_code=404, detail="Generated file not found") from None

    if job_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Invalid generated file path")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found")
    return resolved


def _completed_job_files(job_root: pathlib.Path) -> list[GeneratedFileInfo]:
    result: list[GeneratedFileInfo] = []
    for directory, directory_names, file_names in os.walk(job_root, followlinks=False):
        directory_path = pathlib.Path(directory)
        directory_names[:] = [
            name for name in directory_names if not (directory_path / name).is_symlink()
        ]
        for file_name in file_names:
            file_path = directory_path / file_name
            if file_path.is_symlink():
                continue
            try:
                resolved = file_path.resolve(strict=True)
                metadata = resolved.stat()
            except (FileNotFoundError, OSError, RuntimeError):
                continue
            if job_root not in resolved.parents or not stat.S_ISREG(metadata.st_mode):
                continue
            language = TEXT_FILE_LANGUAGES.get(resolved.suffix.lower(), "binary")
            result.append(
                GeneratedFileInfo(
                    path=resolved.relative_to(job_root).as_posix(),
                    size_bytes=metadata.st_size,
                    language=language,
                    viewable=(
                        language != "binary"
                        and metadata.st_size <= MAX_VIEWABLE_FILE_BYTES
                        and not metadata.st_mode & 0o111
                    ),
                )
            )
            if len(result) > MAX_JOB_FILE_COUNT:
                raise HTTPException(
                    status_code=413,
                    detail="This project contains too many files to browse safely.",
                )
    return sorted(result, key=lambda file: file.path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/jobs/{job_id}/files", response_model=JobFilesResponse)
def list_job_files(job_id: str) -> JobFilesResponse:
    job_root = _job_output_dir(job_id)
    return JobFilesResponse(job_id=job_id, files=_completed_job_files(job_root))


@app.get("/jobs/{job_id}/files/{file_path:path}", response_model=GeneratedFileResponse)
def get_job_file(job_id: str, file_path: str) -> GeneratedFileResponse:
    job_root = _job_output_dir(job_id)
    file_path_on_disk = _safe_job_file(job_root, file_path)
    language = TEXT_FILE_LANGUAGES.get(file_path_on_disk.suffix.lower())
    if language is None:
        raise HTTPException(status_code=400, detail="This file type is not available for viewing")

    try:
        with file_path_on_disk.open("rb") as generated_file:
            metadata = pathlib.Path(file_path_on_disk).stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise HTTPException(status_code=400, detail="This file is not available for viewing")
            if metadata.st_size > MAX_VIEWABLE_FILE_BYTES:
                raise HTTPException(status_code=413, detail="Generated file exceeds the viewing limit")
            if metadata.st_mode & 0o111:
                raise HTTPException(status_code=400, detail="Executable files are not available for viewing")
            content = generated_file.read(MAX_VIEWABLE_FILE_BYTES + 1)
    except OSError:
        raise HTTPException(status_code=404, detail="Generated file not found") from None

    if len(content) > MAX_VIEWABLE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Generated file exceeds the viewing limit")
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="This file is not valid UTF-8 text") from None

    return GeneratedFileResponse(
        job_id=job_id,
        path=file_path_on_disk.relative_to(job_root).as_posix(),
        language=language,
        content=text_content,
    )


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    """Run generation synchronously in an isolated, server-owned directory."""
    job_id = uuid4().hex
    output_dir = (PROJECTS_ROOT / job_id).resolve()
    if PROJECTS_ROOT.resolve() not in output_dir.parents:
        raise HTTPException(status_code=500, detail="Could not initialize generation job")

    try:
        output_dir.mkdir(parents=True, exist_ok=False)
        try:
            with use_project_root(output_dir):
                result = agent.invoke(
                    {"user_prompt": request.project_description},
                    {"recursion_limit": 100},
                )
        except RateLimitError:
            raise HTTPException(status_code=429, detail=RATE_LIMIT_DETAIL) from None

        if not isinstance(result, Mapping):
            raise RuntimeError("Graph returned an unexpected state type")

        plan = result.get("plan")
        if plan is None:
            raise RuntimeError("Graph completed without a project plan")

        files = sorted(
            str(path.relative_to(output_dir))
            for path in output_dir.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and output_dir in path.resolve().parents
        )
        response = GenerateResponse(
            job_id=job_id,
            status="completed",
            project={
                "name": plan.name,
                "description": plan.description,
                "techstack": plan.techstack,
                "features": plan.features,
            },
            generated_files=files,
        )
        completed_root_path = PROJECTS_ROOT / ".completed"
        completed_root_path.mkdir(parents=True, exist_ok=True)
        completed_root = completed_root_path.resolve()
        if completed_root.parent != PROJECTS_ROOT.resolve():
            raise RuntimeError("Completed-job marker directory is outside the jobs root")
        (completed_root / f"{job_id}.done").touch(exist_ok=False)
        return response
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Generation failed. Check the backend configuration and try again.",
        ) from None
