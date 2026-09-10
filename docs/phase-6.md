# Phase 6 — Cloud Deployment and Production

Phase 6 đưa project vào trạng thái có thể triển khai, nhưng không tự tạo AWS resources hay domain. Các quyết định cloud cần được thực hiện trong AWS Console/GitHub Secrets để tránh đưa credential vào Git.

## Artefacts đã có trong repository

| Mục tiêu | File | Vai trò |
|---|---|---|
| API image | `Dockerfile` | Python non-root image, liveness health check, proxy headers |
| Frontend image | `frontend/Dockerfile` | Build React thành static files, không chạy Vite ở production |
| Local stack | `compose.yaml` | PostgreSQL + Redis local; Redis logical DB 0/1/2 cho memory/cache/rate-limit |
| Production stack | `compose.production.yaml` | Chỉ API, MCP, Web, Nginx; PostgreSQL/Redis là external managed services |
| Reverse proxy | `deploy/nginx/tourism.conf` | Static web + `/api/*` proxy; `/api/chat` tắt buffering cho SSE |
| DB migration | `alembic/` | Versioned PostgreSQL schema migration |
| CI/CD | `.github/workflows/` | Test/build; push GHCR image + SSH deploy |
| Host deployment | `scripts/deploy-production.sh` | Pull image → Alembic upgrade → rolling Compose update |

## Production topology

```text
Browser ─HTTPS─> Nginx (EC2)
                   ├─ /       -> React static web container
                   └─ /api/*  -> FastAPI API -> MCP container
                                         ├─ RDS PostgreSQL
                                         ├─ ElastiCache Redis (memory/cache/rate limit)
                                         ├─ Qdrant Cloud
                                         └─ Gemini/Cohere/Goong/... APIs
```

Only Nginx will expose port 80/443. API (`8000`), MCP (`8001`), PostgreSQL and Redis are private to the Compose network or AWS VPC.

## Local run

```powershell
docker compose up -d --build
cd frontend
npm run dev
```

The development frontend now calls `/api`; Vite proxies it to `http://localhost:8000`. This avoids browser CORS issues locally.

## Production environment

Copy `deploy/.env.production.example` to a private file named `.env.production` on EC2, then fill it using values rendered from AWS Secrets Manager or SSM Parameter Store. Do not commit that file.

Redis is intentionally separated by purpose:

- `REDIS_MEMORY_URL`: short-term chat history.
- `REDIS_CACHE_URL`: retrieval cache; MCP uses this endpoint.
- `REDIS_RATE_LIMIT_URL`: request counters.

They may be logical Redis DBs during a small deployment, or independent ElastiCache endpoints when scaling.

## Migrations

For a new RDS database:

```bash
DATABASE_URL='postgresql+psycopg://...' alembic upgrade head
```

The production deploy script runs this before API startup. Local Compose also uses the same Alembic migration path, so schema changes have one versioned source of truth.

## Nginx and SSE

`/api/chat` uses `proxy_buffering off`, `X-Accel-Buffering: no` and a one-hour read timeout. These are required so token and safe activity events reach the browser as they stream.

## Observability and security controls

- JSON logs contain `request_id`, method, path, status code and `duration_ms`; they do not log request bodies, API keys, tool payloads or chain-of-thought.
- Langfuse continues to track Agent/tool/retrieval latency when configured.
- Redis fixed-window rate limit protects `/chat`; default is 20 requests per 60 seconds per client.
- Optional JWT verification is disabled by default. Enable it only after an identity provider can issue tokens with the configured audience.
- Production config rejects wildcard CORS and placeholder credentials.

## HTTPS — setup later after domain points to EC2

Do not run Certbot until the domain A record resolves to this EC2 public IP and port 80 is reachable. Then replace `server_name _;` with the domain and run:

```bash
sudo certbot --nginx -d chat.example.com
```

Certbot will add the TLS server block and redirect HTTP to HTTPS. After it works, expose only ports 80 and 443 in the EC2 security group; SSH 22 should be restricted to your own IP.

## GitHub Actions secrets needed later

Create the `production` GitHub Environment and add:

- `EC2_HOST`
- `EC2_USER`
- `EC2_SSH_KEY`

The runtime API keys remain only in AWS Secrets Manager/SSM and `/opt/tourism-agent/.env.production`; never add them as GitHub repository variables or embed them in the Docker image.
