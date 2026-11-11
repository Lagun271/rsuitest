# rsuitest

UI Automation test helpers for RobotStudio 2026 add-ins, in Python with
[pywinauto](https://github.com/pywinauto/pywinauto) (backend `uia`), plus a reader for saved stations (`PIM.xml`
inside an `.rsstn`).

A test starts RobotStudio with your add-in sideloaded, finds ribbon controls and dialogs in the Windows UI Automation
tree by name and `AutomationId` (not by pixel coordinates), reads results as text, checks the saved station file, and
writes a report. Each test declares success criteria; the verdict is about those only.

- `rsuitest.core`: start/attach/close RobotStudio, ribbon tabs and buttons, dialogs (every wait stops on an
  unexpected one), screenshots, RobotStudio's Output window, an add-in's log file, and `Run` (steps, criteria,
  `result.md`).
- `rsuitest.pim`: object frame sizes and path colours from a saved station, for checks that must not depend on
  looking at the 3D view.
- Command-line tools: `rsuitest-status`, `rsuitest-close`, `rsuitest-dump-tree`, `rsuitest-pim`.

## Requirements

- Windows, with RobotStudio 2026 installed (developed against 2026.4). Default path
  `C:\Program Files (x86)\ABB\RobotStudio 2026\Bin\RobotStudio.exe`; set `RSUITEST_RS_EXE` (or `core.RS_EXE`) for
  another one.
- Python 3.12 or later.
- An unlocked desktop. Clicks hit screen coordinates and RobotStudio's ribbon only works while its window is in
  front, so keep the mouse and keyboard untouched while a test runs.
- Display scaling: developed and run at 200 %. The helpers use UIA rectangles and pywinauto's clicks, which run
  DPI-aware; other scalings are expected to work but are not tested.
- RobotStudio licence that allows add-ins (the Free licence does not start any add-in).

## Installation

Pin to a tag. uv and pip need `git` on the machine to install from a git URL.

```powershell
uv add "git+https://github.com/Lagun271/rsuitest" --tag v0.1.0
```

or in `pyproject.toml`:

```toml
dependencies = ["rsuitest @ git+https://github.com/Lagun271/rsuitest@v0.1.0"]
```

or with pip:

```powershell
pip install "git+https://github.com/Lagun271/rsuitest@v0.1.0"
```

### Self-contained test folder (template in `scripts/`)

The bootstrap scripts cannot come from the package, since they download uv and Python before anything is
installed. Copy the contents of [`scripts/`](scripts) into your test folder and change `pyproject.toml` (name,
description):

| File | What |
|---|---|
| `setup.ps1` | One-time: downloads uv into `.uv\`, Python into `.python\` (version from `.python-version`), creates `.venv\` and installs `pyproject.toml`'s dependencies. Needs internet and git. |
| `env.ps1` | Keeps every uv path inside the folder (`UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR`, `UV_PROJECT_ENVIRONMENT`, `UV_PYTHON_PREFERENCE=only-managed`); nothing is written to the user profile or `PATH`. |
| `run.ps1`, `run.cmd` | `run.ps1 <name> [-- args]` runs `<name>.py` from the folder, or `python -m rsuitest.<name>` if there is no such file (`run.ps1 status`, `close`, `dump_tree`, `pim`). Runs `setup.ps1` first if there is no `.venv\`. |
| `pyproject.toml`, `.python-version` | The project, with rsuitest pinned to a tag; Python 3.12. |
| `.gitignore` | The toolchain folders and `reports\`. |

## Example

A test project sets what `rsuitest.core` cannot know: the `.rsaddin` to sideload, the folder name of its installed
`.rspak`, and its ribbon tab. The usual place is a small module that every test imports, e.g. `myaddin.py`:

```python
from pathlib import Path

from rsuitest import core
from rsuitest.core import *  # noqa: F401,F403  (tests use myaddin.<helper>)

HERE = Path(__file__).resolve().parent
core.ADDIN = HERE.parent / "src" / "MyAddin" / "bin" / "Debug" / "MyAddin.rsaddin"
core.PACKAGE_GLOB = "Vendor.MyAddin-*"
core.TAB_GROUPS["MyAddin"] = "My Addin"   # tab name -> a group Pane only that tab shows
```

Set these on `core`, not on your module: `core` reads its own globals. `ADDIN` and `PACKAGE_GLOB` can come from the
environment variables `RSUITEST_ADDIN` and `RSUITEST_PACKAGE_GLOB` instead.

`tc_about.py`:

```python
import sys
from datetime import datetime

import myaddin as rs

report = rs.HERE / "reports" / f"{datetime.now():%Y-%m-%d-%H%M}-TC-ABOUT"
run = rs.Run("TC-ABOUT", report)
run.declare(A1="About shows the add-in's name")
app = main = pid = None
try:
    with run.step("start RobotStudio") as s:
        pid = rs.start_robotstudio()            # refuses if RobotStudio or a virtual controller is running
        app, main = rs.attach(pid)
        s.seen = f"PID {pid}"
    with run.step("load the add-in") as s:
        rs.load_powerpac(main, "MyAddin")       # Add-Ins > PowerPacs > first button, waits for the tab
        s.screenshot = rs.shot(main, report / "loaded.png")
    with run.step("About") as s:
        rs.tab(main, "MyAddin")
        dlg = rs.open_dialog(pid, main, "CmdBarCtl_About", "About My Addin", run.unexpected)
        title = rs.text(dlg, "labelName")        # AutomationId = WinForms Control.Name
        run.check("A1", title.startswith("My Addin"), repr(title))
        rs.press(rs.find(dlg, title="OK", control_types=("Button",)))
except Exception as e:  # noqa: BLE001
    run.error(e, main)
finally:
    if pid:
        rs.shutdown(pid)
    verdict, code = run.verdict()
    run.finish(verdict)
sys.exit(code)
```

```powershell
.\run.ps1 tc_about
```

Find the names to target with `.\run.ps1 dump_tree` (or `rsuitest-dump-tree`) while RobotStudio runs.

## Writing a new test

1. Write down what the test proves as success criteria (`run.declare(A1=..., A2=...)`) before the steps. The steps
   are only the means; a step that cannot be done leaves its criteria "not checked" (COULD NOT RUN), not FAIL.
2. Start RobotStudio by hand (or with a test and `--keep`), bring it to the state of the step, and run
   `.\run.ps1 dump_tree` (`-- --title "<dialog title>"` for a dialog). Grep `reports\tree-*.txt` for the Names,
   `AutomationId`s and control types. Add-in dialogs: the ids are the WinForms `Control.Name`s in the
   `*.Designer.cs` files.
3. Copy an existing test and keep its frame: `Run`, one `with run.step(...)` per step, `run.check` for each criterion,
   `run.error` in `except`, `shutdown` in `finally`, `sys.exit(code)`.
4. Prefer checks on text (labels, the Output window, the add-in's log file via `log_mark`/`wait_log`) and on the saved
   station (`rsuitest.pim`) over screenshots. Screenshots are evidence for a person, not the check.
5. Dialogs that are unrelated to what the test checks go into `AUTO_ANSWERS` (listed under "Noted"); any other dialog
   stops the run with its text.

## Adding a helper

- **Generic** (works for any add-in, only RobotStudio's own UI): add it to `rsuitest.core` in this repo. Find
  targets by UIA name, id and type, never by coordinates; wait with `wait_until(..., watch=main)` so a dialog stops
  the wait; never `Invoke` a button that opens a modal dialog. The docstring says what it does and what was observed
  that made it so (with the date), and names no add-in, customer or machine. A new fact about RobotStudio's UIA tree
  goes into "RobotStudio 2026 UIA facts" below.
- **Add-in specific** (its tab, dialogs, log file, version): in the test project's own module (`myaddin.py` in the
  example), not here.
- Release: raise `version` in `pyproject.toml` and `__version__` in `src/rsuitest/__init__.py` as described in
  "Versioning", commit, tag `vX.Y.Z`, push the tag. Projects move their pin to the new tag
  (`uv add ... --tag vX.Y.Z`).

## Writing tests with Claude Code and computer use

The tests are written to be developed by an AI coding agent such as Claude Code, in a session that has both a shell
and computer use (in the Claude desktop app: Settings > This computer > Computer use, then approve RobotStudio when
asked; a terminal `claude` on Windows has no computer use).

- **Give the agent this README.** The "UIA facts" are the rules it needs: RobotStudio in front, never kill it, never
  `Invoke` a button that opens a modal dialog, one RobotStudio at a time, success criteria first.
- **Explore with screenshots, automate with UIA.** The agent may look at RobotStudio by screenshot to understand a
  step, then uses `dump_tree` to find the UIA names and writes the step as code. Everything that is a tab, button,
  dialog, label or list belongs in the script: deterministic, milliseconds per step, checked on text.
- **Run, read, fix.** The agent runs `.\run.ps1 tc_<name>`, reads `result.md`, `run.log` and the screenshots, and
  fixes the test. `rsuitest-status` shows what is running and any open dialog as text; `rsuitest-close` closes
  RobotStudio cleanly between attempts.
- **Handoff steps.** What UIA cannot reach (the 3D view: compare sizes by eye, pick a point in the graphics) becomes
  a handoff point: the script prints what to do and waits for a flag file such as `<report>\step04.done`; the agent
  does the step by screenshot and click, creates the file, and the script continues. Prefer typed values in dialogs
  over clicks in the graphics, and checks in the saved station over looking.
- **Never both at once.** While a script runs, the agent (and you) keep the mouse and keyboard untouched; computer
  use acts only at a handoff point, when the script waits.

## Report format

Each `Run` writes to its report folder:

- `result.md`: heading with test id and time, the verdict and total time, a table of criteria
  (`| Criterion | Must be true | Result | Evidence |`, result `met` / `**not met**` / `not checked`), a table of steps
  (`| Step | Seen | Screenshot | s |`), then "Unexpected" (errors, retried clicks) and "Noted" (dialogs answered
  automatically through `AUTO_ANSWERS`), which are not part of the verdict.
- `run.log`: everything the test printed.
- Screenshots (`shot`) and, if the test reads it, RobotStudio's Output window (`output-<when>.txt`).

`Run.verdict()` returns `("PASS", 0)` if every criterion is met, `("FAIL", 1)` if one was checked and not met, and
`("COULD NOT RUN", 2)` if some were never checked and none failed; use the number as the exit code.

## RobotStudio 2026 UIA facts

Verified with RobotStudio 2026.4; read before writing a test.

- **The shell is WinForms, not WPF.** Main window class `WindowsForms10.Window.8.app…`, title `RobotStudio`.
- **Ribbon tab Names carry the mnemonic**: `&File`, `&Home`, `&Modeling`, `&Simulation`, `&Controller`, `&RAPID`,
  `&Add-Ins`. Match with `title_re=r"^&?Home$"`; `tab()` tries both.
- **Ribbon buttons are named by command id, not caption**: `CmdBarCtl_<id>` (`CmdBarCtl_Options`, ...); dropdowns
  are MenuItems. Groups are Panes named by caption (`PowerPacs`). A PowerPac's button in the `PowerPacs` group may
  have an empty id: `load_powerpac` takes it by index.
- **The ribbon only works with RobotStudio in front.** In the background the tab content has no children and tab
  switching does nothing. `foreground()` handles it; a locked screen stops a run.
- **Ribbon TabItems never report themselves selected.** `tab()` clicks the tab and checks that a group only that tab
  shows is there (`TAB_GROUPS`).
- **Every wait watches for modal dialogs** and stops at once with the dialog's title, message and buttons
  (`DialogAppeared`) instead of timing out. `AUTO_ANSWERS` answers expected ones; `dialogs(pid, main)` reads any open
  dialog as text.
- **Never kill RobotStudio.** Its virtual controller (`RobVC.exe`) survives, and the next RobotStudio asks whether to
  terminate it. `shutdown()` / `rsuitest-close` close through the UI (`WM_CLOSE`; UIA `Close()` was ignored).
- **Never UIA-`Invoke` a button that opens a modal dialog**: it blocks until the dialog closes, then fails. Use
  `press(..., click=True)` (`open_dialog` does).
- **The first click right after a tab switch can be lost.** `click_until` checks for the result and clicks once more.
- **Home > Frame Size** opens a menu whose items are not in the UIA tree; `frame_size()` clicks the item's part of
  the popup (the one place that uses coordinates).
- **WinForms add-in modal dialogs are child Windows of the main window**, not top-level: `dialog(pid, title,
  owner=main)`. Their controls have `AutomationId` = WinForms `Control.Name`.
- **Screenshots copy screen pixels**: `shot()` refuses unless RobotStudio is in front, so it never saves another
  window.
- **Lookups are the cost, not clicks**: a pywinauto lookup in the main window takes ~0.4 s, a raw UIA `FindFirst`
  from the cached Ribbon pane ~30 ms. Use `ribbon()` for tabs, groups, buttons and dropdowns.
- **Wait for the virtual controller before acting** on a station with one (`wait_controllers_ready`): it starts in
  the background after the station opens. Changing the station before that can make RobotStudio throw
  `DeltaState is not open`.
- **RobotStudio's own exceptions** appear only in the Output window and in
  `C:\ProgramData\ABB\RobotStudio\ErrorLogs\`. `output_rows()` reads the whole Output window (it scrolls the grid);
  `Run.read_output` / `check_no_exceptions` turn that into a criterion.
- **Tests write into the station's project folder**: the virtual controller runs from `<project>\Systems\` and
  RobotStudio makes backups in `<project>\Backups\`. Copying only the `.rsstn` does not isolate a test.
- pywinauto 0.6.9: a wrapper (from `.wrapper_object()` / `.children()`) has no `child_window`, only a spec does.
  Enumerating `descendants()` of a whole dialog can take tens of seconds; look controls up by `auto_id` / `title`.

## Versioning

[Semantic Versioning](https://semver.org). Before 1.0.0 the minor version takes the role of the major one:

| Change | Examples | Next version |
|---|---|---|
| Breaking | A public name removed or renamed, a changed signature or default, a changed environment variable, command or argument, a changed `result.md` format or exit code | minor: 0.1.x → 0.2.0 |
| Compatible | A new helper, a bug fix, a more robust wait, a new UIA fact | patch: 0.1.0 → 0.1.1 |
| Documentation only | README, comments | no new tag |

The public API is: the names without a leading `_` in `rsuitest.core` and `rsuitest.pim`, the `rsuitest-*` commands
and their arguments, the `RSUITEST_*` environment variables, the `result.md` format and the exit codes 0/1/2, and the
template in `scripts/`. Everything else may change in any release.

1.0.0 comes when the API has been used by real test projects for a while without a breaking change; from then on a
breaking change raises the major version, a new feature the minor and a fix the patch.

Projects pin an exact tag, so nothing changes under them by accident. The version tells how much to check before
moving the pin: after a patch, run the tests; after a minor (before 1.0) or major, read the changes first.

## Known limitations

- Windows and RobotStudio 2026 only; names and ids were read off 2026.4 and may change in other versions.
- Needs the desktop: no headless runs, no locked screen, no other input during a run.
- One RobotStudio at a time. `start_robotstudio` refuses while RobotStudio or a virtual controller runs, and refuses to
  sideload while the add-in's `.rspak` is installed (`sideload=False` tests the installed package instead).
- The 3D view is not in the UIA tree. Check results in the saved station (`rsuitest.pim`) or leave that step to a
  person.
- `frame_size()` clicks by position inside the popup.
- No PyPI release; install from git with a tag.

## Licence

MIT, see [LICENSE.md](LICENSE.md). Copyright (c) 2026 Lagun 271 AB. Uses pywinauto, pywin32, psutil and Pillow as
installed libraries under their own licences.
