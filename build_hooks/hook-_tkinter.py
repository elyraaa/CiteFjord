"""Collect Tcl/Tk data explicitly when PyInstaller's probe cannot open a window."""

from pathlib import Path
import sys

base = Path(sys.base_prefix) / "tcl"
tcl = base / "tcl8.6"
tk = base / "tk8.6"
if not tcl.is_dir() or not tk.is_dir():
    raise RuntimeError("A full Python installation with Tcl/Tk is required")
datas = [(str(tcl), "_tcl_data"), (str(tk), "_tk_data")]
