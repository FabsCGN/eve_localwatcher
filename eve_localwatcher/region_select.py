"""Fullscreen drag-rectangle region selector (Tkinter).

Returns an absolute (x, y, w, h) screen rectangle, or None if cancelled. Spans
the whole virtual desktop so regions on secondary monitors can be selected.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional, Tuple

from . import winutil


def select_region(parent: tk.Misc,
                  prompt: str = "Bereich aufziehen — Esc bricht ab") \
        -> Optional[Tuple[int, int, int, int]]:
    vx, vy, vw, vh = winutil.virtual_screen()
    if vw <= 0 or vh <= 0:
        vx, vy = 0, 0
        vw, vh = parent.winfo_screenwidth(), parent.winfo_screenheight()

    top = tk.Toplevel(parent)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.30)
    top.configure(bg="black")
    top.geometry(f"{vw}x{vh}+{vx}+{vy}")

    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(vw // 2, 30, text=prompt, fill="white",
                       font=("Segoe UI", 16, "bold"))

    state = {"x0": 0, "y0": 0, "rect": None, "result": None}

    def on_down(e):
        state["x0"], state["y0"] = e.x, e.y
        state["rect"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#ff3b30", width=2, fill="#ff3b30",
            stipple="gray25")

    def on_drag(e):
        if state["rect"] is not None:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    def on_up(e):
        x0, y0 = state["x0"], state["y0"]
        x1, y1 = e.x, e.y
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w >= 3 and h >= 3:
            state["result"] = (vx + x, vy + y, w, h)
        top.destroy()

    def on_cancel(_e):
        state["result"] = None
        top.destroy()

    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_up)
    top.bind("<Escape>", on_cancel)

    top.focus_force()
    top.grab_set()
    parent.wait_window(top)
    return state["result"]
