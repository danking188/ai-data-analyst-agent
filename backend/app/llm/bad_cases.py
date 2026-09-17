from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.orm.assistant_models import (
    AssistantFeedbackRow,
    AssistantMessageRow,
    LLMRunRow,
)

_SECRET = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,}|AKIA[0-9A-Z]{16})",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def collect_bad_cases(session: Session, *, limit: int = 200) -> list[dict[str, Any]]:
    feedback_rows = list(
        session.execute(
            select(AssistantFeedbackRow, AssistantMessageRow)
            .join(
                AssistantMessageRow,
                AssistantMessageRow.message_id == AssistantFeedbackRow.message_id,
            )
            .where(AssistantFeedbackRow.rating == "not_helpful")
            .order_by(AssistantFeedbackRow.created_at.desc())
            .limit(limit)
        )
    )
    failed_runs = list(
        session.scalars(
            select(LLMRunRow)
            .where(LLMRunRow.status == "failed")
            .order_by(LLMRunRow.created_at.desc())
            .limit(limit)
        )
    )
    cases = []
    for feedback, message in feedback_rows:
        parent = (
            session.get(AssistantMessageRow, message.parent_message_id)
            if message.parent_message_id
            else None
        )
        cases.append(
            {
                "case_id": f"feedback:{feedback.feedback_id}",
                "source": "user_feedback",
                "project_id": feedback.project_id,
                "message_id": feedback.message_id,
                "reason": feedback.reason,
                "comment": _redact(feedback.comment),
                "question_excerpt": _redact(parent.content if parent else None),
                "answer_excerpt": _redact(message.content),
                "created_at": feedback.created_at.isoformat(),
            }
        )
    cases.extend(
        {
            "case_id": f"run:{run.llm_run_id}",
            "source": "failed_run",
            "project_id": run.project_id,
            "message_id": run.message_id,
            "failure_category": (run.error_json or {}).get("category", "internal"),
            "error_code": (run.error_json or {}).get("code", "UNKNOWN"),
            "prompt_version": f"{run.prompt_name}@{run.prompt_version}",
            "model": run.model,
            "created_at": run.created_at.isoformat(),
        }
        for run in failed_runs
    )
    return sorted(cases, key=lambda item: str(item["created_at"]), reverse=True)[:limit]


def _redact(value: str | None) -> str | None:
    if value is None:
        return None
    compact = value.replace("\x00", " ")[:1000]
    return _EMAIL.sub("[REDACTED_EMAIL]", _SECRET.sub("[REDACTED_SECRET]", compact))
