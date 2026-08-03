from pydantic import BaseModel


class ProjetoOut(BaseModel):
    id: str
    name: str
    description: str | None
    product_type: str | None
    complexity: str | None
    status: str
    created_at: str
    updated_at: str
