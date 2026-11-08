from typing import Any, Optional
from pydantic import BaseModel, Field

class FieldSpec(BaseModel):
    name: str = ''
    description: str = ''
    primary: bool = False
    type: Optional[str] = None

class InputSchema(BaseModel):
    name: str = 'custom'
    description: str = ''
    fields: dict[str, FieldSpec]

class FieldValue(BaseModel):
    value: Any = None
    citation: str = ''
    confidence: float = Field(default=0.0, ge=0, le=1)
    page_numbers: Optional[list[int]] = None
    source_locations: Optional[list[str]] = None

class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    updated_at: str
    stage: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[dict] = None
