"""服务端配置。所有配置优先读环境变量，便于在 Windows 服务环境下注入。"""

from __future__ import annotations

import json
import os
import sys
import threading
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
    server_kind: str = "windows-server"
    max_upload_mb: int = int(os.getenv("GPM_MAX_UPLOAD_MB", "4096"))
    reporter_id: str = os.getenv("GPM_REPORTER_ID", "")  # 留空则用 server_name

    def __init__(self) -> None:
        # 兜底 secret：未配置则进程内随机生成（重启后所有 token 失效，仅适合开发）
        self._secret = os.getenv("GPM_AUTH_SECRET", "") or generate_secret()
        self._lock = threading.Lock()
        self._users_file = os.path.join(self.data_dir, "users.json")
        self._users = self._load_users()
        # 运行时可改的配置：从 server.json 读，环境变量优先级最高
        self._config_file = os.path.join(self.data_dir, "server.json")
        self._runtime = self._load_runtime_config()

    # ---------- 运行时配置持久化 ----------
    def _load_runtime_config(self) -> dict:
        """加载可热更新的配置（admin_url / server_name / public_base_url / reporter_interval）。
        优先级：环境变量 > server.json > 类默认值。"""
        saved: dict = {}
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
            except (OSError, json.JSONDecodeError):
                saved = {}
        return {
            "admin_url": os.getenv("GPM_ADMIN_URL") or saved.get("admin_url", ""),
            "server_name": os.getenv("GPM_SERVER_NAME") or saved.get("server_name", "gpm-windows-server"),
            "public_base_url": os.getenv("GPM_PUBLIC_BASE_URL") or saved.get("public_base_url", f"http://127.0.0.1:{self.port}"),
            "reporter_interval": float(os.getenv("GPM_REPORTER_INTERVAL") or saved.get("reporter_interval", 10.0)),
        }

    def _save_runtime_config(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._runtime, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @property
    def admin_url(self) -> str:
        return self._runtime["admin_url"]

    @property
    def server_name(self) -> str:
        return self._runtime["server_name"]

    @property
    def public_base_url(self) -> str:
        return self._runtime["public_base_url"]

    @property
    def reporter_interval(self) -> float:
        return self._runtime["reporter_interval"]

    def update_runtime(self, *, admin_url: str | None = None,
                       server_name: str | None = None,
                       public_base_url: str | None = None,
                       reporter_interval: float | None = None) -> dict:
        """更新运行时配置并持久化。返回更新后的完整配置。"""
        with self._lock:
            if admin_url is not None:
                self._runtime["admin_url"] = admin_url.strip()
            if server_name is not None and server_name.strip():
                self._runtime["server_name"] = server_name.strip()
            if public_base_url is not None:
                self._runtime["public_base_url"] = public_base_url.strip()
            if reporter_interval is not None and reporter_interval > 0:
                self._runtime["reporter_interval"] = float(reporter_interval)
            self._save_runtime_config()
            return dict(self._runtime)

    # ---------- 用户持久化 ----------
    def _load_users(self) -> dict[str, str]:
        """优先读 users.json；不存在则用默认 admin/admin123 并写入文件。"""
        if os.getenv("GPM_USERS"):
            # 显式指定则不持久化（只读环境变量）
            return self._parse_users_env(os.getenv("GPM_USERS", ""))
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, "r", encoding="utf-8") as f:
                    users = json.load(f)
                if users:
                    return users
            except (OSError, json.JSONDecodeError):
                pass
        # 默认管理员：admin / admin123
        default = {"admin": hash_password("admin123")}
        self._save_users(default)
        return default

    def _save_users(self, users: dict[str, str]) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self._users_file, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _parse_users_env(raw: str) -> dict[str, str]:
        users: dict[str, str] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                u, h = pair.split(":", 1)
                users[u.strip()] = h.strip()
        return users

    # ---------- 用户管理 API ----------
    @property
    def users(self) -> dict[str, str]:
        with self._lock:
            return dict(self._users)

    @property
    def auth_secret(self) -> str:
        return self._secret

    def add_user(self, username: str, password: str) -> None:
        with self._lock:
            if username in self._users:
                raise ValueError(f"用户已存在: {username}")
            self._users[username] = hash_password(password)
            self._save_users(self._users)

    def set_password(self, username: str, password: str) -> None:
        with self._lock:
            if username not in self._users:
                raise ValueError(f"用户不存在: {username}")
            self._users[username] = hash_password(password)
            self._save_users(self._users)

    def delete_user(self, username: str) -> None:
        with self._lock:
            if username not in self._users:
                raise ValueError(f"用户不存在: {username}")
            if len(self._users) <= 1:
                raise ValueError("至少保留一个用户，禁止删除最后一个用户")
            del self._users[username]
            self._save_users(self._users)

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
