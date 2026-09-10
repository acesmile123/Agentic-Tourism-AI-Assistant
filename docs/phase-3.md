# Phase 3 - MCP tool platform and adaptive retrieval

## Kết quả kiến trúc

```text
Client -> FastAPI /chat -> LangGraph planner
                              |
                              | MCP Streamable HTTP
                              v
                    Tourism MCP service :8001
                    |-- tourism knowledge
                    |     |-- Qdrant dense+sparse hybrid
                    |     |-- Cohere rerank
                    |     `-- Tavily fallback
                    |-- weather / maps / web
                    `-- budget calculator

PostgreSQL <- chat sessions      Redis <- memory + retrieval cache
```

FastAPI không còn import hoặc khởi tạo trực tiếp Qdrant, Cohere hay các provider tool. Nó lấy catalog/schema bằng MCP `tools/list`, để planner chọn tool, rồi gọi bằng MCP `tools/call`. Service MCP là nơi duy nhất sở hữu implementation và API key của tool.

Transport dùng **Streamable HTTP** tại `http://mcp:8001/mcp`. Đây là transport HTTP hiện hành của MCP; SSE cũ không được dùng cho kết nối MCP này. SSE tại `/chat` vẫn được giữ nguyên vì đó là giao thức stream token tới frontend, không liên quan đến MCP.

## Tools và resources

Tools được expose tùy theo cấu hình thực tế:

- `search_tourism_knowledge`: luôn có; Qdrant hybrid + Cohere + adaptive web fallback.
- `budget_calculator`: luôn có.
- `weather`: chỉ expose khi có `OPENWEATHER_API_KEY`.
- `map_location`: chỉ expose khi có `GOONG_API_KEY`; dùng Goong Place AutoComplete/Detail.
- `web_search`: chỉ expose khi có `TAVILY_API_KEY`.

Resources (dữ liệu application-controlled):

- `tourism://tools/catalog`: catalog và trạng thái cấu hình của toàn bộ tool.
- `tourism://retrieval/policy`: threshold và chính sách fallback hiện tại.

Muốn tái sử dụng service từ agent/app khác, chỉ cần trỏ MCP client đến endpoint trên; client không cần biết class Python hoặc API provider nằm phía sau.

## Adaptive Retrieval Thresholding

`search_tourism_knowledge` chạy theo thứ tự:

1. Qdrant dense+sparse hybrid retrieval.
2. Lưu hybrid score trên từng chunk và rerank bằng Cohere.
3. Nếu max hybrid score nhỏ hơn `ADAPTIVE_RETRIEVAL_THRESHOLD` (mặc định `0.3`), gọi Tavily để bổ sung.
4. Câu hỏi có dấu hiệu thời sự như “hôm nay”, “sắp tới”, “giá vé”, “giờ mở cửa”, “lễ hội” luôn kích hoạt web fallback, kể cả score nội bộ cao.
5. Tool trả về JSON có `internal_retrieval`, `web_fallback`, lý do fallback, score và URL nguồn. Gemini được yêu cầu dùng nội bộ cho kiến thức ổn định, web cho dữ liệu mới, không âm thầm trộn dữ liệu mâu thuẫn.

Qdrant hybrid/RRF score **không phải xác suất đã hiệu chỉnh**. `0.3` chỉ là giá trị khởi đầu; nên dùng bộ câu hỏi validation để đo answer coverage và web-fallback rate trước khi chọn threshold production.

Nếu chưa có `TAVILY_API_KEY`, kết quả vẫn cho biết lý do đáng lẽ phải fallback nhưng không bịa dữ liệu web.

## Cấu hình và chạy local

Các biến mới trong `.env`:

```env
MCP_SERVER_URL=http://mcp:8001/mcp
MCP_HOST=0.0.0.0
MCP_PORT=8001
MCP_READ_TIMEOUT_SECONDS=45
MCP_DISCOVERY_TTL_SECONDS=300
ADAPTIVE_RETRIEVAL_THRESHOLD=0.3
```

Build và chạy cả stack:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f mcp api
```

Các endpoint:

- App API: `http://localhost:8000`
- MCP Streamable HTTP: `http://localhost:8001/mcp`

Không mở MCP URL trực tiếp trong browser để kiểm thử như trang web thông thường; MCP client phải gửi đúng protocol headers và session messages.

## Cách thêm tool mới

1. Viết domain tool thực thi logic và trả `ToolResult`.
2. Đăng ký tool vào `build_tool_registry()` của MCP service.
3. Expose một function có type hints bằng `@server.tool()`.
4. Restart service MCP. API tự khám phá schema mới sau TTL (mặc định 5 phút) hoặc ngay khi restart API.

Không cần sửa planner prompt hay tạo HTTP endpoint riêng cho từng provider.
