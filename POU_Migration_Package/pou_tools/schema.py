"""Schema loader / validator / SchemaXml generator.

schema/lists.json is the single source of truth. This module is used by provisioning, the importer,
the fake SharePoint used in tests, the flow definitions checker and the app linter, so a column that is
renamed in one place and not another fails a test instead of failing on a cabinet PC.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"

RESERVED = {"ID", "Id", "Title", "Created", "Modified", "Author", "Editor", "Version", "Type", "Status",
            "ContentType", "Attachments", "Name", "FileRef", "Order", "Owshiddenversion"}
FIELD_TYPES = {"Text", "Note", "Number", "Currency", "Boolean", "Choice", "DateTime"}
MAX_INDEXES = 20
MAX_INTERNAL_NAME = 32

# Built-in columns every list has and flows/app may use
BUILTIN_FIELDS = {"ID", "Id", "Title", "Created", "Modified", "Author", "Editor", "AuthorId", "EditorId"}


class SchemaError(Exception):
    pass


@dataclass
class Field:
    name: str
    display: str
    type: str
    required: bool = False
    unique: bool = False
    indexed: bool = False
    max_length: int | None = None
    decimals: int | None = None
    min: float | None = None
    max: float | None = None
    default: object = None
    choices: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def is_indexed(self) -> bool:
        return self.indexed or self.unique

    def schema_xml(self) -> str:
        """SchemaXml for POST .../fields/createfieldasxml (Options=8 keeps the internal name)."""
        a = {
            "Type": self.type, "DisplayName": self.display, "Name": self.name, "StaticName": self.name,
            "Required": "TRUE" if self.required else "FALSE",
        }
        if self.is_indexed:
            a["Indexed"] = "TRUE"
        if self.unique:
            a["EnforceUniqueValues"] = "TRUE"
        if self.type == "Text":
            a["MaxLength"] = str(self.max_length or 255)
        if self.type == "Note":
            a["NumLines"] = "6"
            a["RichText"] = "FALSE"
        if self.type in ("Number", "Currency"):
            if self.decimals is not None:
                a["Decimals"] = str(self.decimals)
            if self.min is not None:
                a["Min"] = str(self.min)
            if self.max is not None:
                a["Max"] = str(self.max)
            if self.type == "Currency":
                a["LCID"] = "1033"
        if self.type == "DateTime":
            a["Format"] = "DateTime"
        if self.type == "Choice":
            a["Format"] = "Dropdown"
            a["FillInChoice"] = "FALSE"
        if self.description:
            a["Description"] = self.description
        attrs = " ".join(f"{k}={quoteattr(v)}" for k, v in a.items())
        inner = ""
        if self.type == "Choice":
            inner += "<CHOICES>" + "".join(f"<CHOICE>{escape(c)}</CHOICE>" for c in self.choices) + "</CHOICES>"
        d = self.default_xml()
        if d is not None:
            inner += f"<Default>{escape(d)}</Default>"
        return f"<Field {attrs}>{inner}</Field>"

    def default_xml(self):
        if self.default is None:
            return None
        if self.type == "Boolean":
            return "1" if self.default else "0"
        return str(self.default)


@dataclass
class ListDef:
    name: str
    description: str
    title_label: str
    fields: list[Field]
    growth: str = ""

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)

    @property
    def field_names(self):
        return [f.name for f in self.fields]

    @property
    def indexed_names(self):
        return [f.name for f in self.fields if f.is_indexed]

    @property
    def unique_names(self):
        return [f.name for f in self.fields if f.unique]


@dataclass
class Schema:
    version: str
    lists: dict[str, ListDef]
    raw: dict

    def __getitem__(self, name) -> ListDef:
        return self.lists[name]


def _field_from(d: dict) -> Field:
    return Field(
        name=d["name"], display=d.get("display", d["name"]), type=d["type"],
        required=d.get("required", False), unique=d.get("unique", False), indexed=d.get("indexed", False),
        max_length=d.get("maxLength"), decimals=d.get("decimals"), min=d.get("min"), max=d.get("max"),
        default=d.get("default"), choices=list(d.get("choices", [])), description=d.get("description", ""),
    )


def load_schema(path: Path | None = None) -> Schema:
    path = path or (SCHEMA_DIR / "lists.json")
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    lists: dict[str, ListDef] = {}
    for ld in raw["lists"]:
        fields = [_field_from(f) for f in ld["fields"]]
        lists[ld["name"]] = ListDef(ld["name"], ld.get("description", ""), ld.get("titleLabel", "Label"),
                                    fields, ld.get("growth", ""))
    s = Schema(raw["schemaVersion"], lists, raw)
    validate_schema(s)
    return s


def validate_schema(s: Schema) -> None:
    errs: list[str] = []
    for ln, ld in s.lists.items():
        if not ln.isalnum():
            errs.append(f"{ln}: list names must be alphanumeric (no spaces/underscores)")
        seen = set()
        for f in ld.fields:
            if f.name in seen:
                errs.append(f"{ln}.{f.name}: duplicate field")
            seen.add(f.name)
            if f.name in RESERVED:
                errs.append(f"{ln}.{f.name}: reserved name")
            if not f.name.isalnum() or f.name[0].isdigit():
                errs.append(f"{ln}.{f.name}: internal names must be alphanumeric and not start with a digit")
            if len(f.name) > MAX_INTERNAL_NAME:
                errs.append(f"{ln}.{f.name}: longer than {MAX_INTERNAL_NAME}")
            if f.type not in FIELD_TYPES:
                errs.append(f"{ln}.{f.name}: unknown type {f.type}")
            if f.unique and f.type not in ("Text", "Number"):
                errs.append(f"{ln}.{f.name}: unique only on Text/Number")
            if f.type == "Note" and (f.unique or f.indexed):
                errs.append(f"{ln}.{f.name}: Note columns cannot be indexed")
            if f.type == "Choice":
                if not f.choices:
                    errs.append(f"{ln}.{f.name}: Choice without choices")
                if f.default is not None and f.default not in f.choices:
                    errs.append(f"{ln}.{f.name}: default not in choices")
            if f.type == "Text" and (f.max_length or 255) > 255:
                errs.append(f"{ln}.{f.name}: single-line text max 255")
        if len(ld.indexed_names) > MAX_INDEXES:
            errs.append(f"{ln}: {len(ld.indexed_names)} indexes exceed {MAX_INDEXES}")
    if errs:
        raise SchemaError("; ".join(errs))


def load_settings_defaults() -> list[dict]:
    return json.loads((SCHEMA_DIR / "settings_defaults.json").read_text(encoding="utf-8"))["settings"]


def load_permissions() -> dict:
    return json.loads((SCHEMA_DIR / "permissions.json").read_text(encoding="utf-8"))
