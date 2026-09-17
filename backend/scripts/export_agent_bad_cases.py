from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.llm.bad_cases import collect_bad_cases  # noqa: E402
from app.persistence.session import get_database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export redacted Agent bad cases")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 1000:
        parser.error("--limit must be between 1 and 1000")
    session = get_database().session()
    try:
        cases = collect_bad_cases(session, limit=args.limit)
    finally:
        session.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"schema_version": 1, "cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"exported {len(cases)} redacted cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
