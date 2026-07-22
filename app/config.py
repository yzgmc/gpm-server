"""服务端配置。所有配置优先读环境变量，便于在 Windows 服务环境下注入。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from gpm_common import generate_secret, hash_password

# Nuitka 编译后存在该变量；用于区分打包 exe 与源码运行环境
_IS_COMPILED = "__compiled__" in dir()


def _default_data_dir() -> str:
    """数据目录：Nuitka 打包后用 exe 同级 data；源码运行用仓库根 data。"""
    if _IS_COMPILED:
        return str(Path(sys.executable).resolve().parent / "data")
    return str(Path(__file__).resolve().parent.parent / "data")


class Settings:
    host: str = os.getenv("GPM_HOST", "0.0.0.0")
    port: int = int(os.getenv("GPM_PORT", "8000"))
    data_dir: str = os.getenv("GPM_DATA_DIR", _default_data_dir())
    server_name: str = os.getenv("GPM_SERVER_NAME", "gpm-windows-server")
    server_kind: str = "windows-server"
    max_upload_mb: int = int(os.getenv("GPM_MAX_UPLOAD_MB", "4096"))
    # Push 模型：向 web-admin 上报心跳
    admin_url: str = os.getenv("GPM_ADMIN_URL", "")  # 留空则不上报
    public_base_url: str = os.getenv(
        "GPM_PUBLIC_BASE_URL", f"http://127.0.0.1:{port}"
    )  # 上报给后台的可访问地址
    reporter_interval: float = float(os.getenv("GPM_REPORTER_INTERVAL", "10"))
    reporter_id: str = os.getenv("GPM_REPORTER_ID", "")  # 留空则用 server_name

    # 登录认证
    _auth_secret_env: str = os.getenv("GPM_AUTH_SECRET", "")  # 留空则进程内随机生成
    _users_env: str = os.getenv("GPM_USERS", "")  # user1:hash1,user2:hash2；留空用默认 admin/admin123

    def __init__(self) -> None:
        # 兜底 secret：未配置则进程内随机生成（重启后所有 token 失效，仅适合开发）
        self._secret = self._auth_secret_env or generate_secret()
        self._users = self._parse_users(self._users_env)

    @staticmethod
    def _parse_users(raw: str) -> dict[str, str]:
        if raw:
            users: dict[str, str] = {}
            for pair in raw.split(","):
                pair = pair.strip()
                if ":" in pair:
                    u, h = pair.split(":", 1)
                    users[u.strip()] = h.strip()
            return users
        # 默认管理员：admin / admin123
        return {"admin": hash_password("admin123")}

    @property
    def auth_secret(self) -> str:
        return self._secret

    @property
    def users(self) -> dict[str, str]:
        return self._users

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def modpacks_dir(self) -> str:
        return os.path.join(self.data_dir, "modpacks")

    @property
    def mods_dir(self) -> str:
        return os.path.join(self.data_dir, "mods")


settings = Settings()
