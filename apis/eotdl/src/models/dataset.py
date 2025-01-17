from pydantic import BaseModel, validator
from datetime import datetime
from typing import List
import re
from ..errors import NameCharsValidationError, NameLengthValidationError, DescriptionLengthValidationError

def validate_name(name: str, regex: str = "^[^a-zA-Z]{1}|[^a-zA-Z0-9-]", max_length: int = 15, min_length: int = 3) -> str:
    if re.findall(regex, name):
        raise NameCharsValidationError()
    if len(name) > max_length or len(name) < min_length:
        raise NameLengthValidationError(max_length, min_length)
    return name

def validate_description(description: str, max_length: int = 50, min_length: int = 5) -> str:
    if len(description) > max_length or len(description) < min_length:
        raise DescriptionLengthValidationError(max_length, min_length)
    return description

class Dataset(BaseModel):
    uid: str
    id: str
    name: str
    description: str
    tags: List[str] = []
    createdAt: datetime = datetime.now()
    updatedAt: datetime = datetime.now()
    likes: int = 0
    downloads: int = 0

    @validator('name')
    def check_name_is_valid(cls, name):
        if name is not None:
            assert validate_name(name) == name
        return name
    
    @validator('description')
    def check_description_is_valid(cls, description):
        if description is not None:
            assert validate_description(description) == description
        return description