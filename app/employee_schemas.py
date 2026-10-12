"""Strict browser/API contracts for mock employee lifecycle."""
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Department = Literal['Claims','Operations','Finance','HR','IT']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class OnboardIn(Strict):
    full_name: str = Field(min_length=5, max_length=120)
    department: Department
    job_title: str = Field(min_length=3, max_length=120)
    manager_name: str = Field(min_length=5, max_length=120)
    start_date: date
    required_groups: list[str] = Field(default_factory=list, max_length=4)
    device_requirements: list[Literal['Laptop','Monitor','Headset']] = Field(default_factory=list, max_length=3)

    @field_validator('full_name', 'manager_name')
    @classmethod
    def name_format(cls, value):
        cleaned = ' '.join(value.split())
        if len(cleaned.split()) < 2 or not all(c.isalpha() or c in " -'" for c in cleaned):
            raise ValueError('Use first and surname (letters, spaces, apostrophes or hyphens)')
        return cleaned

    @field_validator('required_groups', 'device_requirements')
    @classmethod
    def unique_options(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('Duplicate group or device requirement')
        return values

    @field_validator('start_date')
    @classmethod
    def reasonable_start(cls, value):
        if not date.today() - timedelta(days=365) <= value <= date.today() + timedelta(days=730):
            raise ValueError('Start date must be within one year past or two years future')
        return value


class OffboardIn(Strict):
    last_working_date: date
    reason: str = Field(min_length=10, max_length=500)


class ApprovalIn(Strict):
    confirm: Literal[True]
    comment: str = Field(min_length=10, max_length=500)
