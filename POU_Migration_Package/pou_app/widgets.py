"""Control builders and the pieces every operator screen shares (header, banner, item/location picker)."""
from __future__ import annotations

from . import formulas as F
from .spec import Ctl

NAVY, WHITE, INK, GREY = "RGBA(31, 56, 100, 1)", "RGBA(255, 255, 255, 1)", "RGBA(32, 32, 32, 1)", "RGBA(110, 110, 110, 1)"
GREEN, AMBER, RED, BLUE = "RGBA(198, 239, 206, 1)", "RGBA(255, 230, 153, 1)", "RGBA(255, 199, 206, 1)", "RGBA(221, 235, 247, 1)"
CLEAR = "RGBA(0, 0, 0, 0)"


def geo(x, y, w, h):
    return {"X": x, "Y": y, "Width": w, "Height": h}


def lbl(name, text, x, y, w, h, size=14, bold=False, color=INK, fill=CLEAR, align="Align.Left", visible=None, note=""):
    p = {**geo(x, y, w, h), "Text": text, "Size": size, "Color": color, "Fill": fill, "Align": align,
         "FontWeight": "FontWeight.Bold" if bold else "FontWeight.Normal", "Wrap": "true", "AutoHeight": "false"}
    if visible is not None:
        p["Visible"] = visible
    return Ctl(name, "label", p, note=note)


def btn(name, text, onselect, x, y, w, h, display=None, fill=NAVY, color=WHITE, size=16, visible=None, tab=None, note=""):
    p = {**geo(x, y, w, h), "Text": text, "OnSelect": onselect, "Fill": fill, "Color": color, "Size": size,
         "HoverFill": "ColorFade(" + fill + ", -15%)", "PressedFill": "ColorFade(" + fill + ", -30%)", "RadiusTopLeft": 4, "RadiusTopRight": 4,
         "RadiusBottomLeft": 4, "RadiusBottomRight": 4}
    if display:
        p["DisplayMode"] = display
    if visible is not None:
        p["Visible"] = visible
    if tab is not None:
        p["TabIndex"] = tab
    return Ctl(name, "button", p, note=note)


def inp(name, hint, x, y, w, h, onchange="", display=None, size=18, tab=None, default="", visible=None, note=""):
    p = {**geo(x, y, w, h), "HintText": f'"{hint}"', "Default": default or '""', "Size": size, "OnChange": onchange or "false",
         "DelayOutput": "false"}
    if display:
        p["DisplayMode"] = display
    if tab is not None:
        p["TabIndex"] = tab
    if visible is not None:
        p["Visible"] = visible
    return Ctl(name, "text", p, note=note)


def tmr(name, duration, ontimerend, repeat=True, start="true", note=""):
    """Tiny but VISIBLE (a Visible=false timer is not relied upon) transparent timer."""
    return Ctl(name, "timer", {"X": 0, "Y": 0, "Width": 6, "Height": 6, "Duration": duration, "Repeat": "true" if repeat else "false",
                               "AutoStart": "false", "Start": start, "OnTimerEnd": ontimerend, "Fill": CLEAR, "Color": CLEAR,
                               "BorderThickness": 0, "BorderColor": CLEAR, "DisplayMode": "DisplayMode.View"}, note=note)


def rect(name, x, y, w, h, fill, note=""):
    return Ctl(name, "rectangle", {**geo(x, y, w, h), "Fill": fill}, note=note)


def act(body: str) -> str:
    return F.ACT + ";\n" + body


# --------------------------------------------------------------------------------------------------------------------
NAV = [  # (key, caption, screen, visible-formula)
    ("Scan", "Add / Remove", "scrScan", "Not(varSupMode)"),
    ("Audit", "Count", "scrAudit", "true"),
    ("AddItem", "New item", "scrAddItem", "true"),
    ("Low", "Low stock", "scrLowStock", "true"),
    ("Hist", "History", "scrHistory", "true"),
    ("Sup", "Supervisor", "scrSupervisor", "varSupMode"),
    ("Admin", "Admin", "scrAdmin", "varSupMode"),
]


def header(p: str) -> list:
    """Visible employee + station identity, navigation, sign-out, idle countdown and the idle timer, on every operator screen."""
    c = [rect(f"recHdr{p}", 0, 0, 1366, 64, NAVY, "Header band"),
         lbl(f"lblHdrStation{p}", '"Station " & varStation', 12, 4, 260, 28, 16, True, WHITE, note="Station identity (always visible)"),
         lbl(f"lblHdrUser{p}", 'If(varSupMode, varEmpName & " (supervisor, signed in as " & User().Email & ")", varEmpName & " - badge session")',
             12, 32, 560, 28, 14, False, WHITE, note="Employee identity (always visible)"),
         lbl(f"lblHdrIdle{p}", '"Auto sign-out in " & Max(0, varIdleMin * 60 - DateDiff(varLastActivity, varTick, TimeUnit.Seconds)) & " s"',
             1040, 4, 200, 24, 12, False, WHITE, align="Align.Right", note="Idle countdown"),
         btn(f"btnHdrOut{p}", '"Sign out"', F.logout_block(), 1250, 12, 104, 40, fill="RGBA(192, 80, 77, 1)", note="Ends the server session"),
         tmr(f"tmrIdle{p}", "1000", "Set(varTick, Now());\nIf(\n    (Not(IsBlank(varSession)) Or varSupMode) And DateDiff(varLastActivity, varTick, TimeUnit.Seconds) >= varIdleMin * 60,\n    "
             + F.logout_block().replace("\n", "\n    ") + "\n)", note="Idle timeout checker (central setting IdleTimeoutMinutes)")]
    x = 580
    for key, cap, scr, vis in NAV:
        c.append(btn(f"btnNav{key}{p}", f'"{cap}"', act(f"Navigate({scr}, ScreenTransition.None)"), x, 18, 100 if len(cap) < 10 else 110, 36,
                     fill="RGBA(68, 114, 196, 1)", size=12, visible=vis, note=f"Go to {scr}"))
        x += 105 if len(cap) < 10 else 115
    return c


def banner(p: str, y=660) -> list:
    """Honest outcome banner + 'Retry same request'. Green appears ONLY for a request the server recorded as Succeeded."""
    fill = f"If(varOutKind = \"ok\", {GREEN}, varOutKind = \"bad\", {RED}, {AMBER})"
    return [lbl(f"lblBanner{p}", "varOutText", 24, y, 1000, 84, 18, True, INK, fill, visible="Not(IsBlank(varOutText))",
                note="Outcome of the last request: ok / waiting / unconfirmed / bad")]


def picker(p: str, y: int, on_select_extra=None, dm_lock="IsBlank(varReq)", qty_ctl: str | None = None, gal_h: int = 230) -> list:
    """Scan item (+ optional location). Uses context vars locSel (record), locMsg, locPending, locLastKey, locLocPending.
    on_select_extra(expr) -> extra record fields to put in the UpdateContext that sets locSel (e.g. the stock version)."""
    q = qty_ctl or f"txtQty{p}"
    extra = (lambda e: ", " + on_select_extra(e)) if on_select_extra else (lambda e: "")
    sel = lambda e: f"UpdateContext({{locSel: {e}{extra(e)}}})"
    edit = f"If({dm_lock}, DisplayMode.Edit, DisplayMode.View)"
    find = f"""{F.ACT};
UpdateContext({{locPending: false, locSel: Blank(), locMsg: ""}});
Reset({q}); Reset(txtLoc{p});
With(
    {{scan: {F.normalise(f"txtItem{p}.Text")}}},
    If(
        Len(scan) < varScanMin,
        UpdateContext({{locMsg: "Scan or type the item number."}}),
        Set(varLookupFailed, false);
        IfError(
            ClearCollect(colStock, SortByColumns(Filter(POUStockLocations, ItemID = scan, Active = true), "LocationCode", SortOrder.Ascending)),
            Set(varLookupFailed, true); Clear(colStock);
            UpdateContext({{locMsg: "Could not look the item up (network?). Nothing was changed. Scan it again."}})
        );
        If(
            Not(varLookupFailed),
            If(
                CountRows(colStock) = 0,
                UpdateContext({{locMsg: If(
                    Not(IsBlank(LookUp(POUItems, ItemID = scan))),
                    "Item " & scan & " exists but is not stocked in any active location. A supervisor can add a stocking location (New item screen).",
                    "Item " & scan & " was not found. Check the barcode, or ask a supervisor to add the item.")}}),
                CountRows(colStock) = 1,
                {sel("First(colStock)")}; SetFocus({q}),
                UpdateContext({{locMsg: "Item " & scan & " is stocked in " & CountRows(colStock) & " locations. Choose or scan the location."}});
                SetFocus(txtLoc{p})
            )
        )
    )
)"""
    loc = f"""{F.ACT};
UpdateContext({{locLocPending: false}});
With(
    {{loc: {F.normalise(f"txtLoc{p}.Text")}}},
    If(
        CountRows(colStock) = 0,
        UpdateContext({{locMsg: "Scan the item first."}}),
        IsBlank(LookUp(colStock, LocationCode = loc)),
        UpdateContext({{locSel: Blank(), locMsg: "Item " & First(colStock).ItemID & " is not stocked at " & loc & ". Choose a listed location, or ask a supervisor to add that location."}}),
        {sel("LookUp(colStock, LocationCode = loc)")}; UpdateContext({{locMsg: ""}}); SetFocus({q})
    )
)"""
    return [
        lbl(f"lblStep1{p}", '"1  Scan the item"', 24, y, 400, 24, 14, True, GREY),
        inp(f"txtItem{p}", "Scan or type item number", 24, y + 26, 420, 48,
            onchange="UpdateContext({locPending: true, locLastKey: Now()});\n" + F.ACT, display=edit, tab=1,
            note="Scanner target. Enter/Tab suffix from the scanner ends the scan; the timer commits it."),
        btn(f"btnFind{p}", '"Look up"', find, 452, y + 26, 100, 48, display=edit, fill="RGBA(68, 114, 196, 1)", tab=2, note="Resolves the scan; also called by the scan timer"),
        lbl(f"lblStep2{p}", '"2  Location (only when the item is in several places)"', 580, y, 520, 24, 14, True, GREY),
        inp(f"txtLoc{p}", "Scan or type location", 580, y + 26, 360, 48,
            onchange="UpdateContext({locLocPending: true, locLastKey: Now()});\n" + F.ACT, display=edit, tab=3,
            visible="CountRows(colStock) > 1", note="Second scan target"),
        btn(f"btnLoc{p}", '"Use location"', loc, 948, y + 26, 130, 48, display=edit, fill="RGBA(68, 114, 196, 1)", tab=4, visible="CountRows(colStock) > 1",
            note="Resolves the location scan; also called by the scan timer"),
        tmr(f"tmrScan{p}", "150",
            f"""If(
    locPending And DateDiff(locLastKey, Now(), TimeUnit.Milliseconds) >= varScanIdle,
    Select(btnFind{p})
);
If(
    locLocPending And DateDiff(locLastKey, Now(), TimeUnit.Milliseconds) >= varScanIdle,
    Select(btnLoc{p})
)""", note="Debounce: commits a scan once keystrokes stop for ScanCommitIdleMs, so Enter/Tab/no-suffix scanners all work"),
        lbl(f"lblMsg{p}", "locMsg", 24, y + 80, 1100, 30, 14, True, "RGBA(156, 0, 6, 1)", visible="Not(IsBlank(locMsg))", note="Lookup messages"),
        Ctl(f"galLoc{p}", "gallery.galleryVertical",
            {**geo(24, y + 116, 420, gal_h), "Items": "colStock", "TemplateSize": 56, "Visible": "CountRows(colStock) > 1",
             "TemplateFill": f"If(ThisItem.StockKey = locSel.StockKey, {BLUE}, {WHITE})",
             "OnSelect": f"{F.ACT};\n{sel('ThisItem')};\nUpdateContext({{locMsg: \"\"}});\nSetFocus({q})"},
            [lbl(f"lblGalLoc{p}", 'ThisItem.LocationCode & "   on hand: " & If(IsBlank(ThisItem.OnHandQty), "-", Text(ThisItem.OnHandQty))', 8, 8, 400, 40, 18, True)],
            note="Choose the location when an item is stocked in more than one place"),
    ]


def card(p: str, y: int) -> list:
    """What was scanned: name, location, on hand, status. Everything comes from the selected stock record."""
    return [
        lbl(f"lblName{p}", 'If(IsBlank(locSel), If(CountRows(colStock) > 1, First(colStock).ItemName & "  -  choose a location", ""), locSel.ItemName)',
            480, y, 860, 40, 24, True, note="Item name"),
        lbl(f"lblMeta{p}", 'If(IsBlank(locSel), "", "Item " & locSel.ItemID & "   |   Location " & locSel.LocationCode & "   |   Area " & Coalesce(locSel.Area, "-") & "   |   Min " & Coalesce(Text(locSel.MinQty), "-") & "   Max " & Coalesce(Text(locSel.MaxQty), "-"))',
            480, y + 42, 860, 28, 14, False, GREY, note="Identity of the exact stock record"),
        lbl(f"lblOnHand{p}", 'If(IsBlank(locSel), "", If(IsBlank(locSel.OnHandQty), "-", Text(locSel.OnHandQty)))', 480, y + 72, 200, 70, 44, True,
            note="On hand (blank = no verified quantity)"),
        lbl(f"lblStatus{p}",
            'If(IsBlank(locSel), "", IsBlank(locSel.OnHandQty), "NO VERIFIED QUANTITY - a supervisor must count this item/location first", locSel.BalanceStatus.Value = "Unverified", "Quantity not yet verified by a count", locSel.LowStockFlag, "LOW STOCK", "")',
            690, y + 82, 650, 50, 18, True, "RGBA(156, 87, 0, 1)", note="Server-computed status; the app never recomputes low stock"),
    ]


def runner(p: str, after_final: str) -> Ctl:
    """The ONE place on a screen that files-if-missing, processes and reads back a request. Entry buttons end with Select(btnRun<screen>)."""
    return Ctl(f"btnRun{p}", "button", {"X": 8, "Y": 8, "Width": 6, "Height": 6, "Text": '""', "Fill": CLEAR, "Color": CLEAR, "BorderThickness": 0,
                                        "OnSelect": F.run_post(after_final)},
               note="Tiny transparent button. Runs the shared posting procedure for the retained request varReq; never creates a new RequestID.")
