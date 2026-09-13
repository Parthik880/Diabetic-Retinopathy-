import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


class PatientInput(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    patientIdNumber: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    age: int = Field(ge=0, le=130)
    gender: Literal['Female', 'Male', 'Other']
    phone: str | None = None
    email: str | None = None

    @field_validator('name', 'patientIdNumber', 'id')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Patient name and identifiers are required.')
        return value.strip()

    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        value = re.sub(r'[\s().-]', '', value or '')
        if value and not re.fullmatch(r'\+?[0-9]{7,15}', value):
            raise ValueError('Phone must contain 7–15 digits and an optional leading +.')
        return value or None

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        value = (value or '').strip()
        if value and (len(value) > 254 or not re.fullmatch(r'[^\s@?&#%]+@[^\s@?&#%]+\.[^\s@?&#%]+', value)):
            raise ValueError('Enter a valid email address.')
        return value or None


class SyncSettingsInput(BaseModel):
    automatic: bool = False
    patient_metadata: bool = True
    reports: bool = True
    retinal_images: bool = False


class ClearInput(BaseModel):
    categories: list[Literal['temporary', 'artifacts', 'reports', 'images', 'history']] = Field(min_length=1)
    acknowledged: bool = False
    confirmation: str = ''
