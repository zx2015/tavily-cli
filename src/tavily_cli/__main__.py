"""`python -m tavily_cli` 入口（与 .venv/bin/tavily-cli 等价）。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
