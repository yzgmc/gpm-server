# gpm-server

Game Push Manager **Windows 服务端**。负责接收整合包 / 模组上传，向客户端提供同步、下载 API，并向 web-admin 暴露状态接口。

> 与 `gpm-web-server` 功能完全一致，二者共享同一套 API 契约（来自 `gpm-common`）。区别仅在于部署位置：本仓库面向 Windows 服务器环境，可注册为 Windows 服务长期运行。

## 功能

- 整合包上传（multipart/form-data）、列表、下载、删除
- 模组上传、列表、下载、删除
- 客户端同步接口：一次返回所有整合包 + 模组 + 支持的游戏列表
- 服务端状态接口：供 web-admin 监测
- 基于游戏适配器的可扩展校验（已内置 Minecraft）

## 安装与运行

```bash
# 1. 先安装 gpm-common（参考 gpm-common 仓库）
pip install -e ../gpm-common

# 2. 安装本仓库依赖
pip install -r requirements.txt

# 3. 运行
python run.py
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

默认监听 `0.0.0.0:8000`，数据存储在 `./data`。可通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `GPM_HOST` | `0.0.0.0` | 监听地址 |
| `GPM_PORT` | `8000` | 监听端口 |
| `GPM_DATA_DIR` | `./data` | 数据存储目录 |
| `GPM_SERVER_NAME` | `gpm-windows-server` | 服务端名称（出现在 status 接口） |
| `GPM_MAX_UPLOAD_MB` | `4096` | 单文件上传上限（MB） |

## API 速览

所有路由前缀：`/api/v1`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sync` | 客户端同步：返回所有整合包、模组、游戏列表 |
| GET | `/games` | 支持的游戏列表 |
| GET | `/status` | 服务端状态（供 web-admin 监测） |
| GET | `/modpacks` | 整合包列表 |
| POST | `/modpacks` | 上传整合包（multipart） |
| GET | `/modpacks/{id}` | 整合包详情 |
| GET | `/modpacks/{id}/download` | 下载整合包文件 |
| DELETE | `/modpacks/{id}` | 删除整合包 |
| GET | `/mods` | 模组列表 |
| POST | `/mods` | 上传模组（multipart） |
| GET | `/mods/{id}` | 模组详情 |
| GET | `/mods/{id}/download` | 下载模组文件 |
| DELETE | `/mods/{id}` | 删除模组 |

详细字段见 `gpm-common` 的 `models.py`。

## 注册为 Windows 服务（可选）

推荐使用 [NSSM](https://nssm.cc/)：

```bat
nssm install GpmServer "C:\path\to\python.exe" "C:\path\to\gpm-server\run.py"
nssm start GpmServer
```

## 扩展新游戏

无需改动本仓库代码。只需在 `gpm-common` 中实现新适配器并注册，重启服务端即可生效。
