# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
"""rsuitest: helpers for UI Automation tests of RobotStudio 2026 add-ins (pywinauto, backend "uia"). Generic: nothing
here knows a particular add-in. A test project sets ADDIN (the .rsaddin to sideload) and PACKAGE_GLOB (its installed
.rspak folder name) and may add its own ribbon tab to TAB_GROUPS. RS_EXE, ADDIN and PACKAGE_GLOB can also come from
the environment variables RSUITEST_RS_EXE, RSUITEST_ADDIN and RSUITEST_PACKAGE_GLOB (read at import).

Targets are found in the UI Automation tree (names, automation ids, control types), not by pixel coordinates (one
exception: frame_size). RobotStudio's shell and WinForms add-in dialogs are WinForms; facts about the tree are in
README.md.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psutil
from pywinauto import Application, Desktop

RS_EXE = Path(os.environ.get("RSUITEST_RS_EXE")
              or r"C:\Program Files (x86)\ABB\RobotStudio 2026\Bin\RobotStudio.exe")
# .rsaddin that start_robotstudio sideloads (/addin); set by the test project
ADDIN: Path | None = Path(os.environ["RSUITEST_ADDIN"]) if os.environ.get("RSUITEST_ADDIN") else None
# folder name of the add-in's installed .rspak, e.g. "Vendor.Product-*"
PACKAGE_GLOB: str | None = os.environ.get("RSUITEST_PACKAGE_GLOB") or None


# ---------------------------------------------------------------- output: console + run.log, step table with timing
class Tee:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(path, "a", encoding="utf-8")
        self._out = sys.stdout
        sys.stdout = self

    def write(self, s):
        self._out.write(s)
        self._f.write(s)

    def flush(self):
        self._out.flush()
        self._f.flush()


@dataclass
class Step:
    name: str
    seen: str = ""
    screenshot: str = ""
    seconds: float = 0.0
    ok: bool | None = None


@dataclass
class Run:
    test_id: str
    report_dir: Path
    steps: list[Step] = field(default_factory=list)
    t0: float = field(default_factory=time.perf_counter)
    unexpected: list[str] = field(default_factory=list)
    # Success criteria: id -> (what must be true, met?, evidence). The verdict is about these only; steps are the
    # means to get there. Declare them all up front with `criteria`, so one never reached shows as "not checked".
    criteria: dict[str, list] = field(default_factory=dict)
    exceptions: list[str] = field(default_factory=list)   # 'Exception' rows seen by read_output
    output_reads: int = 0

    def __post_init__(self):
        self.report_dir.mkdir(parents=True, exist_ok=True)
        Tee(self.report_dir / "run.log")
        print(f"== {self.test_id} {datetime.now():%Y-%m-%d %H:%M:%S}  report: {self.report_dir}")

    def step(self, name: str) -> "_StepCtx":
        return _StepCtx(self, Step(name))

    def declare(self, **criteria: str) -> None:
        for cid, text in criteria.items():
            self.criteria[cid] = [text, None, "not checked (run stopped before)"]

    def check(self, cid: str, ok: bool, evidence: str) -> bool:
        self.criteria[cid][1:] = [bool(ok), evidence]
        print(f"   {cid} {'MET' if ok else 'NOT MET'}: {evidence}")
        return bool(ok)

    def read_output(self, main, when: str) -> None:
        """Read RobotStudio's whole Output window into output-<when>.txt and keep its Exception rows (do it before
        each close: the window starts over with RobotStudio)."""
        rows = output_rows(main)
        (self.report_dir / f"output-{when}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        self.exceptions.extend(f"{when}: {r}" for r in rows if "exception" in r.lower())
        self.output_reads += 1

    def check_no_exceptions(self, cid: str) -> None:
        if self.output_reads:
            self.check(cid, not self.exceptions, "; ".join(self.exceptions) or f"none in {self.output_reads} reading(s)")

    def error(self, e: Exception, window=None) -> None:
        """Record an exception that stopped the run, with a screenshot of `window` if there is one."""
        self.unexpected.append(f"{type(e).__name__}: {e}")
        if window is not None:
            try:
                self.unexpected.append("screenshot: " + shot(window, self.report_dir / "error.png"))
            except Exception as e2:  # noqa: BLE001
                self.unexpected.append(f"no screenshot: {e2}")

    def verdict(self) -> tuple[str, int]:
        """PASS (0) if every criterion is met; FAIL (1) if any was checked and not met; COULD NOT RUN (2) if some
        were never checked (a step could not be done) and none failed."""
        states = [c[1] for c in self.criteria.values()]
        if states and all(s is True for s in states):
            return "PASS", 0
        if any(s is False for s in states):
            return "FAIL", 1
        return "COULD NOT RUN", 2

    def finish(self, verdict: str) -> None:
        total = time.perf_counter() - self.t0
        lines = [f"# {self.test_id} run {datetime.now():%Y-%m-%d %H:%M}", "",
                 f"**{verdict}** — total {total:.1f} s", ""]
        if self.criteria:
            lines += ["| Criterion | Must be true | Result | Evidence |", "|---|---|---|---|"]
            for cid, (text, ok, ev) in self.criteria.items():
                res = {True: "met", False: "**not met**", None: "not checked"}[ok]
                lines.append(f"| {cid} | {text} | {res} | {ev} |")
            lines.append("")
        lines += ["| Step | Seen | Screenshot | s |", "|---|---|---|---|"]
        for s in self.steps:
            shot = f"[{s.screenshot}]({s.screenshot})" if s.screenshot else "-"
            lines.append(f"| {s.name} | {s.seen} | {shot} | {s.seconds:.1f} |")
        if self.unexpected:
            lines += ["", "Unexpected:", *[f"- {u}" for u in self.unexpected]]
        if NOTED:
            lines += ["", "Noted, not part of the verdict (dialogs acknowledged automatically):",
                      *[f"- {n}" for n in NOTED]]
        (self.report_dir / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))


class _StepCtx:
    def __init__(self, run: Run, step: Step):
        self.run, self.step = run, step

    def __enter__(self) -> Step:
        self._t = time.perf_counter()
        print(f"-- {self.step.name}")
        return self.step

    def __exit__(self, et, ev, tb):
        self.step.seconds = time.perf_counter() - self._t
        if et is not None:
            self.step.seen = f"ERROR: {ev}"
            self.step.ok = False
        elif self.step.ok is None:   # finished without an error and without its own verdict: done
            self.step.ok = True
        self.run.steps.append(self.step)
        print(f"   {self.step.seen}  ({self.step.seconds:.1f} s)")
        return False  # re-raise


# ---------------------------------------------------------------- process: start RobotStudio with the add-in sideloaded
def processes(names=("RobotStudio.exe", "RobVC.exe")) -> list[psutil.Process]:
    """Running RobotStudio and virtual controller (RobVC) processes. A RobVC outlives a killed RobotStudio, and
    the next RobotStudio then asks whether to terminate it: close RobotStudio with `shutdown`, never kill it."""
    out = []
    for p in psutil.process_iter(["name", "create_time"]):
        if p.info["name"] in names:
            out.append(p)
    return out


def robotstudio_pids() -> list[int]:
    return [p.pid for p in processes(("RobotStudio.exe",))]


def robotstudio_version() -> str:
    """File version of RobotStudio.exe, e.g. 26.4.11894.0."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Item '{RS_EXE}').VersionInfo.FileVersion"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def installed_packages() -> list[str]:
    """Installed .rspak folders of the add-in under test (PACKAGE_GLOB); none if PACKAGE_GLOB is not set."""
    if not PACKAGE_GLOB:
        return []
    return glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "ABB", "DistributionPackages*", PACKAGE_GLOB))


def start_robotstudio(station: Path | None = None, sideload: bool = True) -> int:
    """No RobotStudio running and the add-in's .rspak not installed, then start RobotStudio 2026 with ADDIN
    sideloaded, optionally opening `station`. Returns the PID.
    sideload=False: no /addin, and the add-in's .rspak must be installed instead (tests of the installed package)."""
    if procs := processes():
        raise SystemExit(f"Already running: {[(p.info['name'], p.pid) for p in procs]}; `run.ps1 close` first. "
                         "(A leftover RobVC makes RobotStudio ask whether to terminate it.)")
    inst = installed_packages()
    if sideload and inst:
        raise SystemExit(f"Add-in package installed, uninstall it first (RobotStudio closed): {inst}")
    if not sideload and not inst:
        raise SystemExit("No add-in package installed to test.")
    if sideload and (ADDIN is None or not Path(ADDIN).exists()):
        raise SystemExit(f"{ADDIN} missing; build the add-in first.")
    if not RS_EXE.exists():
        raise SystemExit(f"{RS_EXE} missing.")
    addin = [f"/addin:{ADDIN}", "/LoadAddins"] if sideload else []
    p = subprocess.Popen([str(RS_EXE)] + addin + ([str(station)] if station else []))
    return p.pid


def attach(pid: int, timeout: float = 180):
    """Attach to the RobotStudio process and wait for its main window (the one with a 'Home' ribbon tab)."""
    import win32con
    import win32gui
    app = Application(backend="uia").connect(process=pid, timeout=timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in Desktop(backend="uia").windows(process=pid):
            try:
                if "RobotStudio" in w.window_text():
                    spec = app.window(handle=w.handle)
                    # Ribbon tab Names carry the mnemonic: '&Home', '&Add-Ins' (WinForms ribbon, not WPF).
                    if spec.child_window(title_re=r"^&?Home$", control_type="TabItem").exists(timeout=1):
                        # A narrow window collapses ribbon groups, which hides their buttons from UIA.
                        win32gui.ShowWindow(w.handle, win32con.SW_MAXIMIZE)
                        return app, spec
            except Exception:
                pass
        time.sleep(1)
    raise TimeoutError(f"No RobotStudio main window with a Home tab within {timeout:.0f} s (PID {pid})")


# ---------------------------------------------------------------- elements
RIBBON_TYPES = ("Button", "SplitButton", "MenuItem", "ListItem", "TabItem")


class DialogAppeared(RuntimeError):
    """A modal dialog blocks RobotStudio while a wait was running; its text is in the message."""


# Dialogs answered automatically during any wait and while closing: substring of the message -> button. A test adds
# the ones that are unrelated to what it checks (e.g. the virtual controller's own errors). Every automatic answer is
# printed and kept in NOTED, which Run.finish lists apart from the verdict.
AUTO_ANSWERS: dict[str, str] = {}
NOTED: list[str] = []
_DIALOG_CHECK_EVERY = 2.0


def watch_dialogs(target) -> None:
    """Raise DialogAppeared if a dialog of target's process is open that does not contain `target` itself (so
    waiting inside a dialog is fine), after answering the ones listed in AUTO_ANSWERS."""
    w = target.wrapper_object() if hasattr(target, "wrapper_object") else target
    own, p = set(), w
    while p is not None:                          # target and its ancestors: dialogs that contain it are expected
        own.add(p.handle)
        p = p.parent()
    top = w.top_level_parent()
    for d in dialogs(w.process_id(), top):
        if d.wrapper.handle in own or d.is_progress:
            continue
        if auto_answer(d):
            continue
        raise DialogAppeared(f"Dialog appeared: {d}")


def auto_answer(d: "Dialog") -> bool:
    """Answer `d` if AUTO_ANSWERS covers it; note it. Returns whether it did."""
    key = next((k for k in AUTO_ANSWERS if k in d.message and AUTO_ANSWERS[k] in d.buttons), None)
    if not key:
        return False
    note = f"{datetime.now():%H:%M:%S} answered {AUTO_ANSWERS[key]!r}: " + " ".join(str(d).split())
    print(f"   {note}")
    NOTED.append(note)
    d.answer(AUTO_ANSWERS[key])
    time.sleep(0.5)
    return True


def wait_until(cond, timeout: float, what: str, watch=None, every: float = 0.2):
    """Call `cond()` until it returns something truthy, and return that; TimeoutError after `timeout` s (cond is
    always tried at least once). With `watch` (a window), a dialog that appears stops the wait at once
    (watch_dialogs) instead of a timeout."""
    deadline = time.monotonic() + timeout
    next_check = time.monotonic() + _DIALOG_CHECK_EVERY
    while True:
        if result := cond():
            return result
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what}: not within {timeout:.0f} s")
        if watch is not None and time.monotonic() >= next_check:
            watch_dialogs(watch)
            next_check = time.monotonic() + _DIALOG_CHECK_EVERY
        time.sleep(every)


def click_until(control, done, what: str, unexpected: list[str] | None = None, timeout: float = 5):
    """Click `control` and wait for `done()` to return something truthy (returned). A click right after a tab switch
    or a long action can be lost, so click once more; the retry is noted in `unexpected`."""
    for attempt in (1, 2):
        press(control, click=True)
        try:
            return wait_until(done, timeout, what)
        except TimeoutError:
            if attempt == 2:
                raise
            if unexpected is not None:
                unexpected.append(f"{what}: first click had no effect, clicked again")


def find(parent, title: str | None = None, title_re: str | None = None,
         control_types: tuple[str | None, ...] = RIBBON_TYPES + (None,), timeout: float = 15):
    """Find a descendant by exact Name (title) or regex (title_re), trying the given control types in order.
    A None type means 'any type' (full tree scan: slow in RobotStudio, so keep it last). Stops on a dialog."""
    def first():
        for ct in control_types:
            kw = {"title": title} if title is not None else {"title_re": title_re}
            spec = parent.child_window(found_index=0, **kw, **({"control_type": ct} if ct else {}))
            try:
                if spec.exists(timeout=0.5):
                    return spec
            except Exception:
                pass
    return wait_until(first, timeout, f"{title or title_re} {control_types}", watch=parent, every=0.5)


_RIBBON_CACHE: dict[int, object] = {}   # main window handle -> the Ribbon pane's IUIAutomationElement


def _ribbon_element(main):
    from pywinauto.uia_defines import IUIA
    h = main.wrapper_object().handle if hasattr(main, "wrapper_object") else main.handle
    el = _RIBBON_CACHE.get(h)
    if el is not None:
        try:
            el.CurrentName   # still alive?
            return el
        except Exception:
            pass
    el = main.child_window(title="Ribbon", control_type="Pane").wrapper_object().element_info.element
    _RIBBON_CACHE[h] = el
    return el


def ribbon(main, names: str | tuple[str, ...], control_type: str, timeout: float = 15, required: bool = True):
    """A control in the ribbon (tab, group Pane, button, dropdown) by exact Name, any of `names`. Searches from the
    Ribbon pane, found once per window and kept: ~30 ms per lookup instead of ~400 ms for a pywinauto lookup in the
    whole window (which also re-resolves any parent spec every time; measured 2026-10-25). Not for gallery items:
    those open in a popup Menu outside the Ribbon. Watches for dialogs while waiting. Returns a wrapper, or None if
    not found and not `required`."""
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.uia_defines import IUIA
    from pywinauto.uia_element_info import UIAElementInfo
    iuia = IUIA()
    names = (names,) if isinstance(names, str) else names
    by_name = [iuia.iuia.CreatePropertyCondition(30005, n) for n in names]           # UIA_NamePropertyId
    name_cond = by_name[0] if len(by_name) == 1 else iuia.iuia.CreateOrConditionFromArray(by_name)
    cond = iuia.iuia.CreateAndCondition(
        name_cond, iuia.iuia.CreatePropertyCondition(30003, iuia.known_control_types[control_type]))  # ControlType
    try:
        el = wait_until(lambda: _ribbon_element(main).FindFirst(4, cond),                # TreeScope_Descendants
                        timeout, f"in the ribbon: {names} ({control_type})", watch=main)
    except TimeoutError:
        if required:
            raise
        return None
    return UIAWrapper(UIAElementInfo(el))


def foreground(spec) -> None:
    """Bring the window to the front. RobotStudio's ribbon only switches tabs and builds its content (UIA children)
    while the window is in front. Windows refuses SetForegroundWindow from a background process unless it just
    received input, hence the synthetic Alt press; minimise + restore as a last resort."""
    import win32api
    import win32con
    import win32gui
    h = (spec.wrapper_object() if hasattr(spec, "wrapper_object") else spec).handle
    for _ in range(5):
        if win32gui.GetForegroundWindow() == h:
            return
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        try:
            win32gui.ShowWindow(h, win32con.SW_RESTORE if win32gui.IsIconic(h) else win32con.SW_SHOW)
            win32gui.SetForegroundWindow(h)
        except Exception:
            win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
        time.sleep(1)
    raise RuntimeError("Could not bring RobotStudio to the front")


def press(spec, timeout: float = 15, click: bool = False):
    """Activate a control: its UIA pattern first (Invoke, then SelectionItem), a real click at its centre last.
    click=True: click only, for a button that opens a modal dialog (Invoke blocks until the dialog closes, minutes,
    then fails). A click hits screen coordinates, so the control's window is brought to the front first; otherwise
    the click lands in whatever window covers it.
    Each lookup searches RobotStudio's whole UIA tree (~0.4 s; spec.wait polls it, ~1.2 s), while the click itself
    takes 0.12 s (measured 2026-10-25), so resolve once and wait only if the control isn't there or enabled yet."""
    if not hasattr(spec, "wrapper_object"):   # already a wrapper (e.g. from ribbon())
        w = spec
        deadline = time.monotonic() + timeout
        while not w.is_enabled():
            if time.monotonic() > deadline:
                raise TimeoutError(f"{w.window_text()!r} not enabled within {timeout:.0f} s")
            time.sleep(0.2)
    else:
        try:
            w = spec.wrapper_object()
            if not w.is_enabled():
                raise RuntimeError("not enabled yet")
        except Exception:
            w = spec.wait("exists enabled", timeout=timeout)
    if click:
        # A modal dialog that doesn't contain the target covers or blocks it (ribbon() finds controls behind a modal
        # too): stop instead of clicking whatever is at that screen position (2026-10-25: a click meant for Teach
        # Target landed on an open Options dialog).
        watch_dialogs(w)
        foreground(w.top_level_parent())
        w.click_input()
        return w

    def select():
        w.iface_selection_item.Select()
        time.sleep(0.3)
        if not w.is_selected():
            raise RuntimeError("Select() had no effect")

    def click():
        foreground(w.top_level_parent())
        w.click_input()

    for do in (lambda: w.iface_invoke.Invoke(), select, click):
        try:
            do()
            return w
        except Exception:
            continue
    raise RuntimeError(f"Could not activate {w.window_text()!r}")


def menu_item(main, menu: str, item: str, timeout: float = 15):
    """Click `item` (a MenuItem, e.g. 'GalleryItem_ToolCreateWorkobject') in ribbon dropdown `menu`
    (e.g. 'CmdBarCtl_GalleryCreateMisc'). Clicking the dropdown toggles it, so open it only if the item isn't shown
    (the items stay in the UIA tree, invisible, after the dropdown closes)."""
    spec = main.child_window(title=item, control_type="MenuItem", found_index=0)
    if not (spec.exists(timeout=1) and spec.is_visible()):
        press(ribbon(main, menu, "MenuItem"), click=True)
    return press(find(main, title=item, control_types=("MenuItem",), timeout=timeout), click=True)


FRAME_SIZES = ("Large", "Medium", "Small")


def frame_size(main, size: str, unexpected: list[str] | None = None) -> None:
    """Home > Frame Size > `size` (needs a station; also sets the per-user default). The popup's items are not in the
    UIA tree and typing the mnemonic swallowed the next Ctrl+S, so click the item's third of the popup (2026-10-27)."""
    from pywinauto import mouse
    popup = main.child_window(title="Menu_MenuFrameSize", control_type="Menu", found_index=0)
    is_open = lambda: popup.exists(timeout=0) and popup.is_visible()  # noqa: E731
    click_until(ribbon(main, "CmdBarCtl_MenuFrameSize", "MenuItem"), is_open, "Frame Size menu", unexpected, timeout=3)
    r = popup.rectangle()
    mouse.click(coords=((r.left + r.right) // 2, r.top + (2 * FRAME_SIZES.index(size) + 1) * r.height() // 6))
    wait_until(lambda: not is_open(), 3, f"Frame Size menu closed after {size}")


def dialog(pid: int, title: str, timeout: float = 15, owner=None):
    """A dialog window of the process: top-level, or (WinForms add-in modal dialogs) a child Window of `owner`, the main
    window. Raises DialogAppeared if a different dialog shows up instead."""
    specs = [Desktop(backend="uia").window(title=title, process=pid, found_index=0)]
    if owner is not None:
        specs.append(owner.child_window(title=title, control_type="Window", found_index=0))

    def shown():
        for spec in specs:
            try:
                if spec.exists(timeout=0.5) and spec.is_visible():
                    return spec
            except Exception:
                pass
        if owner is not None and (other := [d for d in dialogs(pid, owner) if d.title != title and not d.is_progress]):
            raise DialogAppeared(f"Waiting for {title!r}, but another dialog appeared: {other[0]}")
    return wait_until(shown, timeout, f"dialog {title!r}", every=0)


# A group (Pane under RibbonTabContent) that only the tab of that name shows: the reliable "tab is selected" check,
# since the ribbon's TabItems never report SelectionItem.IsSelected (verified 2026-10-25).
TAB_GROUPS = {"Home": "Build Station", "Simulation": "Simulation Control", "Add-Ins": "PowerPacs"}   # a test project adds its own tab


def tab(main, name: str, timeout: float = 30):
    """Select ribbon tab `name` (a key of TAB_GROUPS: 'Home', 'Add-Ins', ...). Clicks are lost while RobotStudio is busy (e.g. a
    station still starting its controller), so click until the tab's group is shown."""
    t = ribbon(main, (f"&{name}", name), "TabItem")
    shown = lambda wait: ribbon(main, TAB_GROUPS[name], "Pane", timeout=wait, required=False)  # noqa: E731
    deadline = time.monotonic() + timeout
    while True:
        if shown(0):
            return t
        press(t, click=True)
        if shown(1):
            return t
        watch_dialogs(main)
        if time.monotonic() > deadline:
            raise TimeoutError(f"Tab {name!r} not selected within {timeout:.0f} s")
        time.sleep(1)


def simulation_time(main) -> float | None:
    """Seconds shown in the status bar's simulation time ('Simulation Time: 57,4s'; the pane's UIA Name is
    'SimulationTimePane', the text is only in its LegacyIAccessible Value; 2026-11-06). None if not shown."""
    pane = main.child_window(title="SimulationTimePane", control_type="Pane", found_index=0)
    if not pane.exists(timeout=1):
        return None
    m = re.search(r"([\d.,]+)\s*s", pane.wrapper_object().legacy_properties().get("Value", ""))
    return float(m.group(1).replace(",", ".")) if m else None


def simulation_play(main, timeout: float = 60) -> float:
    """Simulation > Play; waits until the simulation time increases (the program runs). Returns the time seen."""
    tab(main, "Simulation")
    start = simulation_time(main) or 0.0
    press(ribbon(main, "CmdBarCtl_SimulationPlay", "Button"), click=True)
    return wait_until(lambda: (t := simulation_time(main)) is not None and t > start + 0.5 and t, timeout,
                      "simulation time to increase after Play")


def simulation_stop(main) -> None:
    """Simulation > Stop."""
    tab(main, "Simulation")
    press(ribbon(main, "CmdBarCtl_SimulationStop", "Button"), click=True)


def load_powerpac(main, tab_name: str, index: int = 0):
    """Add-Ins > PowerPacs > button `index` of the PowerPacs group; waits for the PowerPac's ribbon tab `tab_name`."""
    tab(main, "Add-Ins")
    press(ribbon(main, "PowerPacs", "Pane").children(control_type="Button")[index])
    return ribbon(main, (f"&{tab_name}", tab_name), "TabItem", timeout=90)   # lazy PowerPac load


def open_dialog(pid: int, main, button: str, title: str, unexpected: list[str] | None = None):
    """Click ribbon button `button` (e.g. 'CmdBarCtl_Options') that opens modal dialog `title`."""
    def opened():
        try:
            return dialog(pid, title, owner=main, timeout=0)
        except TimeoutError:
            return None
    return click_until(ribbon(main, button, "Button"), opened, f"{button} opens {title!r}", unexpected, timeout=10)


def close_dialog(dlg, auto_id: str, unexpected: list[str] | None = None) -> None:
    """Click button `auto_id` (e.g. 'btnClose') until dialog `dlg` is gone (a click right after Apply resizing 300+
    objects was lost, 2026-10-25)."""
    click_until(dlg.child_window(auto_id=auto_id), lambda: not dlg.exists(timeout=0),
                f"{auto_id} closes {dlg.window_text()!r}", unexpected)


def set_number(dlg, auto_id: str, value: int) -> str:
    """Type into a WinForms NumericUpDown (UIA Spinner with an Edit child); Tab commits it. Returns the shown text."""
    edit = dlg.child_window(auto_id=auto_id).child_window(control_type="Edit").wrapper_object()
    edit.click_input()
    edit.type_keys(f"^a{value}{{TAB}}")
    return edit.window_text()


def number(dlg, auto_id: str) -> str:
    return dlg.child_window(auto_id=auto_id).child_window(control_type="Edit").wrapper_object().window_text()


def open_station(main, path: Path) -> None:
    """Ctrl+O, type `path` into the standard Windows Open dialog (a child Window of the main window), Enter."""
    foreground(main)
    main.type_keys("^o")
    dlg = wait_until(lambda: next((c for c in main.wrapper_object().children()
                                   if c.element_info.class_name == "#32770" and c.window_text() == "Open"), None),
                     15, "Open dialog")
    edit = next(e for e in dlg.descendants(control_type="Edit") if e.element_info.automation_id == "1148")
    edit.set_edit_text(str(path))
    edit.type_keys("{ENTER}")


def panel_button(main, panel: str, button: str, timeout: float = 15):
    """A button (Create, Close, Clear) of a RobotStudio modeless panel such as 'Create Frame'. The outer Pane named
    `panel` holds the button row; there is another 'Close' elsewhere, so never search the whole window."""
    outer = find(main, title=panel, control_types=("Pane",), timeout=timeout)
    return find(outer, title=button, control_types=("Button",), timeout=timeout)


def save(main, path: Path, timeout: float = 120) -> None:
    """Ctrl+S, then wait until the station file is rewritten (mtime changes and stays put for 2 s)."""
    before = path.stat().st_mtime
    foreground(main)
    main.type_keys("^s")

    def written():
        m = path.stat().st_mtime
        if m == before:
            return False
        time.sleep(2)
        return path.stat().st_mtime == m
    wait_until(written, timeout, f"{path.name} saved", watch=main, every=1)


@dataclass
class Dialog:
    title: str
    message: str
    buttons: list[str]
    wrapper: object = field(repr=False)

    def __str__(self):
        return f"[{self.title}] {self.message} {self.buttons}"

    @property
    def is_progress(self) -> bool:
        """RobotStudio's progress window (e.g. '87% <station>.rsstn' [Cancel] while a station loads): busy, not a
        question. Waits keep waiting through it."""
        return self.buttons == ["Cancel"] and re.search(r"\d+%", self.message) is not None

    def answer(self, button: str) -> None:
        """Click `button`. click_input clicks screen coordinates, so the dialog's window must be in front first,
        otherwise the click lands in whatever window covers it (seen 2026-10-25: the Claude app)."""
        b = next(c for c in self.wrapper.descendants(control_type="Button") if c.window_text() == button)
        foreground(self.wrapper.top_level_parent())
        b.click_input()


def dialogs(pid: int, main=None) -> list[Dialog]:
    """Open dialogs of the process, read as text: visible top-level windows other than the main window, and child
    Windows of the main window (add-in dialogs, RobotStudio's save prompt), each with at least one titled button.
    Hidden 2x2 helper windows are skipped. Used to stop on, or answer, dialogs instead of timing out blind."""
    mw = None if main is None else main.wrapper_object() if hasattr(main, "wrapper_object") else main
    h = mw.handle if mw is not None else None
    cands = [w for w in Desktop(backend="uia").windows(process=pid) if w.handle != h]
    if mw is not None:
        cands += [c for c in mw.children() if c.element_info.control_type == "Window"]
    out = []
    for w in cands:
        try:
            r = w.rectangle()
            if r.width() < 20 or r.height() < 20 or not w.is_visible():
                continue
            buttons = [b.window_text() for b in w.descendants(control_type="Button") if b.window_text()]
            if not buttons or len(buttons) > 8:   # not a message box (e.g. the main window itself)
                continue
            texts = [t.window_text() for t in w.descendants(control_type="Text")
                     if t.window_text() and t.window_text() not in buttons]
            out.append(Dialog(w.window_text(), " ".join(texts), buttons, w))
        except Exception:
            pass
    return out


def main_window(pid: int):
    """The main window spec of a running RobotStudio (no wait for the Home tab, works with a dialog open)."""
    app = Application(backend="uia").connect(process=pid, timeout=10)
    # The largest one: message boxes are top-level windows titled "RobotStudio" too.
    wins = [w for w in Desktop(backend="uia").windows(process=pid) if "RobotStudio" in w.window_text()]
    if not wins:
        raise RuntimeError(f"No RobotStudio main window (PID {pid})")
    w = max(wins, key=lambda w: w.rectangle().width() * w.rectangle().height())
    return app, app.window(handle=w.handle)


def shutdown(pid: int, discard: bool = False, terminate_vc: bool = False, timeout: float = 120) -> list[str]:
    """Close RobotStudio through its own UI and wait for the process to exit. Answers 'unsaved changes' with No only
    if discard, and 'virtual controllers are running ... terminated?' with Yes only if terminate_vc; any other dialog
    raises with its text. Returns what was answered."""
    import win32con
    import win32gui
    app, main = main_window(pid)
    h = main.wrapper_object().handle
    done, last_error = [], None
    # WM_CLOSE = the window's X button. UIA WindowPattern.Close() was ignored by an idle RobotStudio (2026-10-25).
    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
    deadline = time.monotonic() + timeout
    resend = time.monotonic() + 15
    # psutil, not app.is_process_running(): that said "exited" 1.5 s after WM_CLOSE while the process still ran.
    while psutil.pid_exists(pid):
        if time.monotonic() > resend and win32gui.IsWindow(h):
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)   # ignored while busy (e.g. still loading): again
            resend = time.monotonic() + 15
        try:
            open_dialogs = dialogs(pid, main)
        except Exception as e:   # e.g. the main window is gone while the process exits
            open_dialogs, last_error = [], f"{type(e).__name__}: {e}"
        for d in open_dialogs:
            if d.is_progress or auto_answer(d):
                continue
            if "unsaved changes" in d.message and discard and "No" in d.buttons:
                d.answer("No")
            elif "virtual controllers are running" in d.message and terminate_vc and "Yes" in d.buttons:
                d.answer("Yes")
            else:
                raise RuntimeError(f"Dialog while closing: {d}")
            done.append(str(d))
        if time.monotonic() > deadline:
            raise TimeoutError(f"RobotStudio {pid} did not exit within {timeout:.0f} s "
                               f"(last error reading dialogs: {last_error})")
        time.sleep(1)
    # Its virtual controller normally stops shortly after; wait for that, so the next start finds nothing running.
    # One whose start failed (see wait_controllers_ready) stays: end it, as RobotStudio's "terminate?" prompt would.
    vc_deadline = time.monotonic() + 30
    while not robotstudio_pids() and processes(("RobVC.exe",)) and time.monotonic() < vc_deadline:
        time.sleep(1)
    if not robotstudio_pids():
        for p in processes(("RobVC.exe",)):
            note = f"{datetime.now():%H:%M:%S} RobVC {p.pid} still running 30 s after RobotStudio exited: ended it"
            print(f"   {note}")
            NOTED.append(note)
            p.terminate()
            p.wait(30)
    return done


def text(parent, auto_id: str) -> str:
    return parent.child_window(auto_id=auto_id).wait("exists", timeout=5).window_text()


def shot(wrapper_or_spec, path: Path) -> str:
    """Screenshot of the element's screen rectangle: grabs screen pixels, so whatever window is on top is captured.
    Refuses unless the element's top-level window is in front, so it never saves another app's window."""
    import win32gui
    w = wrapper_or_spec.wrapper_object() if hasattr(wrapper_or_spec, "wrapper_object") else wrapper_or_spec
    top = w.top_level_parent()
    if win32gui.GetForegroundWindow() != top.handle:
        top.set_focus()
        time.sleep(0.5)
    if win32gui.GetForegroundWindow() != top.handle:
        raise RuntimeError(f"Not taking {path.name}: {top.window_text()!r} is not in front")
    w.capture_as_image().save(path)
    return path.name


# ---------------------------------------------------------------- Output window, add-in log files
LOG_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+ (.*)$")


def output_rows(main) -> list[str]:
    """All rows of RobotStudio's Output window as 'message | time | category'. The window is a DataGrid that only
    exposes the rows in view, so scroll it top to bottom and collect. RobotStudio's own exceptions show up only here
    (e.g. 'Exception: DeltaState is not open', 2026-10-25), not in an add-in's own log."""
    grid = main.child_window(control_type="DataGrid", found_index=0).wrapper_object()
    rows: list[str] = []

    def read():
        for r in grid.children(control_type="DataItem"):
            text = " | ".join(t.window_text().replace("\n", " ").strip()
                              for t in r.descendants(control_type="Text") if t.window_text())
            if text and text not in rows:
                rows.append(text)

    try:
        sp = grid.iface_scroll
        scrollable = sp.CurrentVerticallyScrollable
    except Exception:
        scrollable = False
    if not scrollable:
        read()
        return rows
    step = max(sp.CurrentVerticalViewSize * 0.8, 1.0)
    pct = 0.0
    while True:
        sp.SetScrollPercent(-1, min(pct, 100.0))      # -1 = leave horizontal as is
        time.sleep(0.1)
        read()
        if pct >= 100:
            break
        pct += step
    return rows


def wait_controllers_ready(main, timeout: float = 180) -> str:
    """Wait until the station's virtual controller has started and is mapped to the station: its event log is
    mirrored into the Output window (rows with category 'Event Log'). It starts in the background after the station
    opens. Acting before that (e.g. an add-in's dialog that changes the station) races its start-up: RobotStudio then throws 'DeltaState is
    not open' in StationVcMapper.PostRestartHandling and shows 'There was a problem with the virtual controller'
    (2026-10-25, ErrorLogs). Only for stations with a controller. Returns the first Event Log row."""
    return wait_until(lambda: next((r for r in output_rows(main) if r.endswith("| Event Log")), None),
                      timeout, "virtual controller event in the Output window", watch=main, every=2)


LogMark = tuple[str | None, int]   # (raw first line, timestamp included; number of lines)


def _raw_log(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _strip(lines: list[str]) -> list[str]:
    return [m.group(2) if (m := LOG_LINE.match(l)) else l for l in lines]


def read_log(path: Path) -> list[str]:
    """All lines of an add-in's log file, timestamps ('yyyy-mm-dd hh:mm:ss.fff ') stripped."""
    return _strip(_raw_log(path))


def log_mark(path: Path) -> LogMark:
    """Where the log stands now. Take one before a step and use log_after(path, mark) for the step's own lines
    (timestamps proved unreliable for that). The first line tells a log that was emptied and written again (an
    add-in that clears its log when it loads) from the same log grown: a line count alone cannot."""
    raw = _raw_log(path)
    return (raw[0] if raw else None, len(raw))


def log_after(path: Path, mark: LogMark) -> list[str]:
    """Log lines written since `mark`: all of them if the log was started over, else those after the marked count."""
    raw = _raw_log(path)
    first, count = mark
    if not raw or raw[0] != first or len(raw) < count:
        return _strip(raw)
    return _strip(raw[count:])


def wait_log(path: Path, mark: LogMark, text: str, count: int = 1, timeout: float = 10) -> list[str]:
    """Wait until `count` lines after `mark` contain `text` (they can come seconds after the click), then return
    all lines after `mark`. Returns them anyway after `timeout`: the caller's criterion decides."""
    try:
        wait_until(lambda: sum(text in l for l in log_after(path, mark)) >= count, timeout, text, every=0.5)
    except TimeoutError:
        pass
    return log_after(path, mark)
