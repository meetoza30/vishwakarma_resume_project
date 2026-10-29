from typing import Optional
from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "recruiter"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str
