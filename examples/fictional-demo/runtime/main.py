"""Fictional, customer-neutral Starter example."""

from __future__ import annotations

import json
import sys

CAPABILITY_ID = "fictional-fastener-summary"


def summarize(request: dict) -> dict:
    items = request["input"]["items"]
    total_items = sum(item["quantity"] for item in items)
    total_length = sum(item["quantity"] * item["nominal_length_mm"] for item in items)
    return {
        "schema_version": "1.0",
        "capability_id": CAPABILITY_ID,
        "status": "COMPLETED",
        "message": f"已汇总 {total_items} 个虚构紧固件。",
        "total_items": total_items,
        "total_nominal_length_mm": total_length,
    }


def main() -> int:
    request = json.load(sys.stdin)
    json.dump(summarize(request), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
