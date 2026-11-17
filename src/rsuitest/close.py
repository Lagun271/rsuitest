# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
"""Close RobotStudio through its own UI (never a kill, which leaves its virtual controller running). Says which one:
a RobotStudio someone is working in must not be closed by a test tool (2026-11-14), so there is no default.

  rsuitest-close                                list what is running, close nothing (exit code 2)
  rsuitest-close --pid 1234 [--pid 5678]        close these RobotStudio processes (the PIDs a test printed)
  rsuitest-close --all                          close every running RobotStudio
  ... --discard                                 answer "unsaved changes ... save?" with No
  ... --discard --terminate-vc                  also answer "virtual controllers are running ... terminate?" with Yes
  rsuitest-close --orphan-vc                    with no RobotStudio running, end leftover RobVC processes (what
                                                RobotStudio's own "terminate them?" prompt does)
(or: python -m rsuitest.close ..., run.ps1 close -- ...)
"""
import argparse
import sys

from rsuitest import core as rs


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rsuitest-close", description="Close RobotStudio through its UI: --pid or --all.")
    ap.add_argument("--pid", type=int, action="append", default=[], help="RobotStudio process to close (repeatable)")
    ap.add_argument("--all", action="store_true", help="close every running RobotStudio")
    ap.add_argument("--discard", action="store_true", help="do not save unsaved changes")
    ap.add_argument("--terminate-vc", action="store_true",
                    help="let RobotStudio terminate leftover virtual controllers")
    ap.add_argument("--orphan-vc", action="store_true", help="end RobVC processes left without a RobotStudio")
    a = ap.parse_args(argv)

    running = rs.robotstudio_pids()
    if a.all:
        pids = running
    else:
        pids = a.pid
        if not pids and not a.orphan_vc:
            print("Running: " + (", ".join(f"{p.info['name']} {p.pid}" for p in rs.processes()) or "nothing"))
            print("Closes nothing without --pid <PID> or --all.")
            sys.exit(2)
        if other := [p for p in pids if p not in running]:
            sys.exit(f"Not a running RobotStudio: {other}")

    for pid in pids:
        print(f"Closing RobotStudio {pid} ...")
        for answered in rs.shutdown(pid, discard=a.discard, terminate_vc=a.terminate_vc):
            print(f"   answered: {answered}")
    if a.orphan_vc and not rs.robotstudio_pids():
        for p in rs.processes(("RobVC.exe",)):
            print(f"Ending orphaned RobVC {p.pid} ...")
            p.terminate()
            p.wait(30)
            print("   ended")
    left = [f"{p.info['name']} {p.pid}" for p in rs.processes()]
    print("Still running: " + (", ".join(left) or "nothing"))


if __name__ == "__main__":
    main()
