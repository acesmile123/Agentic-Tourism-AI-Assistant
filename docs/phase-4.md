# Phase 4 - Agent reliability

Phase này cố ý giữ thiết kế nhỏ: một planner có cấu trúc, một executor dependency-aware, một validator deterministic và tối đa một lần sửa kế hoạch.

## Workflow

```text
START
  -> planner / query decomposition
       |-- không cần tool -> draft
       `-- có tool -> dependency-aware tools
                          -> draft answer
                          -> validator
                               |-- đạt -> finalize -> SSE
                               `-- lỗi và còn retry
                                      -> correction/replan
                                      -> tools -> draft -> validator
                               `-- hết retry -> finalize an toàn
```

Khác Phase 3, Gemini tạo một `draft_answer` trước. Validator chạy trước khi token được gửi ra frontend, vì không thể thu hồi các token sai đã stream. Khi đạt hoặc đã hết retry, node `finalize` mới phát các token qua SSE.

## 1. Query decomposition

Planner trả structured JSON:

```json
{
  "goal": "Lập kế hoạch Đà Nẵng",
  "subtasks": ["Tìm điểm đến", "Kiểm tra thời tiết", "Tính ngân sách"],
  "tool_calls": [
    {
      "id": "step_1",
      "task": "Tìm điểm đến",
      "name": "search_tourism_knowledge",
      "arguments": {"query": "..."},
      "depends_on": []
    }
  ]
}
```

Giới hạn tối đa 5 subtasks/tool calls để tránh plan quá lớn. Tool name vẫn phải thuộc catalog lấy từ MCP.

## 2. Dependency-aware execution

Executor coi tool plan là một DAG nhỏ:

- Bước không có dependency chạy trước.
- Bước chỉ chạy khi toàn bộ dependency đã hoàn tất thành công.
- Nhiều bước cùng sẵn sàng được gửi trong một batch MCP.
- Dependency cha thất bại thì bước con bị đánh dấu failed, không gọi API vô ích.
- Cycle hoặc dependency không giải quyết được trở thành một tool error để validator xử lý.

Phase này chưa truyền động output bằng placeholder từ step trước vào arguments step sau. Dependency chỉ kiểm soát thứ tự và điều kiện thực thi; cách này dễ hiểu và tránh tạo một expression language quá sớm.

## 3. Validator

Validator hiện là deterministic code, không gọi thêm LLM. Nó kiểm tra:

- Mọi planned step có observation.
- Tool result có `success=true`.
- Tool thành công không trả nội dung rỗng.
- Draft answer không rỗng.

Ưu điểm: nhanh, dễ test, không phát sinh token cost và hành vi ổn định. Hạn chế: chưa đánh giá sâu tính đúng/sai về ngữ nghĩa của câu trả lời.

## 4. Self-correction có giới hạn

Khi validation thất bại, planner nhận:

- Plan trước.
- Tool results.
- Danh sách lỗi từ validator.

Planner có thể sửa arguments, đổi tool hoặc loại dependency lỗi. `AGENT_MAX_RETRIES=1` nghĩa là chỉ sửa một lần. Workflow không thể lặp vô hạn. Code còn hard-cap tối đa 2 retry ngay cả khi environment cấu hình lớn hơn.

Nếu retry vẫn thất bại, Agent trả lời dựa trên kết quả cuối cùng và nói rõ giới hạn. Nếu không tạo được draft, hệ thống trả một fallback message an toàn.

## Cấu hình

```env
AGENT_MAX_RETRIES=1
```

Giá trị đề xuất cho Phase 4 là `1`. Đặt `0` để tắt self-correction khi debug hoặc muốn giảm latency/cost.

## Test

```powershell
pytest -q tests/test_agent_planner.py tests/test_agent_reliability.py
pytest -q
```

Test reliability xác minh topological order, chặn dependent step khi parent lỗi và chỉ correction đúng một lần trước khi stream câu trả lời.
