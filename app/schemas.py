"""HTTP validation contracts. Reject unknown fields instead of silently ignoring them."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal['Hardware','Software','Network','Printer','Account Access','Other']
Priority = Literal['Low','Medium','High','Critical']
Status = Literal['Open','Assigned','In Progress','Resolved','Closed']
AssetType = Literal['Laptop','Desktop','Printer','Router','Switch']
AssetStatus = Literal['Available','Assigned','Reserved','Maintenance','Retired']


def clean(value: str) -> str:
    return ' '.join(value.split())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class LoginIn(StrictModel):
    username: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=1)


class UserCreate(StrictModel):
    username: str = Field(pattern=r'^[a-z0-9._-]{3,60}$')
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=180)
    role: Literal['Admin','Technician','Employee']
    password: str = Field(min_length=12, max_length=128)


class TicketCreate(StrictModel):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=3000)
    category: Category
    priority: Priority = 'Medium'
    affected_asset_id: int | None = Field(default=None, gt=0)
    employee_id: int | None = Field(default=None, gt=0)  # admin may file for employee


class TicketAssign(StrictModel):
    technician_id: int = Field(gt=0)


class TicketUpdate(StrictModel):
    status: Status
    resolution_details: str | None = Field(default=None, max_length=3000)


class TicketNote(StrictModel):
    note: str = Field(min_length=2, max_length=3000)


class AssetCreate(StrictModel):
    asset_tag: str = Field(pattern=r'^[A-Z0-9-]{3,40}$')
    serial_number: str = Field(min_length=3, max_length=100)
    device_type: AssetType
    manufacturer: str = Field(min_length=2, max_length=80)
    model: str = Field(min_length=2, max_length=120)
    operating_system: str | None = Field(default=None, max_length=100)
    purchase_date: date
    warranty_expiry: date | None = None
    notes: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def validate_dates(self):
        if self.purchase_date > date.today():
            raise ValueError('purchase_date cannot be in the future')
        if self.warranty_expiry and self.warranty_expiry < self.purchase_date:
            raise ValueError('warranty_expiry must be after purchase_date')
        return self


class AssetEdit(StrictModel):
    manufacturer: str | None = Field(default=None, min_length=2, max_length=80)
    model: str | None = Field(default=None, min_length=2, max_length=120)
    operating_system: str | None = Field(default=None, max_length=100)
    warranty_expiry: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    status: Literal['Available','Maintenance','Retired'] | None = None


class AssetAssign(StrictModel):
    employee_id: int = Field(gt=0)


class UserEdit(StrictModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=180)
    role: Literal['Admin','Technician','Employee'] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
