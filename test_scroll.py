#!/usr/bin/env python3
"""ScrolledWindow + TextView の初期スクロール動作を検証するスクリプト。
ウィンドウを開いたとき末尾が見えているかどうかを確認する。"""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Gio

LINES = 200  # スクロールが必要になる行数


def make_buffer() -> Gtk.TextBuffer:
    buf = Gtk.TextBuffer()
    for i in range(LINES):
        buf.insert(buf.get_end_iter(), f"line {i:04d}\n")
    return buf


# ------------------------------------------------------------------ #
# 試す手法をここに実装する
# ------------------------------------------------------------------ #

def scroll_to_bottom(label: str, scroll: Gtk.ScrolledWindow, _=None):
    adj = scroll.get_vadjustment()
    adj.set_value(adj.get_upper() - adj.get_page_size())
    print(f"  [{label}] scroll_to_bottom: upper={adj.get_upper():.0f} page={adj.get_page_size():.0f} → value={adj.get_value():.0f}")


def setup_scroll(label: str, scroll: Gtk.ScrolledWindow):
    """ここでいろいろな手法を試す"""
    adj = scroll.get_vadjustment()

    stb = lambda: scroll_to_bottom(label, scroll)

    if label == "A: map 直接":
        scroll.get_parent().get_root().connect(
            "map", lambda w: stb())

    elif label == "B: map + idle_add":
        scroll.get_parent().get_root().connect(
            "map", lambda w: GLib.idle_add(lambda: stb() or False))

    elif label == "C: notify::upper (初回)":
        def on_upper(adj, _pspec):
            if adj.get_upper() > adj.get_page_size():
                adj.disconnect(handler[0])
                stb()
        handler = [adj.connect("notify::upper", on_upper)]

    elif label == "D: notify::upper (安定後)":
        # upper が変化しなくなった＝安定したとみなして発火
        last = [0.0]
        def on_upper(adj, _pspec):
            v = adj.get_upper()
            if v == last[0] and v > adj.get_page_size():
                adj.disconnect(handler[0])
                stb()
            last[0] = v
        handler = [adj.connect("notify::upper", on_upper)]

    elif label == "E: map + idle_add (PRIORITY_LOW)":
        def on_map(win):
            GLib.idle_add(lambda: stb() or False, priority=GLib.PRIORITY_LOW)
        scroll.get_parent().get_root().connect("map", on_map)

    print(f"[{label}] setup done")


# ------------------------------------------------------------------ #
# ウィンドウ生成
# ------------------------------------------------------------------ #

METHODS = [
    "A: map 直接",
    "B: map + idle_add",
    "C: notify::upper (初回)",
    "D: notify::upper (安定後)",
    "E: map + idle_add (PRIORITY_LOW)",
]


class TestApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.walbrix.test-scroll",
                         flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        buf = make_buffer()
        for method in METHODS:
            self._make_window(method, buf)

    def _make_window(self, label: str, buf: Gtk.TextBuffer):
        win = Gtk.ApplicationWindow(application=self, title=label)
        win.set_default_size(400, 300)

        view = Gtk.TextView(buffer=buf)
        view.set_editable(False)
        view.set_monospace(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(view)
        scroll.set_vexpand(True)

        win.set_child(scroll)
        setup_scroll(label, scroll)
        win.present()


TestApp().run([])
