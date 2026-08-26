from typing import Any

from sqlalchemy.orm import Session

from app.models.tool_call_log import ToolCallLog


class ToolCallLogRepository:
    """
    Persistence layer for tool execution logs.
    """

    def create(
        self,
        db: Session,
        *,
        user_id: int,
        workspace_id: int,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any = None,
        status: str,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> ToolCallLog:

        log = ToolCallLog(
            user_id=user_id,
            workspace_id=workspace_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            status=status,
            error=error,
            duration_ms=duration_ms,
        )

        db.add(log)
        db.commit()
        db.refresh(log)

        return log
