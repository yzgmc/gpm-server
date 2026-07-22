"""服务端配置。所有配置优先读环境变量，便于在 Windows 服务环境下注入。"""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    host: str = os.getenv("GPM_HOST", "0.0.0.0")
    port: int = int(os.getenv("GPM_PORT", "8000"))
    data_dir: str = os.getenv("GPM_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
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
