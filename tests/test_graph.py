import pytest

import agent.graph as graph_module
from agent.states import Plan, TaskPlan


class StubStructuredModel:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, _prompt):
        if self.schema is Plan:
            return Plan(
                name="Graph state regression",
                description="A project used to verify graph state retention",
                techstack="Python",
                features=["State survives each workflow node"],
                files=[],
            )
        if self.schema is TaskPlan:
            return TaskPlan(implementation_steps=[])
        raise AssertionError(f"Unexpected structured output schema: {self.schema}")


class StubModel:
    def with_structured_output(self, schema):
        return StubStructuredModel(schema)


def test_compiled_graph_preserves_plan_through_coder(monkeypatch):
    monkeypatch.setattr(graph_module, "llm", StubModel())

    result = graph_module.agent.invoke(
        {"user_prompt": "A safe local regression prompt"},
        {"recursion_limit": 100},
    )

    assert isinstance(result["plan"], Plan)
    assert result["plan"].name == "Graph state regression"
    assert isinstance(result["task_plan"], TaskPlan)
    assert result["status"] == "DONE"


def test_compiled_graph_failure_identifies_the_failing_node(monkeypatch):
    class FailingStructuredModel:
        def invoke(self, _prompt):
            raise RuntimeError("structured model failure")

    class FailingModel:
        def with_structured_output(self, _schema):
            return FailingStructuredModel()

    monkeypatch.setattr(graph_module, "llm", FailingModel())

    with pytest.raises(RuntimeError, match="structured model failure") as raised:
        graph_module.agent.invoke(
            {"user_prompt": "A safe local regression prompt"},
            {"recursion_limit": 100},
        )

    assert "LangGraph node: planner" in raised.value.__notes__
