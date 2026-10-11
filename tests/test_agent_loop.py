import json
import pytest
from app.agents.loop import AutonomousAgentLoop
from app.llm import BaseLLMProvider, LLMMessage, LLMResponse
from app.schemas.context import RepositoryContext
from app.schemas.github import RepositoryInfo, RepositorySnapshot, SourceFile


class SequenceLLMProvider(BaseLLMProvider):
    """Fake LLM Provider that yields a predefined sequence of responses for multi-turn testing."""

    def __init__(self, responses: list[dict]):
        self.responses = [json.dumps(r) for r in responses]
        self.call_count = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        content = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return LLMResponse(
            content=content,
            model="sequence-model",
            prompt_tokens=50,
            completion_tokens=25,
        )


@pytest.fixture
def mock_context():
    repo = RepositoryInfo(
        owner="owner",
        name="repo",
        full_name="owner/repo",
        default_branch="main",
        stars=1,
        forks=0,
        is_private=False,
    )

    f1 = SourceFile(
        path="app/config.py",
        sha="1",
        content="TIMEOUT = 30\n",
        language="python",
        size=15,
    )

    snapshot = RepositorySnapshot(repository=repo, files=[f1])
    return RepositoryContext(snapshot=snapshot, existing_issues=[])


@pytest.mark.asyncio
async def test_agent_loop_tool_calling_flow(mock_context):
    sequence = [
        # Turn 1: Call tool grep_search_code
        {
            "action": "call_tool",
            "tool_name": "grep_search_code",
            "arguments": {"pattern": "TIMEOUT"},
        },
        # Turn 2: Return final result
        {
            "action": "final_result",
            "summary": "Verified config timeout settings",
            "hypotheses": [
                {
                    "title": "Low timeout value",
                    "description": "Timeout set to only 30s",
                    "path": "app/config.py",
                    "line": 1,
                    "severity": "info",
                    "evidence": ["TIMEOUT = 30"],
                    "confidence": 0.6,
                }
            ],
        },
    ]

    provider = SequenceLLMProvider(sequence)
    agent = AutonomousAgentLoop(provider=provider, max_iterations=3)

    result = await agent.run(mock_context)

    assert result.iterations_used == 2
    assert result.summary == "Verified config timeout settings"
    assert len(result.hypotheses) == 1
    assert len(result.evidence_gathered) == 1
    assert result.evidence_gathered[0]["tool"] == "grep_search_code"


@pytest.mark.asyncio
async def test_agent_loop_max_iterations_reached(mock_context):
    # LLM keeps calling tools indefinitely
    sequence = [
        {
            "action": "call_tool",
            "tool_name": "grep_search_code",
            "arguments": {"pattern": "TIMEOUT"},
        }
    ]

    provider = SequenceLLMProvider(sequence)
    agent = AutonomousAgentLoop(provider=provider, max_iterations=2)

    result = await agent.run(mock_context)

    assert result.iterations_used == 2
    assert "maximum iteration limit" in result.summary
    assert len(result.hypotheses) == 0
