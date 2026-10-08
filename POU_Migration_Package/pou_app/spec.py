"""A tiny, explicit model of a canvas app: screens -> controls -> Power Fx property formulas.

One model feeds three outputs, so they can never disagree:
  * app/src/*.fx.yaml      - Power Apps source format ("As" syntax) for Studio paste / pac canvas pack (UNVALIDATED, see docs)
  * app/docs/CONTROL_REFERENCE.md - every control, type and formula, for building by hand if the paste route is not accepted
  * the static linter (lint.py)

Only classic controls are used (label, text, button, timer, gallery, rectangle): they are the most stable across Studio versions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# yaml control type token -> human name
CONTROL_TYPES = {
    "label": "Label", "text": "Text input", "button": "Button", "timer": "Timer",
    "rectangle": "Rectangle", "gallery.galleryVertical": "Vertical gallery",
}


@dataclass
class Ctl:
    name: str
    type: str
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    note: str = ""


@dataclass
class Screen:
    name: str
    title: str
    purpose: str
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)


def walk(ctls):
    for c in ctls:
        yield c
        yield from walk(c.children)


def _fx(val) -> str:
    """Property value -> Power Fx text beginning with '='."""
    s = val if isinstance(val, str) else str(val)
    s = s.strip("\n")
    return s if s.startswith("=") else "=" + s


def _emit_props(props: dict, indent: int, out: list):
    pad = " " * indent
    for k, v in props.items():
        fx = _fx(v)
        if "\n" in fx:
            out.append(f"{pad}{k}: |-")
            for line in fx.split("\n"):
                out.append(f"{pad}    {line}" if line.strip() else "")
        else:
            out.append(f"{pad}{k}: {fx}")


def _emit_ctl(c: Ctl, indent: int, out: list):
    pad = " " * indent
    out.append(f"{pad}{c.name} As {c.type}:")
    _emit_props(c.props, indent + 4, out)
    for ch in c.children:
        _emit_ctl(ch, indent + 4, out)


def screen_yaml(s: Screen) -> str:
    out = [f"{s.name} As screen:"]
    _emit_props(s.props, 4, out)
    for c in s.children:
        _emit_ctl(c, 4, out)
    return "\n".join(out) + "\n"


def app_yaml(props: dict) -> str:
    out = ["App As appinfo:"]
    _emit_props(props, 4, out)
    return "\n".join(out) + "\n"


def screen_markdown(s: Screen) -> str:
    md = [f"## {s.name} - {s.title}", "", s.purpose, ""]
    if s.props:
        md.append("**Screen properties**\n")
        for k, v in s.props.items():
            md += [f"- `{k}`", "  ```powerfx", *["  " + ln for ln in _fx(v).split("\n")], "  ```"]
        md.append("")
    md.append("| Control | Type | Purpose |")
    md.append("|---|---|---|")
    for c in walk(s.children):
        md.append(f"| `{c.name}` | {CONTROL_TYPES.get(c.type, c.type)} | {c.note} |")
    md.append("")
    for c in walk(s.children):
        formula_props = {k: v for k, v in c.props.items()
                         if k in ("Text", "Default", "Items", "OnSelect", "OnChange", "OnTimerEnd", "OnVisible", "DisplayMode", "Visible",
                                  "Start", "Duration", "HintText", "Fill", "Color", "TabIndex", "Reset", "AutoStart", "Repeat", "Format",
                                  "OnStart", "OnHidden", "BorderColor")
                         and not (isinstance(v, str) and len(v) < 18 and "(" not in v and k in ("Fill", "Color", "BorderColor"))}
        if not formula_props:
            continue
        md += [f"### `{c.name}` ({CONTROL_TYPES.get(c.type, c.type)})", ""]
        for k, v in formula_props.items():
            md += [f"**{k}**", "", "```powerfx", _fx(v), "```", ""]
    return "\n".join(md)
