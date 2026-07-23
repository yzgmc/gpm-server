"""服务端 PySide6 GUI 窗口。

启动时弹出窗口，后台线程运行 uvicorn 服务；窗口内展示运行状态、整合包/模组列表，
支持上传/删除/编辑/上下架，并可管理用户、修改密码。写操作需先登录获取 token。
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import settings


# ---------- 工具 ----------
def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    v, i = float(n), 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}" if v < 10 else f"{int(v)} {units[i]}"


def fmt_duration(sec: float | None) -> str:
    if sec is None:
        return "—"
    d = int(sec // 86400)
    h = int((sec % 86400) // 3600)
    m = int((sec % 3600) // 60)
    if d > 0:
        return f"{d}天{h}时"
    if h > 0:
        return f"{h}时{m}分"
    return f"{m}分"


def build_multipart(fields: dict[str, str], file_path: str) -> tuple[bytes, str]:
    """构造 multipart/form-data 请求体，返回 (body, content_type)。"""
    boundary = "----gpm_boundary_" + os.urandom(8).hex()
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        parts.append(v.encode() + b"\r\n")
    fname = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# ---------- 通用 HTTP 请求工作线程 ----------
class ApiWorker(QThread):
    """在工作线程中执行 HTTP 请求，通过信号返回结果。"""

    done = Signal(bool, object)

    def __init__(self, method: str, path: str, token: str = "",
                 data: bytes | None = None, headers: dict | None = None) -> None:
        super().__init__()
        self.method = method
        self.path = path
        self.token = token
        self.data = data
        self.headers = headers or {}

    def run(self) -> None:
        base = f"http://127.0.0.1:{settings.port}{self.path}"
        req_headers = dict(self.headers)
        if self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(base, data=self.data, method=self.method,
                                     headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                self.done.emit(True, json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8", errors="replace"))
                msg = err.get("error") or err.get("detail") or str(e)
            except Exception:
                msg = f"HTTP {e.code}"
            self.done.emit(False, msg)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, str(e))


# ---------- 登录对话框 ----------
class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("服务端管理登录")
        self.setFixedSize(320, 180)
        self.token: str | None = None
        self._worker: ApiWorker | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.user_edit = QLineEdit("admin")
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        form.addRow("用户名:", self.user_edit)
        form.addRow("密码:", self.pass_edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("登录")
        self.login_btn.clicked.connect(self._on_login)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self.login_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        hint = QLabel("默认 admin / admin123")
        hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def _on_login(self) -> None:
        user = self.user_edit.text().strip()
        pwd = self.pass_edit.text()
        if not user or not pwd:
            return
        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")
        body = json.dumps({"username": user, "password": pwd}).encode()
        self._worker = ApiWorker("POST", "/api/v1/auth/login", data=body,
                                 headers={"Content-Type": "application/json"})
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, result: Any) -> None:
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        if ok and isinstance(result, dict) and result.get("token"):
            self.token = result["token"]
            self.accept()
        else:
            QMessageBox.warning(self, "登录失败", str(result))


# ---------- 整合包元数据对话框（上传 / 编辑通用） ----------
class ModpackMetaDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, existing: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑整合包" if existing else "整合包信息")
        self.setFixedWidth(340)
        form = QFormLayout(self)
        self.name = QLineEdit(); self.name.setPlaceholderText("TestPack")
        self.version = QLineEdit(); self.version.setPlaceholderText("1.0")
        self.game = QLineEdit("minecraft")
        self.game_version = QLineEdit(); self.game_version.setPlaceholderText("1.20")
        self.loader = QComboBox(); self.loader.addItems(["vanilla", "forge", "fabric", "quilt"])
        self.loader_ver = QLineEdit(); self.loader_ver.setPlaceholderText("可选")
        self.desc = QLineEdit(); self.desc.setPlaceholderText("可选")
        self.enabled = QCheckBox("上架（取消勾选则下架，客户端同步不到）")
        self.enabled.setChecked(True)
        if existing:
            self.name.setText(existing.get("name", ""))
            self.version.setText(existing.get("version", ""))
            self.game.setText(existing.get("game", "minecraft"))
            self.game_version.setText(existing.get("game_version", ""))
            self.loader.setCurrentText(existing.get("mod_loader", "vanilla"))
            self.loader_ver.setText(existing.get("mod_loader_version") or "")
            self.desc.setText(existing.get("description", ""))
            self.enabled.setChecked(existing.get("enabled", True))
        form.addRow("名称*:", self.name)
        form.addRow("版本*:", self.version)
        form.addRow("游戏*:", self.game)
        form.addRow("游戏版本*:", self.game_version)
        form.addRow("加载器:", self.loader)
        form.addRow("加载器版本:", self.loader_ver)
        form.addRow("描述:", self.desc)
        form.addRow(self.enabled)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict[str, Any] | None:
        if not (self.name.text().strip() and self.version.text().strip()
                and self.game.text().strip() and self.game_version.text().strip()):
            return None
        return {
            "name": self.name.text().strip(),
            "version": self.version.text().strip(),
            "game": self.game.text().strip(),
            "game_version": self.game_version.text().strip(),
            "mod_loader": self.loader.currentText(),
            "mod_loader_version": self.loader_ver.text().strip(),
            "description": self.desc.text().strip(),
            "enabled": self.enabled.isChecked(),
        }


# ---------- 模组元数据对话框（上传 / 编辑通用） ----------
class ModMetaDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, existing: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑模组" if existing else "模组信息")
        self.setFixedWidth(340)
        form = QFormLayout(self)
        self.name = QLineEdit(); self.name.setPlaceholderText("ExampleMod")
        self.version = QLineEdit(); self.version.setPlaceholderText("1.0")
        self.game = QLineEdit("minecraft")
        self.desc = QLineEdit(); self.desc.setPlaceholderText("可选")
        self.enabled = QCheckBox("上架")
        self.enabled.setChecked(True)
        if existing:
            self.name.setText(existing.get("name", ""))
            self.version.setText(existing.get("version", ""))
            self.game.setText(existing.get("game", "minecraft"))
            self.desc.setText(existing.get("description", ""))
            self.enabled.setChecked(existing.get("enabled", True))
        form.addRow("名称*:", self.name)
        form.addRow("版本*:", self.version)
        form.addRow("游戏*:", self.game)
        form.addRow("描述:", self.desc)
        form.addRow(self.enabled)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict[str, Any] | None:
        if not (self.name.text().strip() and self.version.text().strip()
                and self.game.text().strip()):
            return None
        return {
            "name": self.name.text().strip(),
            "version": self.version.text().strip(),
            "game": self.game.text().strip(),
            "description": self.desc.text().strip(),
            "enabled": self.enabled.isChecked(),
        }


# ---------- 改密码对话框 ----------
class ChangePasswordDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("修改密码")
        self.setFixedWidth(340)
        self._worker: ApiWorker | None = None
        form = QFormLayout(self)
        self.old_pwd = QLineEdit(); self.old_pwd.setEchoMode(QLineEdit.Password)
        self.new_pwd = QLineEdit(); self.new_pwd.setEchoMode(QLineEdit.Password)
        self.new_pwd.setPlaceholderText("至少6位")
        self.confirm = QLineEdit(); self.confirm.setEchoMode(QLineEdit.Password)
        form.addRow("原密码:", self.old_pwd)
        form.addRow("新密码:", self.new_pwd)
        form.addRow("确认新密码:", self.confirm)
        self.msg = QLabel("")
        self.msg.setStyleSheet("color: #ef4444; font-size: 12px;")
        form.addRow(self.msg)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _on_ok(self) -> None:
        if self.new_pwd.text() != self.confirm.text():
            self.msg.setText("两次新密码不一致")
            return
        if len(self.new_pwd.text()) < 6:
            self.msg.setText("新密码至少 6 位")
            return
        self.msg.setText("")

    def build_request(self, token: str) -> tuple[ApiWorker, str]:
        body = json.dumps({
            "old_password": self.old_pwd.text(),
            "new_password": self.new_pwd.text(),
        }).encode()
        w = ApiWorker("PUT", "/api/v1/auth/password", token=token, data=body,
                      headers={"Content-Type": "application/json"})
        return w, "改密码请求已发出"


# ---------- 添加用户对话框 ----------
class AddUserDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加用户")
        self.setFixedWidth(320)
        form = QFormLayout(self)
        self.username = QLineEdit()
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("至少6位")
        form.addRow("用户名:", self.username)
        form.addRow("密码:", self.password)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> tuple[str, str] | None:
        if not self.username.text().strip() or len(self.password.text()) < 6:
            return None
        return self.username.text().strip(), self.password.text()


# ---------- 上传工作线程 ----------
class UploadWorker(QThread):
    done = Signal(bool, object)

    def __init__(self, path: str, token: str, fields: dict[str, str], file_path: str) -> None:
        super().__init__()
        self.path = path
        self.token = token
        self.fields = fields
        self.file_path = file_path

    def run(self) -> None:
        try:
            body, ctype = build_multipart(self.fields, self.file_path)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"读取文件失败: {e}")
            return
        base = f"http://127.0.0.1:{settings.port}{self.path}"
        headers = {"Content-Type": ctype}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(base, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                b = resp.read().decode("utf-8", errors="replace")
                self.done.emit(True, json.loads(b) if b else {})
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8", errors="replace"))
                msg = err.get("error") or str(e)
            except Exception:
                msg = f"HTTP {e.code}"
            self.done.emit(False, msg)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, str(e))


# ---------- 主窗口 ----------
class ServerWindow(QMainWindow):
    def __init__(self, server_thread: "ServerThread") -> None:
        super().__init__()
        self.server_thread = server_thread
        self.token: str | None = None
        self.current_user: str = ""
        self._workers: list = []
        self.setWindowTitle("GPM 服务端管理")
        self.resize(950, 640)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 顶部状态栏
        top = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #eab308; font-size: 18px;")
        self.status_label = QLabel("服务启动中...")
        self.addr_label = QLabel(f"http://127.0.0.1:{settings.port}")
        self.addr_label.setStyleSheet("color: #2563eb;")
        top.addWidget(self.status_dot)
        top.addWidget(self.status_label)
        top.addWidget(QLabel("地址:"))
        top.addWidget(self.addr_label)
        top.addStretch()
        self.open_web_btn = QPushButton("打开网页管理")
        self.open_web_btn.clicked.connect(self._open_web)
        self.change_pwd_btn = QPushButton("改密码")
        self.change_pwd_btn.clicked.connect(self._change_password)
        self.login_btn = QPushButton("登录")
        self.login_btn.clicked.connect(self._show_login)
        top.addWidget(self.open_web_btn)
        top.addWidget(self.change_pwd_btn)
        top.addWidget(self.login_btn)
        root.addLayout(top)

        # 状态卡片
        card_row = QHBoxLayout()
        self.stat_labels: dict[str, QLabel] = {}
        for key, title in [("name", "服务名称"), ("uptime", "运行时长"),
                           ("modpacks", "整合包"), ("mods", "模组"), ("storage", "存储占用")]:
            box = QVBoxLayout()
            t = QLabel(title); t.setStyleSheet("color: #64748b; font-size: 12px;")
            v = QLabel("—"); v.setStyleSheet("font-size: 16px; font-weight: 600;")
            v.setWordWrap(True)
            box.addWidget(t); box.addWidget(v)
            wrap = QWidget(); wrap.setLayout(box)
            wrap.setStyleSheet("background: #fff; border-radius: 6px; padding: 8px;")
            card_row.addWidget(wrap)
            self.stat_labels[key] = v
        root.addLayout(card_row)

        # 选项卡
        self.tabs = QTabWidget()
        # 整合包
        self.modpack_table = self._make_table(["ID", "名称", "版本", "游戏", "游戏版本", "加载器", "大小", "状态"])
        mp_tab = QWidget(); mp_layout = QVBoxLayout(mp_tab)
        mp_btns = QHBoxLayout()
        self.mp_upload_btn = QPushButton("上传整合包"); self.mp_upload_btn.clicked.connect(self._upload_modpack)
        self.mp_edit_btn = QPushButton("编辑选中"); self.mp_edit_btn.clicked.connect(self._edit_modpack)
        self.mp_toggle_btn = QPushButton("上架/下架"); self.mp_toggle_btn.clicked.connect(self._toggle_modpack)
        self.mp_del_btn = QPushButton("删除选中"); self.mp_del_btn.clicked.connect(self._delete_modpack)
        self.mp_refresh_btn = QPushButton("刷新"); self.mp_refresh_btn.clicked.connect(self._load_modpacks)
        for b in (self.mp_upload_btn, self.mp_edit_btn, self.mp_toggle_btn, self.mp_del_btn):
            mp_btns.addWidget(b)
        mp_btns.addStretch(); mp_btns.addWidget(self.mp_refresh_btn)
        mp_layout.addLayout(mp_btns); mp_layout.addWidget(self.modpack_table)
        self.tabs.addTab(mp_tab, "整合包管理")

        # 模组
        self.mod_table = self._make_table(["ID", "名称", "版本", "游戏", "大小", "状态"])
        mod_tab = QWidget(); mod_layout = QVBoxLayout(mod_tab)
        mod_btns = QHBoxLayout()
        self.mod_upload_btn = QPushButton("上传模组"); self.mod_upload_btn.clicked.connect(self._upload_mod)
        self.mod_edit_btn = QPushButton("编辑选中"); self.mod_edit_btn.clicked.connect(self._edit_mod)
        self.mod_toggle_btn = QPushButton("上架/下架"); self.mod_toggle_btn.clicked.connect(self._toggle_mod)
        self.mod_del_btn = QPushButton("删除选中"); self.mod_del_btn.clicked.connect(self._delete_mod)
        self.mod_refresh_btn = QPushButton("刷新"); self.mod_refresh_btn.clicked.connect(self._load_mods)
        for b in (self.mod_upload_btn, self.mod_edit_btn, self.mod_toggle_btn, self.mod_del_btn):
            mod_btns.addWidget(b)
        mod_btns.addStretch(); mod_btns.addWidget(self.mod_refresh_btn)
        mod_layout.addLayout(mod_btns); mod_layout.addWidget(self.mod_table)
        self.tabs.addTab(mod_tab, "模组管理")

        # 用户管理
        user_tab = QWidget(); user_layout = QVBoxLayout(user_tab)
        user_btns = QHBoxLayout()
        self.user_add_btn = QPushButton("添加用户"); self.user_add_btn.clicked.connect(self._add_user)
        self.user_del_btn = QPushButton("删除选中"); self.user_del_btn.clicked.connect(self._del_user)
        self.user_refresh_btn = QPushButton("刷新"); self.user_refresh_btn.clicked.connect(self._load_users)
        user_btns.addWidget(self.user_add_btn); user_btns.addWidget(self.user_del_btn)
        user_btns.addStretch(); user_btns.addWidget(self.user_refresh_btn)
        user_layout.addLayout(user_btns)
        self.user_list = QListWidget()
        user_layout.addWidget(self.user_list)
        self.tabs.addTab(user_tab, "用户管理")
        root.addWidget(self.tabs)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪。写操作需先登录。")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_status)
        self.timer.start(10000)
        QTimer.singleShot(1500, self._refresh_status)
        QTimer.singleShot(1800, self._load_modpacks)
        QTimer.singleShot(1800, self._load_mods)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    # --- 登录 ---
    def _show_login(self) -> None:
        dlg = LoginDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.token:
            self.token = dlg.token
            self.current_user = dlg.user_edit.text().strip()
            self.login_btn.setText(f"已登录: {self.current_user}")
            self.login_btn.setEnabled(False)
            self.statusBar().showMessage("登录成功", 3000)

    def _require_token(self) -> str | None:
        if not self.token:
            QMessageBox.information(self, "请先登录", "写操作需要先登录。")
            self._show_login()
        return self.token

    def _open_web(self) -> None:
        QDesktopServices.openUrl(QUrl(f"http://127.0.0.1:{settings.port}/admin"))

    def _change_password(self) -> None:
        token = self._require_token()
        if not token:
            return
        dlg = ChangePasswordDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        w, _ = dlg.build_request(token)

        def _cb(ok: bool, result: Any) -> None:
            if ok:
                QMessageBox.information(self, "成功", "密码已修改，请重新登录")
                self.token = None
                self.current_user = ""
                self.login_btn.setText("登录")
                self.login_btn.setEnabled(True)
            else:
                QMessageBox.warning(self, "失败", str(result))

        w.done.connect(_cb)
        self._workers.append(w)
        w.start()

    # --- 刷新状态 ---
    def _refresh_status(self) -> None:
        w = ApiWorker("GET", "/api/v1/status")
        w.done.connect(self._on_status)
        self._workers.append(w)
        w.start()

    def _on_status(self, ok: bool, result: Any) -> None:
        if not ok or not isinstance(result, dict):
            self.status_dot.setStyleSheet("color: #ef4444; font-size: 18px;")
            self.status_label.setText("服务未响应")
            return
        self.status_dot.setStyleSheet("color: #22c55e; font-size: 18px;")
        self.status_label.setText("服务运行中")
        self.stat_labels["name"].setText(result.get("server_name", "—"))
        self.stat_labels["uptime"].setText(fmt_duration(result.get("uptime_seconds")))
        self.stat_labels["modpacks"].setText(str(result.get("modpack_count", 0)))
        self.stat_labels["mods"].setText(str(result.get("mod_count", 0)))
        self.stat_labels["storage"].setText(fmt_bytes(result.get("storage_used_bytes")))

    # --- 整合包 ---
    def _load_modpacks(self) -> None:
        w = ApiWorker("GET", "/api/v1/modpacks")
        w.done.connect(self._on_modpacks)
        self._workers.append(w)
        w.start()

    def _on_modpacks(self, ok: bool, result: Any) -> None:
        if not ok or not isinstance(result, dict):
            return
        items = result.get("modpacks", [])
        self.modpack_table.setRowCount(len(items))
        for r, m in enumerate(items):
            vals = [m.get("id", "")[:8], m.get("name", ""), m.get("version", ""),
                    m.get("game", ""), m.get("game_version", ""), m.get("mod_loader", ""),
                    fmt_bytes(m.get("file_size")), "上架" if m.get("enabled", True) else "下架"]
            for c, v in enumerate(vals):
                self.modpack_table.setItem(r, c, QTableWidgetItem(str(v)))
            self.modpack_table.item(r, 0).setToolTip(m.get("id", ""))

    def _upload_modpack(self) -> None:
        token = self._require_token()
        if not token:
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择整合包文件", "", "整合包 (*.zip)")
        if not file_path:
            return
        dlg = ModpackMetaDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        meta = dlg.values()
        if meta is None:
            QMessageBox.warning(self, "缺少必填", "名称/版本/游戏/游戏版本必填")
            return
        self._do_upload(meta, file_path, "/api/v1/modpacks", "整合包", self._load_modpacks)

    def _edit_modpack(self) -> None:
        token = self._require_token()
        if not token:
            return
        row = self.modpack_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        full_id = self.modpack_table.item(row, 0).toolTip()
        # 先拉详情
        w = ApiWorker("GET", f"/api/v1/modpacks/{full_id}")

        def _on_get(ok: bool, result: Any) -> None:
            if not ok or not isinstance(result, dict):
                QMessageBox.warning(self, "失败", "获取详情失败: " + str(result))
                return
            dlg = ModpackMetaDialog(self, existing=result)
            if dlg.exec() != QDialog.Accepted:
                return
            meta = dlg.values()
            if meta is None:
                QMessageBox.warning(self, "缺少必填", "名称/版本/游戏/游戏版本必填")
                return
            body = json.dumps(meta).encode()
            pw = ApiWorker("PATCH", f"/api/v1/modpacks/{full_id}", token=token, data=body,
                           headers={"Content-Type": "application/json"})

            def _on_patch(ok2: bool, r2: Any) -> None:
                if ok2:
                    self.statusBar().showMessage("整合包已更新", 3000)
                    self._load_modpacks()
                else:
                    QMessageBox.warning(self, "失败", str(r2))

            pw.done.connect(_on_patch)
            self._workers.append(pw)
            pw.start()

        w.done.connect(_on_get)
        self._workers.append(w)
        w.start()

    def _toggle_modpack(self) -> None:
        token = self._require_token()
        if not token:
            return
        row = self.modpack_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        full_id = self.modpack_table.item(row, 0).toolTip()
        cur = self.modpack_table.item(row, 7).text() == "上架"
        body = json.dumps({"enabled": not cur}).encode()
        w = ApiWorker("PATCH", f"/api/v1/modpacks/{full_id}", token=token, data=body,
                      headers={"Content-Type": "application/json"})
        w.done.connect(lambda ok, r: self._on_toggled(ok, r, "整合包", self._load_modpacks))
        self._workers.append(w)
        w.start()

    def _delete_modpack(self) -> None:
        token = self._require_token()
        if not token:
            return
        row = self.modpack_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        full_id = self.modpack_table.item(row, 0).toolTip()
        if QMessageBox.question(self, "确认", "确定删除该整合包？") != QMessageBox.Yes:
            return
        w = ApiWorker("DELETE", f"/api/v1/modpacks/{full_id}", token=token)
        w.done.connect(lambda ok, r: self._on_deleted(ok, r, "整合包", self._load_modpacks))
        self._workers.append(w)
        w.start()

    # --- 模组 ---
    def _load_mods(self) -> None:
        w = ApiWorker("GET", "/api/v1/mods")
        w.done.connect(self._on_mods)
        self._workers.append(w)
        w.start()

    def _on_mods(self, ok: bool, result: Any) -> None:
        if not ok or not isinstance(result, dict):
            return
        items = result.get("mods", [])
        self.mod_table.setRowCount(len(items))
        for r, m in enumerate(items):
            vals = [m.get("id", "")[:8], m.get("name", ""), m.get("version", ""),
                    m.get("game", ""), fmt_bytes(m.get("file_size")),
                    "上架" if m.get("enabled", True) else "下架"]
            for c, v in enumerate(vals):
                self.mod_table.setItem(r, c, QTableWidgetItem(str(v)))
            self.mod_table.item(r, 0).setToolTip(m.get("id", ""))

    def _upload_mod(self) -> None:
        token = self._require_token()
        if not token:
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择模组文件", "", "模组 (*.jar)")
        if not file_path:
            return
        dlg = ModMetaDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        meta = dlg.values()
        if meta is None:
            QMessageBox.warning(self, "缺少必填", "名称/版本/游戏必填")
            return
        self._do_upload(meta, file_path, "/api/v1/mods", "模组", self._load_mods)

    def _edit_mod(self) -> None:
        token = self._require_token()
        if not token:
            return
        row = self.mod_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        full_id = self.mod_table.item(row, 0).toolTip()
        w = ApiWorker("GET", f"/api/v1/mods/{full_id}")

        def _on_get(ok: bool, result: Any) -> None:
            if not ok or not isinstance(result, dict):
                QMessageBox.warning(self, "失败", "获取详情失败: " + str(result))
                return
            dlg = ModMetaDialog(self, existing=result)
            if dlg.exec() != QDialog.Accepted:
                return
            meta = dlg.values()
            if meta is None:
                QMessageBox.warning(self, "缺少必填", "名称/版本/游戏必填")
                return
            body = json.dumps(meta).encode()
            pw = ApiWorker("PATCH", f"/api/v1/mods/{full_id}", token=token, data=body,
                           headers={"Content-Type": "application/json"})

            def _on_patch(ok2: bool, r2: Any) -> None:
                if ok2:
                    self.statusBar().showMessage("模组已更新", 3000)
                    self._load_mods()
                else:
                    QMessageBox.warning(self, "失败", str(r2))

            pw.done.connect(_on_patch)
            self._workers.append(pw)
            pw.start()

        w.done.connect(_on_get)
        self._workers.append(w)
        w.start()

    def _toggle_mod(self) -> None:
        token = self._require_token()
        if not token:
            return
        row = self.mod_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        full_id = self.mod_table.item(row, 0).toolTip()
        cur = self.mod_table.item(row, 5).text() == "上架"
        body = json.dumps({"enabled": not cur}).encode()
        w = ApiWorker("PATCH", f"/api/v1/mods/{full_id}", token=token, data=body,
                      headers={"Content-Type": "application/json"})
        w.done.connect(lambda ok, r: self._on_toggled(ok, r, "模组", self._load_mods))
        self._workers.append(w)
        w.start()

    def _delete_mod(self) -> None:
        token = self._require_token()
        if not token:
            return
        row = self.mod_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        full_id = self.mod_table.item(row, 0).toolTip()
        if QMessageBox.question(self, "确认", "确定删除该模组？") != QMessageBox.Yes:
            return
        w = ApiWorker("DELETE", f"/api/v1/mods/{full_id}", token=token)
        w.done.connect(lambda ok, r: self._on_deleted(ok, r, "模组", self._load_mods))
        self._workers.append(w)
        w.start()

    # --- 用户管理 ---
    def _load_users(self) -> None:
        token = self._require_token()
        if not token:
            return
        w = ApiWorker("GET", "/api/v1/users", token=token)
        w.done.connect(self._on_users)
        self._workers.append(w)
        w.start()

    def _on_users(self, ok: bool, result: Any) -> None:
        if not ok or not isinstance(result, dict):
            self.user_list.clear()
            return
        self.user_list.clear()
        for u in result.get("users", []):
            label = u + (" （当前）" if u == self.current_user else "")
            self.user_list.addItem(label)

    def _add_user(self) -> None:
        token = self._require_token()
        if not token:
            return
        dlg = AddUserDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        if vals is None:
            QMessageBox.warning(self, "提示", "用户名不能空，密码至少6位")
            return
        username, password = vals
        body = json.dumps({"username": username, "password": password}).encode()
        w = ApiWorker("POST", "/api/v1/users", token=token, data=body,
                      headers={"Content-Type": "application/json"})

        def _cb(ok: bool, r: Any) -> None:
            if ok:
                self.statusBar().showMessage("用户已添加", 3000)
                self._load_users()
            else:
                QMessageBox.warning(self, "失败", str(r))

        w.done.connect(_cb)
        self._workers.append(w)
        w.start()

    def _del_user(self) -> None:
        token = self._require_token()
        if not token:
            return
        item = self.user_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一个用户")
            return
        username = item.text().replace(" （当前）", "")
        if QMessageBox.question(self, "确认", f"确定删除用户 {username}？") != QMessageBox.Yes:
            return
        w = ApiWorker("DELETE", f"/api/v1/users/{username}", token=token)

        def _cb(ok: bool, r: Any) -> None:
            if ok:
                self.statusBar().showMessage("用户已删除", 3000)
                self._load_users()
            else:
                QMessageBox.warning(self, "失败", str(r))

        w.done.connect(_cb)
        self._workers.append(w)
        w.start()

    # --- 通用回调 ---
    def _do_upload(self, meta: dict[str, Any], file_path: str, path: str,
                   kind: str, on_done) -> None:
        self.statusBar().showMessage(f"正在上传{kind}...")
        # 上传表单字段不含 enabled（上传默认上架）
        fields = {k: str(v) for k, v in meta.items() if k != "enabled"}
        w = UploadWorker(path, self.token or "", fields, file_path)

        def _cb(ok: bool, result: Any) -> None:
            if ok:
                self.statusBar().showMessage(f"{kind}上传成功", 3000)
                on_done()
                self._refresh_status()
            else:
                QMessageBox.warning(self, "上传失败", str(result))
                self.statusBar().showMessage("上传失败", 3000)

        w.done.connect(_cb)
        self._workers.append(w)
        w.start()

    def _on_toggled(self, ok: bool, result: Any, kind: str, on_done) -> None:
        if ok:
            self.statusBar().showMessage(f"{kind}状态已切换", 3000)
            on_done()
        else:
            QMessageBox.warning(self, "操作失败", str(result))

    def _on_deleted(self, ok: bool, result: Any, kind: str, on_done) -> None:
        if ok:
            self.statusBar().showMessage(f"{kind}已删除", 3000)
            on_done()
            self._refresh_status()
        else:
            QMessageBox.warning(self, "删除失败", str(result))

    def closeEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        self.statusBar().showMessage("正在停止服务...")
        self.server_thread.stop_server()
        event.accept()


# ---------- 服务线程 ----------
class ServerThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.server = None

    def run(self) -> None:
        import uvicorn
        config = uvicorn.Config(
            "app.main:app", host=settings.host, port=settings.port,
            reload=False, log_level="warning",
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop_server(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
