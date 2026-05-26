#!/usr/bin/env python3
"""gadget — GTK4 process launcher for streaming gadgets

Usage: gadget <dir>
  <dir> must contain launcher.toml describing the process to manage.
"""

import argparse
import re
import subprocess
import sys
import threading
import tomllib
from pathlib import Path

import gi
import keyutils

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

LAUNCHER_TOML = "gadget.toml"
LOG_MAX_LINES = 500


def load_config(work_dir: Path) -> dict:
    with open(work_dir / LAUNCHER_TOML, "rb") as f:
        return tomllib.load(f)


# --------------------------------------------------------------------------- #
# パスワードダイアログ
# --------------------------------------------------------------------------- #

class PasswordDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, key_name: str, desc: str, on_submit):
        super().__init__(
            title="パスワードの入力",
            transient_for=parent,
            modal=True,
            resizable=False,
        )
        self._on_submit = on_submit

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        label = Gtk.Label()
        label.set_markup(
            f"{GLib.markup_escape_text(desc)}\n"
            f"<small>(keyring: <tt>{GLib.markup_escape_text(key_name)}</tt>)</small>"
        )
        label.set_wrap(True)
        label.set_halign(Gtk.Align.START)
        box.append(label)

        self._entry = Gtk.PasswordEntry()
        self._entry.set_show_peek_icon(True)
        self._entry.connect("activate", lambda _: self._submit())
        box.append(self._entry)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        cancel = Gtk.Button(label="キャンセル")
        cancel.connect("clicked", lambda _: self.close())

        ok = Gtk.Button(label="OK")
        ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: self._submit())

        btn_box.append(cancel)
        btn_box.append(ok)
        box.append(btn_box)

        self.set_child(box)
        self.set_default_size(380, -1)

    def _submit(self):
        password = self._entry.get_text()
        self.close()
        if password:
            self._on_submit(password)


# --------------------------------------------------------------------------- #
# ログウィンドウ
# --------------------------------------------------------------------------- #

class LogWindow(Gtk.Window):
    def __init__(self, parent: Gtk.Window, title: str, buffer: Gtk.TextBuffer):
        super().__init__(title=f"ログ — {title}", transient_for=parent)

        view = Gtk.TextView(buffer=buffer)
        view.set_editable(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_child(view)
        self._scroll.set_vexpand(True)
        self._scroll.set_hexpand(True)

        buffer.connect("changed", self._on_changed)
        self.connect("map", self._on_map)

        self.set_child(self._scroll)
        self.set_default_size(720, 420)

    def _on_map(self, _):
        GLib.idle_add(self._scroll_to_bottom)

    def _scroll_to_bottom(self, _=None):
        adj = self._scroll.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return False

    def _on_changed(self, _buf):
        if not self.get_visible():
            return
        adj = self._scroll.get_vadjustment()
        if adj.get_value() >= adj.get_upper() - adj.get_page_size() - 20:
            GLib.idle_add(self._scroll_to_bottom)


# --------------------------------------------------------------------------- #
# メインウィンドウ
# --------------------------------------------------------------------------- #

class LauncherWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, config: dict, work_dir: Path):
        self._name = config.get("name", work_dir.name)
        super().__init__(application=app, title=self._name)
        self._config = config
        self._work_dir = work_dir
        self._process: subprocess.Popen | None = None
        self._closing = False
        self._log_buffer = Gtk.TextBuffer()
        self._log_win: LogWindow | None = None
        self._build_ui()

    def _build_ui(self):
        icon_path = self._config.get("icon")
        if icon_path:
            header = Gtk.HeaderBar()
            img = Gtk.Image.new_from_file(str(self._work_dir / icon_path))
            img.set_pixel_size(24)
            header.pack_start(img)
            self.set_titlebar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self._status = Gtk.Label(label="停止中")
        self._status.set_halign(Gtk.Align.START)
        box.append(self._status)

        markup = self._config.get("info", {}).get("markup")
        if markup:
            info = Gtk.Label()
            info.set_markup(markup)
            info.set_halign(Gtk.Align.START)
            info.set_wrap(True)
            info.set_selectable(True)
            box.append(info)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self._start_btn = Gtk.Button(label="起動")
        self._start_btn.add_css_class("suggested-action")
        self._start_btn.connect("clicked", self._on_start)

        self._stop_btn = Gtk.Button(label="停止")
        self._stop_btn.add_css_class("destructive-action")
        self._stop_btn.set_sensitive(False)
        self._stop_btn.connect("clicked", self._on_stop)

        log_btn = Gtk.Button(label="ログ")
        log_btn.connect("clicked", self._on_show_log)

        btn_box.append(self._start_btn)
        btn_box.append(self._stop_btn)
        btn_box.append(log_btn)

        keys = self._config.get("keyring", [])
        if keys:
            menu = Gio.Menu()
            for kr in keys:
                key_name = kr["key"]
                label = f"「{key_name}」を再入力"
                action_name = f"rekey_{key_name}"
                menu.append(label, f"win.{action_name}")
                action = Gio.SimpleAction.new(action_name, None)
                action.connect(
                    "activate",
                    lambda _a, _p, k=key_name, d=kr.get("desc", f"キー '{key_name}' のパスワード"):
                        self._reenter_key(k, d),
                )
                self.add_action(action)

            menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
            btn_box.append(menu_btn)

        box.append(btn_box)

        self.set_child(box)
        self.set_default_size(320, -1)
        self.set_resizable(False)

    # ------------------------------------------------------------------ #
    # 起動フロー
    # ------------------------------------------------------------------ #

    def _on_start(self, _):
        self._check_keys(self._config.get("keyring", []), 0)

    def _check_keys(self, keys: list, index: int):
        if index >= len(keys):
            self._start_process()
            return
        kr = keys[index]
        key_name = kr["key"]
        serial = keyutils.request_key(key_name.encode(), keyutils.KEY_SPEC_USER_KEYRING)
        if serial is None:
            desc = kr.get("desc", f"キー '{key_name}' のパスワード")
            dlg = PasswordDialog(
                self, key_name, desc,
                lambda pw, k=key_name, i=index: self._register_key(k, pw, keys, i + 1),
            )
            dlg.present()
        else:
            self._check_keys(keys, index + 1)

    def _reenter_key(self, key_name: str, desc: str):
        dlg = PasswordDialog(
            self, key_name, desc,
            lambda pw: self._update_key(key_name, pw),
        )
        dlg.present()

    def _update_key(self, key_name: str, password: str):
        serial = keyutils.request_key(key_name.encode(), keyutils.KEY_SPEC_USER_KEYRING)
        try:
            if serial is not None:
                subprocess.run(
                    ["keyctl", "update", str(serial), password],
                    check=True, capture_output=True,
                )
            else:
                subprocess.run(
                    ["keyctl", "padd", "user", key_name, "@u"],
                    input=password.encode(),
                    check=True, capture_output=True,
                )
        except subprocess.CalledProcessError as e:
            self._append_log(f"[gadget] keyctl エラー: {e.stderr.decode()}\n")
            return
        self._append_log(f"[gadget] キー '{key_name}' を更新しました\n")

    def _register_key(self, key_name: str, password: str, keys: list, next_index: int):
        try:
            subprocess.run(
                ["keyctl", "padd", "user", key_name, "@u"],
                input=password.encode(),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            self._append_log(f"[gadget] keyctl エラー: {e.stderr.decode()}\n")
            return
        self._check_keys(keys, next_index)

    def _start_process(self):
        exec_cmd = self._config["exec"]
        if isinstance(exec_cmd, str):
            exec_cmd = exec_cmd.split()

        self._process = subprocess.Popen(
            exec_cmd,
            cwd=self._work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._append_log(f"--- 起動 (PID {self._process.pid}) ---\n")
        self._set_running(True)
        threading.Thread(target=self._read_output, daemon=True, name="log-reader").start()

    # ------------------------------------------------------------------ #
    # 停止フロー
    # ------------------------------------------------------------------ #

    def _on_stop(self, _):
        if self._process:
            self._process.terminate()

    # ------------------------------------------------------------------ #
    # 出力キャプチャ（バックグラウンドスレッド）
    # ------------------------------------------------------------------ #

    def _read_output(self):
        for line in self._process.stdout:
            GLib.idle_add(self._append_log, line)
        GLib.idle_add(self._process_ended)

    def _process_ended(self):
        if self._closing:
            return
        rc = self._process.poll() if self._process else None
        self._append_log(f"--- 終了 (code {rc}) ---\n")
        self._process = None
        self._set_running(False)

    # ------------------------------------------------------------------ #
    # UI ユーティリティ
    # ------------------------------------------------------------------ #

    def _append_log(self, text: str):
        buf = self._log_buffer
        buf.insert(buf.get_end_iter(), text)
        line_count = buf.get_line_count()
        if line_count > LOG_MAX_LINES:
            buf.delete(buf.get_start_iter(), buf.get_iter_at_line(line_count - LOG_MAX_LINES))

    def _set_running(self, running: bool):
        self._start_btn.set_sensitive(not running)
        self._stop_btn.set_sensitive(running)
        self._status.set_label("稼働中" if running else "停止中")

    def _on_show_log(self, _):
        if self._log_win is None or not self._log_win.get_visible():
            self._log_win = LogWindow(self, self._name, self._log_buffer)
        self._log_win.present()

    # ------------------------------------------------------------------ #
    # ウィンドウ閉じる
    # ------------------------------------------------------------------ #

    def do_close_request(self) -> bool:
        self._closing = True
        if self._process:
            self._process.terminate()
        return False


# --------------------------------------------------------------------------- #
# アプリケーション
# --------------------------------------------------------------------------- #

def _make_app_id(work_dir: Path) -> str:
    safe = re.sub(r'[^a-zA-Z0-9]', '_', work_dir.name)
    return f"com.walbrix.gadget.{safe}"


class GadgetApp(Gtk.Application):
    def __init__(self, work_dir: Path):
        super().__init__(
            application_id=_make_app_id(work_dir),
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self._work_dir = work_dir

    def do_activate(self):
        error = self._validate()
        if error:
            self._show_error(error)
            return
        config = load_config(self._work_dir)
        win = LauncherWindow(self, config, self._work_dir)
        win.present()

    def _validate(self) -> str | None:
        if not self._work_dir.exists():
            return f"ディレクトリが存在しません:\n{self._work_dir}"
        if not self._work_dir.is_dir():
            return f"ディレクトリではありません:\n{self._work_dir}"
        toml_path = self._work_dir / LAUNCHER_TOML
        if not toml_path.exists():
            return f"{LAUNCHER_TOML} が見つかりません:\n{toml_path}"
        try:
            load_config(self._work_dir)
        except tomllib.TOMLDecodeError as e:
            return f"{LAUNCHER_TOML} の解析に失敗しました:\n{e}"
        return None

    def _show_error(self, message: str):
        win = Gtk.ApplicationWindow(application=self, title="gadget — 起動エラー")
        win.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        label = Gtk.Label(label=message)
        label.set_wrap(True)
        label.set_max_width_chars(50)
        label.set_halign(Gtk.Align.START)
        label.set_selectable(True)
        box.append(label)

        btn = Gtk.Button(label="閉じる")
        btn.connect("clicked", lambda _: win.close())
        btn.set_halign(Gtk.Align.END)
        box.append(btn)

        win.set_child(box)
        win.set_default_size(400, -1)
        win.present()


def cmd_install(work_dir: Path, config: dict) -> None:
    name = config.get("name", work_dir.name)
    comment = config.get("comment", "")
    icon_rel = config.get("icon")
    app_id = _make_app_id(work_dir)
    gadget_bin = Path(sys.argv[0]).resolve()
    desktop_dir = Path.home() / ".local/share/applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = desktop_dir / f"{work_dir.name}.desktop"

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={name}",
    ]
    if comment:
        lines.append(f"Comment={comment}")
    lines += [
        f"Exec={gadget_bin} {work_dir}",
        "Terminal=false",
    ]
    if icon_rel:
        lines.append(f"Icon={work_dir / icon_rel}")
    categories = config.get("categories", "AudioVideo")
    if not categories.endswith(";"):
        categories += ";"
    lines += [
        f"StartupWMClass={app_id}",
        f"Categories={categories}",
    ]

    desktop_path.write_text("\n".join(lines) + "\n")
    print(f"インストール完了: {desktop_path}")


def main():
    parser = argparse.ArgumentParser(
        description="gadget — GTK4 process launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="<dir>/gadget.toml で起動コマンド・キーリング・URLを設定します。",
    )
    parser.add_argument("dir", help="ワーキングディレクトリ (gadget.toml が必要)")
    parser.add_argument("--install", action="store_true",
                        help=".desktop ファイルを生成して ~/.local/share/applications/ に配置する")
    args = parser.parse_args()

    work_dir = Path(args.dir).resolve()

    if args.install:
        if not work_dir.is_dir():
            print(f"エラー: '{args.dir}' はディレクトリではありません", file=sys.stderr)
            sys.exit(1)
        toml_path = work_dir / LAUNCHER_TOML
        if not toml_path.exists():
            print(f"エラー: {toml_path} が見つかりません", file=sys.stderr)
            sys.exit(1)
        try:
            config = load_config(work_dir)
        except tomllib.TOMLDecodeError as e:
            print(f"エラー: {toml_path} の解析に失敗しました:\n  {e}", file=sys.stderr)
            sys.exit(1)
        cmd_install(work_dir, config)
        return

    app = GadgetApp(work_dir)
    sys.exit(app.run([sys.argv[0]]))  # GTK に余分な引数を渡さない


if __name__ == "__main__":
    main()
