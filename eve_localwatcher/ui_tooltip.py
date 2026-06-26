"""Lightweight hover tooltip for Tkinter widgets."""
from __future__ import annotations

import tkinter as tk


class ToolTip:
    def __init__(self, widget: tk.Misc, text: str, delay: int = 450,
                 wrap: int = 320) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wrap = wrap
        self._tip: tk.Toplevel | None = None
        self._after: str | None = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _event=None) -> None:
        self._unschedule()
        self._after = self.widget.after(self.delay, self._show)

    def _leave(self, _event=None) -> None:
        self._unschedule()
        self._hide()

    def _unschedule(self) -> None:
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tw, text=self.text, justify="left", background="#1f1f23",
                 foreground="#ededed", relief="solid", borderwidth=1,
                 wraplength=self.wrap, font=("Segoe UI", 9), padx=8, pady=5).pack()

    def _hide(self) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


def attach(widget: tk.Misc, text: str) -> None:
    ToolTip(widget, text)
