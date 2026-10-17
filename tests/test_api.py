from pydantic import BaseModel
from fastapi.testclient import TestClient

import api.main as api_main
from agent.tools import use_project_root, write_file


client = TestClient(api_main.app)


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
