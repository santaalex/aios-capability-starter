"""Starter runtime for __CAPABILITY_ID__.

Replace this placeholder and connect the capability through an explicit AIOS Core
adapter before publishing it. Merely building a Pack does not create a generic
remote-code plugin.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    json.load(sys.stdin)
    json.dump(
        {
            "schema_version": "1.0",
            "capability_id": "__CAPABILITY_ID__",
            "status": "NOT_IMPLEMENTED",
            "message": "请先实现能力并接入 AIOS Core 固定入口。",
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
