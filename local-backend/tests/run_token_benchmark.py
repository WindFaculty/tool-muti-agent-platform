from __future__ import annotations

import json
from pathlib import Path
from tempfile import mkdtemp

from token_benchmark_support import run_token_benchmark


if __name__ == "__main__":
    temp_dir = Path(mkdtemp(prefix="token-benchmark-"))
    output = run_token_benchmark(temp_dir)
    print(json.dumps(output, ensure_ascii=False, indent=2))
