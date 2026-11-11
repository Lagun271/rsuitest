# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
"""Discovery: dump the UIA tree of the RobotStudio main window (or one dialog) to a text file, to read off the
Names / AutomationIds / ControlTypes a test should target. RobotStudio must be running; load the add-in first if
you want its ribbon tab.

  rsuitest-dump-tree                          main window, depth 6  -> reports/tree-main.txt
  rsuitest-dump-tree --depth 12
  rsuitest-dump-tree --title "<dialog title>"
  rsuitest-dump-tree --out <folder>           write there instead of reports/ in the current folder
(or: python -m rsuitest.dump_tree ..., run.ps1 dump_tree -- ...)
"""
import argparse
from pathlib import Path

from rsuitest import core as rs


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rsuitest-dump-tree", description="Dump RobotStudio's UIA tree to a file.")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--title", help="dump this top-level window of the process instead of the main window")
    ap.add_argument("--out", type=Path, default=Path("reports"), help="output folder (default: reports)")
    a = ap.parse_args(argv)

    pid = a.pid or (rs.robotstudio_pids() or [None])[0]
    if not pid:
        raise SystemExit("No RobotStudio running.")
    a.out.mkdir(parents=True, exist_ok=True)
    if a.title:
        win = rs.dialog(pid, a.title)
        path = a.out / f"tree-{a.title.replace(' ', '_')}.txt"
    else:
        _, win = rs.attach(pid, timeout=30)
        path = a.out / "tree-main.txt"
    win.dump_tree(depth=a.depth, filename=str(path))
    print(f"Wrote {path.resolve()} (depth {a.depth}). Grep it for the Names you need.")


if __name__ == "__main__":
    main()
