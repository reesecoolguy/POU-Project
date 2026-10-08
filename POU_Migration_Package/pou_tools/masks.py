"""SharePoint SPBasePermissions flags and role-definition masks.

Values are the documented SPBasePermissions enumeration. `tests/test_masks.py` proves that the built-in
Read level computed from flags equals the well-known Low=138612833 / High=176.
"""
from __future__ import annotations

FLAGS = {
    "EmptyMask": 0,
    "ViewListItems": 1 << 0,
    "AddListItems": 1 << 1,
    "EditListItems": 1 << 2,
    "DeleteListItems": 1 << 3,
    "ApproveItems": 1 << 4,
    "OpenItems": 1 << 5,
    "ViewVersions": 1 << 6,
    "DeleteVersions": 1 << 7,
    "CancelCheckout": 1 << 8,
    "ManagePersonalViews": 1 << 9,
    "ManageLists": 1 << 11,
    "ViewFormPages": 1 << 12,
    "Open": 1 << 16,
    "ViewPages": 1 << 17,
    "AddAndCustomizePages": 1 << 18,
    "ApplyThemeAndBorder": 1 << 19,
    "ApplyStyleSheets": 1 << 20,
    "ViewUsageData": 1 << 21,
    "CreateSSCSite": 1 << 22,
    "ManageSubwebs": 1 << 23,
    "CreateGroups": 1 << 24,
    "ManagePermissions": 1 << 25,
    "BrowseDirectories": 1 << 26,
    "BrowseUserInfo": 1 << 27,
    "AddDelPrivateWebParts": 1 << 28,
    "UpdatePersonalWebParts": 1 << 29,
    "ManageWeb": 1 << 30,
    "UseClientIntegration": 1 << 36,
    "UseRemoteAPIs": 1 << 37,
    "ManageAlerts": 1 << 38,
    "CreateAlerts": 1 << 39,
    "EditMyUserInfo": 1 << 40,
    "EnumeratePermissions": 1 << 62,
    "FullMask": (1 << 63) - 1,
}

READ_FLAGS = [
    "ViewListItems", "OpenItems", "ViewVersions", "ViewFormPages", "Open", "ViewPages",
    "CreateSSCSite", "BrowseUserInfo", "UseClientIntegration", "UseRemoteAPIs", "CreateAlerts",
]
CONTRIBUTE_EXTRA = ["AddListItems", "EditListItems", "DeleteListItems", "ManagePersonalViews",
                    "AddDelPrivateWebParts", "UpdatePersonalWebParts", "DeleteVersions", "CancelCheckout"]


def mask_of(names) -> int:
    m = 0
    for n in names:
        m |= FLAGS[n]
    return m


def split(mask: int):
    return {"Low": mask & 0xFFFFFFFF, "High": mask >> 32}


def join(low: int, high: int) -> int:
    return (int(high) << 32) | int(low)


READ_MASK = mask_of(READ_FLAGS)
BUILTIN_MASKS = {
    "Read": READ_MASK,
    "Contribute": READ_MASK | mask_of(CONTRIBUTE_EXTRA),
    "Full Control": FLAGS["FullMask"],
}
