import asyncio
import json

from mcp import Client

from tourism_agent.core.config import Settings
from tourism_agent.mcp.client import MCPToolRegistry
from tourism_agent.mcp.server import create_mcp_server
from tourism_agent.tools.base import ToolRegistry
from tourism_agent.tools.budget import BudgetCalculatorTool


def make_server():
    settings = Settings(
        qdrant_url="http://qdrant:6333",
        collection_name="tourism",
        gemini_api_key="test",
        adaptive_retrieval_threshold=0.3,
    )
    return create_mcp_server(ToolRegistry([BudgetCalculatorTool()]), settings)


def test_mcp_exposes_tools_and_resources():
    async def scenario():
        async with Client(make_server()) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["budget_calculator"]

            result = await client.call_tool("budget_calculator", {
                "destination": "Đà Nẵng", "days": 3, "travelers": 2,
            })
            outer = json.loads(result.content[0].text)
            budget = json.loads(outer["content"])
            assert budget["currency"] == "VND"

            policy = await client.read_resource("tourism://retrieval/policy")
            payload = json.loads(policy.contents[0].text)
            assert payload["fallback_threshold"] == 0.3

    asyncio.run(scenario())


def test_agent_registry_discovers_and_calls_tools_through_mcp():
    registry = MCPToolRegistry(make_server(), discovery_ttl_seconds=60)

    assert [tool.name for tool in registry.specs()] == ["budget_calculator"]
    result = registry.execute("budget_calculator", {"destination": "Huế", "days": 2})

    assert result.success is True
    assert json.loads(result.content)["destination"] == "Huế"
