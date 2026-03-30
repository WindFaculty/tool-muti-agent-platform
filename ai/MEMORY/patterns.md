# Patterns

- Planner -> Executor -> Reviewer, mỗi agent chỉ nhận context đủ dùng cho phần việc của mình.
- Runtime prompt assembly nên đi qua một context builder deterministic dùng chung cho fast/deep/hybrid routes.
- Context lớn nên nén bằng field pruning, top-N selection, word caps, line caps, duplicate removal.
