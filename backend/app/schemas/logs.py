from typing import Any, Optional, Union
from pydantic import BaseModel


class LogOut(BaseModel):
    id: str
    project_id: Optional[str]
    execution_id: Optional[str]
    decision_record_id: Optional[str]
    level: str
    event_type: str
    message: str
    metadata: Union[dict[str, Any], str]
    created_at: str
