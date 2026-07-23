"""服务端 GUI 启动入口：弹出 PySide6 管理窗口，后台线程运行 uvicorn 服务。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import settings
from app.gui import ServerThread, ServerWindow


def main() -> None:
    # 先在后台线程启动 uvicorn 服务
    server_thread = ServerThread()
    server_thread.start()

    # 启动 GUI 事件循环
    app = QApplication(sys.argv)
    app.setApplicationName("GPM 服务端管理")
    window = ServerWindow(server_thread)
    window.show()
    # 窗口关闭时停止服务并退出
    app.lastWindowClosed.connect(lambda: server_thread.stop_server())
    exit_code = app.exec()
    server_thread.stop_server()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
