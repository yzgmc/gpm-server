"""服务端 GUI 启动入口：弹出 PySide6 管理窗口，后台线程运行 uvicorn 服务。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtWidgets import QApplication

from app.config import settings
from app.gui import ServerThread, ServerWindow


# 全局 QSS：按钮 hover/press 状态、输入框 focus 高亮、统一观感
GLOBAL_QSS = """
QWidget { font-family: "Microsoft YaHei", "Segoe UI", -apple-system, sans-serif; }
QMainWindow { background: #f1f5f9; }

QPushButton {
    background: #3b82f6; color: #fff; border: none; border-radius: 5px;
    padding: 6px 16px; font-weight: 600;
}
QPushButton:hover { background: #2563eb; }
QPushButton:pressed { background: #1d4ed8; }
QPushButton:disabled { background: #94a3b8; }
QPushButton:focus { outline: none; }

QLineEdit, QComboBox, QSpinBox {
    background: #fff; border: 1px solid #cbd5e1; border-radius: 5px;
    padding: 6px 10px; selection-background-color: #3b82f6;
}
QLineEdit:focus, QComboBox:focus { border-color: #3b82f6; }

QTabWidget::pane { border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; }
QTabBar::tab {
    background: transparent; color: #64748b; padding: 8px 18px;
    border: 1px solid transparent; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QTabBar::tab:selected { color: #2563eb; font-weight: 600; background: #fff; border-color: #e2e8f0; }
QTabBar::tab:hover:!selected { color: #3b82f6; }

QTableWidget { background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; gridline-color: #f1f5f9; }
QHeaderView::section { background: #f1f5f9; color: #64748b; border: none; padding: 8px; font-weight: 600; }

QStatusBar { background: #0f172a; color: #cbd5e1; }
QLabel { color: #0f172a; }
"""


def main() -> None:
    # 先在后台线程启动 uvicorn 服务
    server_thread = ServerThread()
    server_thread.start()

    # 启动 GUI 事件循环
    app = QApplication(sys.argv)
    app.setApplicationName("GPM 服务端管理")
    app.setStyleSheet(GLOBAL_QSS)
    window = ServerWindow(server_thread)
    window.show()

    # 窗口淡入动画（opacity 0 → 1，300ms 缓出）
    window.setWindowOpacity(0.0)
    fade = QPropertyAnimation(window, b"windowOpacity", window)
    fade.setDuration(300)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    QTimer.singleShot(30, fade.start)

    # 窗口关闭时停止服务并退出
    app.lastWindowClosed.connect(lambda: server_thread.stop_server())
    exit_code = app.exec()
    server_thread.stop_server()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
