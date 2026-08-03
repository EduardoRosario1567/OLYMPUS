from typing import Any
from pydantic import BaseModel


class LogOut(BaseModel):
    id: str
    project_id: str | None
    execution_id: str | None
    decision_record_id: str | None
    level: str
    event_type: str
    message: str
    metadata: dict[str, Any] | str
    created_at: str
