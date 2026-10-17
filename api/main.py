import pathlib
from collections.abc import Mapping
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, StringConstraints

from agent.graph import agent
from agent.tools import use_project_root


PROJECTS_ROOT = pathlib.Path(__file__).resolve().parents[1] / "generated_project" / "jobs"

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest) -> GenerateResponse:
    """Run generation synchronously in a server-owned, isolated job directory."""
    job_id = uuid4().hex
    jobs_root = PROJECTS_ROOT.resolve()
    output_dir = (PROJECTS_ROOT / job_id).resolve()
    if jobs_root not in output_dir.parents:
        raise HTTPException(status_code=500, detail="Could not initialize generation job")

    try:
        output_dir.mkdir(parents=True, exist_ok=False)
        with use_project_root(output_dir):
            result = agent.invoke(
                {"user_prompt": request.project_description},
                {"recursion_limit": 100},
            )

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
        return GenerateResponse(
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
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Generation failed. Check the backend configuration and try again.",
        ) from None
