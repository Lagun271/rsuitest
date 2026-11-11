# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
"""Close every running RobotStudio through its own UI (never a kill, which leaves its virtual controller running).

  rsuitest-close                                stops on any dialog and prints it
  rsuitest-close --discard                      answer "unsaved changes ... save?" with No
  rsuitest-close --discard --terminate-vc       also answer "virtual controllers are running ... terminate?" with Yes
  rsuitest-close --orphan-vc                    with no RobotStudio running, end leftover RobVC processes (what
                                                RobotStudio's own "terminate them?" prompt does)
(or: python -m rsuitest.close ..., run.ps1 close -- ...)
"""
import argparse

from rsuitest import core as rs


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rsuitest-close", description="Close every running RobotStudio through its UI.")
    ap.add_argument("--discard", action="store_true", help="do not save unsaved changes")
    ap.add_argument("--terminate-vc", action="store_true",
                    help="let RobotStudio terminate leftover virtual controllers")
    ap.add_argument("--orphan-vc", action="store_true", help="end RobVC processes left without a RobotStudio")
    a = ap.parse_args(argv)

    for pid in rs.robotstudio_pids():
        print(f"Closing RobotStudio {pid} ...")
        for answered in rs.shutdown(pid, discard=a.discard, terminate_vc=a.terminate_vc):
            print(f"   answered: {answered}")
        print("   exited")
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
