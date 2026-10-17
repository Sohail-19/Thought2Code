from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

import api.main as api_main
from agent.tools import use_project_root, write_file


client = TestClient(api_main.app)


def make_completed_job(monkeypatch, tmp_path, files):
    jobs_root = tmp_path / "jobs"
    job_id = uuid4().hex
    job_root = jobs_root / job_id
    job_root.mkdir(parents=True)
    for path, content in files.items():
        output = job_root / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    marker_root = jobs_root / ".completed"
    marker_root.mkdir(exist_ok=True)
    (marker_root / f"{job_id}.done").touch()
    monkeypatch.setattr(api_main, "PROJECTS_ROOT", jobs_root)
    return job_id, job_root


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_rejects_invalid_description():
    response = client.post("/generate", json={"project_description": "short"})

    assert response.status_code == 422


def test_generate_returns_plan_and_job_scoped_files(monkeypatch, tmp_path):
    class FakePlan(BaseModel):
        name: str = "Example"
        description: str = "Example project"
        techstack: str = "HTML, CSS, JavaScript"
        features: list[str] = ["A sample feature"]

    monkeypatch.setattr(api_main, "PROJECTS_ROOT", tmp_path / "jobs")

    def fake_invoke(state, config):
        assert state["user_prompt"] == "Build a small example application"
        assert config == {"recursion_limit": 100}
        write_file.invoke({"path": "index.html", "content": "<main>Example</main>"})
        return {"plan": FakePlan()}

    monkeypatch.setattr(api_main.agent, "invoke", fake_invoke)

    response = client.post(
        "/generate",
        json={"project_description": "Build a small example application"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["project"]["name"] == "Example"
    assert body["generated_files"] == ["index.html"]
    assert (tmp_path / "jobs" / body["job_id"] / "index.html").read_text() == "<main>Example</main>"
    assert (tmp_path / "jobs" / ".completed" / f"{body['job_id']}.done").exists()


def test_file_tools_are_isolated_by_project_root(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    with use_project_root(first_root):
        write_file.invoke({"path": "only-first.txt", "content": "first"})
    with use_project_root(second_root):
        write_file.invoke({"path": "only-second.txt", "content": "second"})

    assert (first_root / "only-first.txt").read_text() == "first"
    assert not (first_root / "only-second.txt").exists()
    assert (second_root / "only-second.txt").read_text() == "second"
    assert not (second_root / "only-first.txt").exists()


def test_completed_job_file_reading_is_isolated(monkeypatch, tmp_path):
    first_id, _ = make_completed_job(monkeypatch, tmp_path, {"index.html": "<h1>first job</h1>"})
    jobs_root = api_main.PROJECTS_ROOT
    second_id = uuid4().hex
    second_root = jobs_root / second_id
    second_root.mkdir()
    (second_root / "index.html").write_text("<h1>second job</h1>")
    (jobs_root / ".completed" / f"{second_id}.done").touch()

    listing = client.get(f"/jobs/{first_id}/files")
    content = client.get(f"/jobs/{first_id}/files/index.html")
    cross_job_path = client.get(f"/jobs/{first_id}/files/%2E%2E%2F{second_id}%2Findex.html")

    assert listing.status_code == 200
    assert listing.json()["job_id"] == first_id
    assert [file["path"] for file in listing.json()["files"]] == ["index.html"]
    assert content.status_code == 200
    assert content.json()["content"] == "<h1>first job</h1>"
    assert cross_job_path.status_code == 400
    assert second_id not in content.text


def test_file_endpoint_rejects_traversal_and_absolute_paths(monkeypatch, tmp_path):
    job_id, job_root = make_completed_job(monkeypatch, tmp_path, {"safe.txt": "safe"})

    for requested in ("../outside.txt", "/etc/passwd", "C:/Windows/win.ini", "..\\outside.txt"):
        try:
            api_main._safe_job_file(job_root, requested)
        except HTTPException as error:
            assert error.status_code == 400
        else:
            raise AssertionError(f"Unsafe path was accepted: {requested}")

    traversal_request = client.get(f"/jobs/{job_id}/files/%2E%2E%2Foutside.txt")
    assert traversal_request.status_code == 400


def test_file_endpoint_returns_404_for_missing_job_or_file(monkeypatch, tmp_path):
    job_id, _ = make_completed_job(monkeypatch, tmp_path, {})

    missing_file = client.get(f"/jobs/{job_id}/files/missing.md")
    missing_job = client.get(f"/jobs/{uuid4().hex}/files")

    assert missing_file.status_code == 404
    assert missing_job.status_code == 404
    assert str(tmp_path) not in missing_file.text


def test_unmarked_job_is_not_treated_as_completed(monkeypatch, tmp_path):
    jobs_root = tmp_path / "jobs"
    job_id = uuid4().hex
    (jobs_root / job_id).mkdir(parents=True)
    monkeypatch.setattr(api_main, "PROJECTS_ROOT", jobs_root)

    response = client.get(f"/jobs/{job_id}/files")

    assert response.status_code == 404
    assert str(tmp_path) not in response.text


def test_file_endpoint_rejects_symlink_escape(monkeypatch, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside job")
    job_id, job_root = make_completed_job(monkeypatch, tmp_path, {})
    (job_root / "escape.txt").symlink_to(outside)

    response = client.get(f"/jobs/{job_id}/files/escape.txt")

    assert response.status_code == 400
    assert str(tmp_path) not in response.text


def test_file_endpoint_enforces_size_and_text_file_limits(monkeypatch, tmp_path):
    job_id, job_root = make_completed_job(
        monkeypatch,
        tmp_path,
        {
            "large.txt": b"x" * (api_main.MAX_VIEWABLE_FILE_BYTES + 1),
            "program.exe": b"MZ\x00\x01",
            "run.sh": "#!/bin/sh\nprintf unsafe",
        },
    )
    (job_root / "run.sh").chmod(0o755)

    oversized = client.get(f"/jobs/{job_id}/files/large.txt")
    executable = client.get(f"/jobs/{job_id}/files/program.exe")
    executable_script = client.get(f"/jobs/{job_id}/files/run.sh")
    listing = client.get(f"/jobs/{job_id}/files")

    assert oversized.status_code == 413
    assert executable.status_code == 400
    assert executable_script.status_code == 400
    listed = {file["path"]: file for file in listing.json()["files"]}
    assert listed["large.txt"]["viewable"] is False
    assert listed["program.exe"]["viewable"] is False
    assert listed["run.sh"]["viewable"] is False


def test_file_endpoint_rejects_non_utf8_text(monkeypatch, tmp_path):
    job_id, _ = make_completed_job(monkeypatch, tmp_path, {"notes.txt": b"\xff\xfe"})

    response = client.get(f"/jobs/{job_id}/files/notes.txt")

    assert response.status_code == 400
    assert str(tmp_path) not in response.text
