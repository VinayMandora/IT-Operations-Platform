"""Strict API input limits for Task 5; no arbitrary shell commands or host scans."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['IPConfig','DNS','TCP']
    target: str = Field(default='localhost', min_length=1, max_length=160)
    port: int | None = Field(default=None, ge=1, le=65535)

class IVRUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    menu_name: str = Field(min_length=2, max_length=60, pattern=r'^[a-zA-Z][a-zA-Z0-9_-]*$')
    digit: str = Field(pattern=r'^[0-9]$')
    label: str = Field(min_length=2, max_length=120)
    destination_type: Literal['Extension','Queue','Voicemail']
    destination: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    enabled: bool = True

class IVRSimulate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    menu_name: str = Field(min_length=2, max_length=60)
    digit: str = Field(pattern=r'^[0-9]$')

class ExportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tables: list[Literal['claims','tickets','assets','call_logs']] = Field(min_length=1, max_length=4)

class FailureRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=8, max_length=500)
