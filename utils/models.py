from pydantic import BaseModel, validator
from typing import List, Optional

class ExtractLinks(BaseModel):
    link_list: List[str]

class UserInput(BaseModel):
    user_input: str
    session_id: Optional[str] = None
    username: str
    
    @validator('user_input')
    def validate_message_length(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Message cannot be empty')
        if len(v) > 400:
            raise ValueError(f'Message too long. Maximum 400 characters, you have {len(v)}')
        return v

class RegisterRequest(BaseModel):
    username: str
    
    @validator('username')
    def validate_username(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Username cannot be empty')
        v = v.strip()
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if len(v) > 50:
            raise ValueError('Username must be 50 characters or less')
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        return v

class VerifyResponse(BaseModel):
    success: bool
    user_id: Optional[int] = None
    message: str