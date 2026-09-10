# Phase 5 - AI Evaluation and Observability

Phase 5 tạo hai vòng phản hồi tách biệt:

```text
Offline: dataset -> run agent -> metrics -> failure report -> sửa có kiểm chứng
Online:  user request -> Langfuse traces/spans -> tìm edge case -> thêm lại dataset
```

Không có code nào tự thay prompt hoặc threshold production. Report chỉ đưa bằng chứng và recommendation; engineer review rồi chạy lại experiment với baseline để tránh regression.

## Evaluation dataset

Seed dataset nằm ở `evaluation/datasets/tourism_ai_eval.jsonl`, gồm 12 case:

- Stable tourism knowledge, food và itinerary.
- Budget, weather và map tool routing.
- Fresh/current-information routing.
- Complex multi-tool planning.
- Direct response không cần tool.

Schema và quy tắc annotation nằm ở `evaluation/README.md`. Đây là seed dataset: trước khi dùng làm release gate phải review relevance label với collection Qdrant thật. Mỗi production failure đã ẩn dữ liệu cá nhân nên được thêm thành một regression case mới.

## Metrics

### Retrieval

- `Recall@K`: tỷ lệ relevance targets xuất hiện trong top K documents.
- `MRR`: nghịch đảo rank của document relevant đầu tiên; relevant ở rank 1 cho MRR=1.0.

Dataset hiện dùng keyword/metadata relevance targets vì các point cũ được upsert bằng UUID ngẫu nhiên. Khi ingestion có stable `document_id/chunk_id`, nên chuyển label sang ID để metric chặt hơn.

### Routing

- Tool precision: Agent có gọi dư tool không.
- Tool recall: Agent có gọi đủ tool bắt buộc không.
- Tool F1: cân bằng hai metric trên.

### Generation

- `Faithfulness`: factual claims trong answer có được context/tool results hỗ trợ không.
- `Relevance`: answer có trả lời query và bao phủ rubric mong đợi không.

Mặc định evaluator dùng Gemini làm semantic judge. `--no-llm-judge` dùng lexical heuristic để smoke test nhanh; heuristic không đủ tin cậy để làm production quality gate.

Threshold ban đầu:

```text
Recall@K     >= 0.80
MRR          >= 0.50
Faithfulness >= 0.75
Relevance    >= 0.75
Tool F1      >= 0.80
```

## Chạy evaluation

Chạy unit tests, không gọi API thật:

```powershell
pytest -q
```

Khi Docker stack đang chạy, đánh giá nhanh hai case qua MCP, không dùng LLM judge:

```powershell
python -m tourism_agent.evaluation.runner --transport mcp --limit 2 --no-llm-judge
```

Chạy toàn bộ semantic evaluation:

```powershell
python -m tourism_agent.evaluation.runner --transport mcp
```

Nếu chạy evaluator trên host, `MCP_SERVER_URL` phải là `http://localhost:8001/mcp`. Trong container API nó vẫn là `http://mcp:8001/mcp`.

Report JSON và Markdown được ghi vào `eval_reports/` và đã được git-ignore. Evaluation thật gọi Qdrant/tool APIs, Agent Gemini và thêm một Gemini judge call trên mỗi case; cần dự trù latency/quota.

## Baseline regression / continuous improvement

Sau khi review một report tốt, dùng JSON đó làm baseline. Với report ví dụ `eval_reports/tourism-eval-20260902-120000.json`:

```powershell
python -m tourism_agent.evaluation.runner `
  --transport mcp `
  --baseline eval_reports/tourism-eval-20260902-120000.json `
  --fail-on-regression
```

Mặc định metric giảm quá `0.02` được coi là regression và process trả exit code 1, phù hợp để nối vào CI. Có thể đổi bằng `--regression-tolerance`.

Failure analyzer ánh xạ vấn đề sang hướng xử lý:

| Failure | Hướng điều tra |
|---|---|
| Recall thấp | metadata/province filter, retrieval K, query expansion |
| MRR thấp | Cohere reranker, hard negatives |
| Faithfulness thấp | context nhiễu, citation, generation prompt |
| Relevance thấp | decomposition và synthesis prompt |
| Tool F1 thấp | tool descriptions, planner routing examples |

Chỉ thay một nhóm cấu hình/prompt mỗi experiment để biết thay đổi nào thực sự tạo ra cải thiện.

## Langfuse observability

Cấu hình trong `.env`:

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_SAMPLE_RATE=1.0
```

Không có key hoặc `LANGFUSE_ENABLED=false` thì observer là no-op; Agent vẫn chạy bình thường.

Các observation:

```text
tourism.agent.workflow        agent       root workflow + output
agent.planner                 agent       goal, subtasks, tool plan
agent.tool_execution          chain       dependency execution
mcp.tool.<name>               tool        arguments, success, sources
agent.self_correction         agent       validation issues + revised plan
agent.validator               evaluator   validity and issues
qdrant.hybrid_retrieval       retriever   route, score, cache hit, documents
gemini.complete               generation  planner/router calls + tokens
gemini.agent_answer           generation  final draft + tokens
evaluation.<case_id>          evaluator   offline metrics and failures
```

Latency được Langfuse tính từ thời gian bắt đầu/kết thúc span. Token input/output/total được lấy từ Gemini `usage_metadata`, không phải ước lượng theo ký tự.

FastAPI và MCP là hai process. API trace chứa Agent và MCP client tool spans; retrieval span chạy trong MCP process và hiện xuất hiện như trace riêng trong cùng project. Distributed trace-context propagation qua MCP có thể thêm ở phase vận hành sau nếu cần một trace xuyên service hoàn chỉnh.

## Privacy và vận hành

- Trace có thể chứa query, recent history, tool results và retrieval snippets; chỉ bật ở project có access control phù hợp.
- Payload được giới hạn độ dài nhưng chưa phải hệ thống PII redaction hoàn chỉnh.
- Dùng `LANGFUSE_SAMPLE_RATE` thấp hơn ở traffic lớn.
- Telemetry được thiết kế fail-open: Langfuse lỗi không được làm chat request thất bại.
- `/health/ready` trả `observability=true` khi client Langfuse thực sự được bật.
