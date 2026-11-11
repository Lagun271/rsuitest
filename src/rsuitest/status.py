# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
"""What is running: RobotStudio and virtual controller (RobVC) processes, each RobotStudio's window title and any
open dialog (title, message, buttons). Changes nothing.

  rsuitest-status                  (or: python -m rsuitest.status, run.ps1 status)
"""
from datetime import datetime

from rsuitest import core as rs


def main() -> None:
    procs = rs.processes()
    if not procs:
        print("No RobotStudio or RobVC running.")
    for p in procs:
        started = datetime.fromtimestamp(p.info["create_time"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{p.info['name']:16} PID {p.pid:6}  started {started}")
        if p.info["name"] == "RobotStudio.exe":
            try:
                _, main_win = rs.main_window(p.pid)
                print(f"   window: {main_win.window_text()!r}")
                for d in rs.dialogs(p.pid, main_win):
                    print(f"   dialog: {d}")
            except Exception as e:  # noqa: BLE001
                print(f"   (no window: {e})")


if __name__ == "__main__":
    main()
