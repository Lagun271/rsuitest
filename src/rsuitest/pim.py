# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
"""Read object frame sizes from a saved station (.rsstn = zip with PIM.xml), for checks that must not depend on
looking at the 3D view. PIM.xml: <Target ID=..><Name Value=../>..<FrameSize Value="0.015"/>, same for <Frame>;
<DataDeclaration> also has <DataType Value="tooldata|wobjdata|robtarget|.."/>. Sizes in metres.

  rsuitest-pim <station.rsstn>          count of each (kind, FrameSize) pair (or: python -m rsuitest.pim ...)
"""
from __future__ import annotations

import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Obj:
    kind: str   # Target, Frame, or the DataType of a DataDeclaration (tooldata, wobjdata, robtarget, ...)
    id: str
    name: str
    size: float


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _value(el, child: str) -> str:
    c = next((c for c in el if _local(c.tag) == child), None)
    return "" if c is None else (c.get("Value") or "")


def _root(station: Path):
    """PIM.xml of the station, parsed. Opened read-shared, so RobotStudio may have it open."""
    with open(station, "rb") as f, zipfile.ZipFile(f) as z:
        return ET.fromstring(z.read(next(n for n in z.namelist() if n.lower().endswith("pim.xml"))))


def _child(el, name: str):
    return next((c for c in el if _local(c.tag) == name), None)


def objects(station: Path) -> list[Obj]:
    """Every element with a <FrameSize Value=.../> child."""
    root = _root(station)
    out = []
    for el in root.iter():
        size = _value(el, "FrameSize")
        if not size:
            continue
        tag = _local(el.tag)
        kind = (_value(el, "DataType") or tag) if tag == "DataDeclaration" else tag
        out.append(Obj(kind, el.get("ID", ""), _value(el, "Name"), float(size)))
    return out


def summary(objs) -> Counter:
    return Counter((o.kind, round(o.size, 4)) for o in objs)


def fmt_summary(objs) -> str:
    return ", ".join(f"{k} {v * 1000:g} mm x{n}" for (k, v), n in sorted(summary(objs).items()))


def task_colors(station: Path) -> Counter:
    """(task name, (R, G, B) 0-255) -> number of move instructions with that <Color>. The task is found by following
    <Parent ID=..> up to the first element whose tag ends with 'Task' (instruction > path procedure > task)."""
    root = _root(station)
    by_id = {el.get("ID"): el for el in root.iter() if el.get("ID") and len(el)}   # references (<Parent ID=../>) are empty

    def task_of(el):
        for _ in range(50):
            if el is None or _local(el.tag).endswith("Task"):
                break
            parent = _child(el, "Parent")
            el = by_id.get(parent.get("ID")) if parent is not None else None
        return _value(el, "Name") if el is not None else None

    out = Counter()
    for el in root.iter():
        color = _child(el, "Color")
        if _local(el.tag) == "MoveInstructionCall" and color is not None:
            out[(task_of(el), tuple(round(float(_value(color, k)) * 255) for k in ("Red", "Green", "Blue")))] += 1
    return out


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: rsuitest-pim <station.rsstn>")
    for (kind, v), n in sorted(summary(objects(Path(args[0]))).items()):
        print(f"{kind:24} {v:7.4f} m  x{n}")


if __name__ == "__main__":
    main()
