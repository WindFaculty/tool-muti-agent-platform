# CONTEXT_SUMMARY

## Root Workflow
- `AGENTS.md` là file rule gốc có hiệu lực toàn repo.
- `tasks/task-queue.md` theo dõi lane AI có thể làm trực tiếp.
- `tasks/done.md` lưu mốc đã hoàn thành có bằng chứng.
- `lessons.md` lưu lesson ngắn để tránh lặp lỗi cũ.

## local-backend
- FastAPI backend cho chat, task, health, speech, stream.
- `AssistantOrchestrator` điều phối route, memory, task actions, TTS, stream events.
- `ActionValidator` biến câu người dùng thành intent an toàn và factual context.
- `PlannerService` tạo summary deterministic từ task data thật.
- `FastResponseService` và `PlanningService` gọi LLM cho fast/deep/hybrid route.
- `MemoryService` giữ recent messages, rolling summary, long-term memory đơn giản.
- `route_logs` đã lưu `token_usage`, route, provider, latency, fallback.

## unity-client
- Unity app là shell chính cho assistant desktop.
- Nhận chat, stream events, reminder, subtitle, avatar state từ backend.
- PlayMode/EditMode tests đã tồn tại cho app flow và UI behavior.

## agent-platform
- Subproject tùy chọn, không phải runtime chính của assistant hiện tại.
- Có prompt files riêng nhưng không nên dùng làm source of truth cho backend.

## Current Token Strategy
- Không gửi full project hoặc raw multi-file context nếu summary đủ.
- Với runtime backend, ưu tiên factual summary, top-N items, notes excerpt, memory excerpt.
- Giữ REST và WebSocket contract ổn định; đo hiệu quả qua `token_usage`.
