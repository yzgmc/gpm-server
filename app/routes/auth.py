"""认证路由：登录签发 JWT。

读操作（同步 / 下载 / 状态）对客户端保持开放，仅写操作（上传 / 删除）需要 token。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from gpm_common import AuthError, create_token, route, verify_password

from app.config import settings


router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    expires_in: int


@router.post(route("/auth/login"), response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    """校验用户名密码，签发 JWT。"""
    stored = settings.users.get(req.username)
    if not stored or not verify_password(req.password, stored):
        raise AuthError("用户名或密码错误", status_code=401)
    token = create_token({"sub": req.username, "role": "admin"}, settings.auth_secret)
    return LoginResponse(
        token=token,
        username=req.username,
        role="admin",
        expires_in=86400,
    )
