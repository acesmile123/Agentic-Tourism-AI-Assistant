# Agentic Tourism AI Assistant

Nền tảng AI agent tư vấn du lịch Việt Nam. Agent chọn công cụ phù hợp, truy xuất knowledge base Qdrant bằng hybrid retrieval + Cohere reranking, rồi tổng hợp câu trả lời streaming qua SSE.

## Kiến trúc

```text
React frontend -> Nginx (/api) -> FastAPI -> LangGraph agent
                                             |-> MCP tourism knowledge tool
                                             |    -> Qdrant hybrid retrieval + Cohere rerank
                                             |-> Weather / Goong Places / Budget / Tavily web search
                                             `-> Gemini synthesis

FastAPI -> PostgreSQL (durable sessions)
        -> Redis (short-term memory, cache, rate limiting)
```

Các tool chỉ trả activity status an toàn cho UI, không trả chain-of-thought.

## Cấu trúc project

```text
.
├── tourism_agent/              # Backend package
│   ├── agent/                  # LangGraph state, planner, validator, workflow
│   ├── api/                    # FastAPI routes, schemas, middleware
│   ├── application/            # Dependency container
│   ├── core/                   # Settings và structured logging
│   ├── domain/                 # Models nghiệp vụ
│   ├── evaluation/             # Metrics, LLM judge, evaluation runner
│   ├── infrastructure/         # PostgreSQL và Redis adapters
│   ├── mcp/                    # MCP server/client
│   ├── observability/          # Langfuse tracing
│   ├── services/               # Retrieval, reranking, RAG, generation, sessions
│   └── tools/                  # Tourism, weather, Goong, budget, web search
├── frontend/                   # React + Vite UI
├── ingestion/                  # Offline crawl/chunk và Qdrant upsert commands
├── evaluation/                 # Evaluation dataset và hướng dẫn chạy eval
├── tests/                      # Unit/integration tests
├── alembic/                    # Versioned PostgreSQL migrations
├── deploy/                     # Nginx và production env template
├── scripts/                    # Deployment scripts
├── docs/                       # Architecture và phase notes
├── compose.yaml                # Local stack
└── compose.production.yaml     # EC2 production stack (RDS/Redis external)
```

`ingestion/` chỉ chạy khi thêm hoặc cập nhật dữ liệu. App production luôn dùng collection Qdrant Cloud đã có, không crawl hoặc embed lại khi khởi động.

## Local development

### 1. Environment

```bash
cp .env.example .env
```

Điền `QDRANT_URL`, `QDRANT_API_KEY`, `COLLECTION_NAME`, `GEMINI_API_KEY`, `COHERE_API_KEY`; các key tool là tùy chọn. Không commit `.env`.

### 2. Backend, PostgreSQL, Redis và MCP

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- MCP internal/local endpoint: `http://localhost:8001/mcp`

Compose chạy Alembic trước API để tạo/cập nhật schema PostgreSQL.

### 3. Frontend

Trong terminal khác:

```bash
cd frontend
npm ci
npm run dev
```

Mở `http://localhost:3000`. Vite proxy `/api` sang backend port 8000.

## Ingestion (chỉ khi cập nhật knowledge base)

Crawler tạo JSON chunks:

```bash
python -m ingestion.crawl --txt urls.txt --province da_nang --source example --output data/processed/da_nang.json --headless
```

Upsert chunks lên collection đã cấu hình:

```bash
python -m ingestion.upsert_qdrant --input-dir data/processed
```

Command upsert dùng UUID ổn định, nên ingest lại cùng chunk sẽ update thay vì tạo duplicate.

## Tests và evaluation

```bash
pytest -q
python -m tourism_agent.evaluation.runner --transport mcp --no-llm-judge
```

Xem [evaluation/README.md](evaluation/README.md) và [docs/phase-5.md](docs/phase-5.md) để biết cách đọc metric, Langfuse và cải thiện retrieval/routing.

## Production

Production stack dùng Nginx, API, MCP và static frontend containers. PostgreSQL/Redis phải là RDS và ElastiCache (hoặc endpoints managed tương đương) bên ngoài Compose.

```bash
cp deploy/.env.production.example .env.production
# Điền secret và endpoints thật, không commit file này.
APP_IMAGE=ghcr.io/OWNER/REPO/api:TAG \
FRONTEND_IMAGE=ghcr.io/OWNER/REPO/web:TAG \
./scripts/deploy-production.sh
```

Xem [docs/phase-6.md](docs/phase-6.md) cho EC2, Nginx/SSE, HTTPS, GitHub Actions và secrets.

## Key capabilities

- LangGraph planner/router, query decomposition, validator và retry có giới hạn.
- MCP service tái sử dụng được; adaptive retrieval fallback sang web search khi score nội bộ thấp.
- Hybrid dense+sparse Qdrant retrieval, Cohere reranking và Gemini fast/complex model routing.
- PostgreSQL sessions; Redis tách logical workload: memory, cache, rate limit.
- Langfuse tracing, evaluation dataset: Recall@K, MRR, faithfulness, relevance, tool routing.
- Docker health checks, Nginx SSE proxy, Alembic migration, CI/CD workflow.
