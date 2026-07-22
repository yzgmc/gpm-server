"""客户端同步路由：一次返回所有整合包 + 模组 + 支持的游戏列表。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from gpm_common import API_VERSION, GameAdapterRegistry, SyncResponse, route

from app import storage
from app.config import settings


router = APIRouter()


@router.get(route("/sync"))
def sync():
    return SyncResponse(
        protocol_version=API_VERSION,
        server_name=settings.server_name,
        modpacks=[m.model_dump() for m in storage.list_modpacks()],
        mods=[m.model_dump() for m in storage.list_mods()],
        games=[g.model_dump() for g in GameAdapterRegistry.all_games()],
        server_time=datetime.now(timezone.utc),
    ).model_dump()
