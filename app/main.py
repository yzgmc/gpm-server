"""FastAPI 应用入口。"""

from __future__ import annotations

# 导入 gpm_common 即触发内置适配器注册（minecraft 等）
import gpm_common  # noqa: F401
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gpm_common import API_VERSION, GamePushError

from app.config import settings
from app.reporter import start_reporter, stop_reporter
from app.routes import games, mods, modpacks, status, sync
from app.server_info import server_info


def create_app() -> FastAPI:
    app = FastAPI(
        title="Game Push Manager - Windows Server",
        version=API_VERSION,
        description="接收整合包/模组上传，向客户端提供同步与下载 API。",
    )

    # 允许跨域，便于 web-admin 与客户端调用
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _count_requests(request: Request, call_next):
        server_info.record_request()
        return await call_next(request)

    @app.exception_handler(GamePushError)
    async def _handle_push_error(_: Request, exc: GamePushError):
        server_info.record_error()
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    app.include_router(games.router)
    app.include_router(status.router)
    app.include_router(sync.router)
    app.include_router(modpacks.router)
    app.include_router(mods.router)

    @app.on_event("startup")
    def _start_reporter():
        # Push 模型：启动后台线程，定期向 web-admin 上报心跳
        start_reporter()

    @app.on_event("shutdown")
    def _stop_reporter():
        stop_reporter()

    @app.get("/")
    def root():
        return {
            "service": "gpm-server",
            "kind": settings.server_kind,
            "protocol_version": API_VERSION,
            "docs": "/docs",
            "reporting_to": settings.admin_url or None,
        }

    return app


app = create_app()
