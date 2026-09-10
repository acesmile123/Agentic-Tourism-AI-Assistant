# Tourism evaluation dataset

`datasets/tourism_ai_eval.jsonl` là seed dataset cho Phase 5, bao phủ knowledge, food, itinerary, budget, weather, map, freshness, complex planning và direct response.

Mỗi dòng có:

- `id`: định danh ổn định, không tái sử dụng.
- `query`: câu hỏi thực tế bằng tiếng Việt.
- `expected_tools`: tool bắt buộc để đánh giá routing.
- `relevant_targets`: keyword/metadata label dùng cho Recall@K và MRR.
- `reference_answer`: rubric cho generation judge, không được coi là retrieval evidence.
- `notes`: lý do case tồn tại hoặc điều kiện API key.

Trước khi dùng làm release gate, hãy chạy dataset trên collection thật và review thủ công `relevant_targets`. Khi phát hiện failure production trong Langfuse, ẩn dữ liệu cá nhân rồi thêm thành case mới. Không thay expected label chỉ để làm metric đẹp hơn.
