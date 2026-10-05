from typing import Optional

from pydantic import BaseModel


class ProjetoOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    product_type: Optional[str]
    complexity: Optional[str]
    status: str
    created_at: str
    updated_at: str
