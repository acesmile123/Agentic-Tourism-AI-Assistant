# Phase 2 — LangGraph tourism agent

## Workflow

```text
START
  -> planner/router (Gemini structured JSON)
       |-- no tool -> respond
       `-- tool calls -> execute tools -> respond
  -> END
```

`AgentState` carries the user query, recent PostgreSQL/Redis-backed chat history, goal, planned tool calls, tool observations, and final answer. LangGraph custom streaming forwards Gemini tokens through the existing `/chat` SSE contract.

## Tools

| Tool | Provider | Configuration |
|---|---|---|
| `search_tourism_knowledge` | Existing Qdrant Cloud + Cohere | Existing Qdrant/Cohere variables |
| `weather` | OpenWeatherMap geocoding + current/5-day forecast | `OPENWEATHER_API_KEY` |
| `map_location` | Goong Place AutoComplete + Detail | `GOONG_API_KEY` |
| `budget_calculator` | Deterministic local calculator | No key |
| `web_search` | Tavily Search | `TAVILY_API_KEY` |

External tools with missing keys are included in the registry with `available=false`; the planner is instructed not to call them. Tool failures are returned as observations so the agent can explain the limitation instead of crashing the SSE stream.

## Configuration

Add the API keys you intend to use to `.env`:

```env
OPENWEATHER_API_KEY=
GOONG_API_KEY=
TAVILY_API_KEY=
TOOL_HTTP_TIMEOUT_SECONDS=10
```

Rebuild the API because Phase 2 adds LangGraph and new source files:

```powershell
docker compose up -d --build api
docker compose logs -f api
```

`/chat` runs the LangGraph agent. Retrieval and generation remain isolated services that can also be called through the Tourism Knowledge MCP tool.
