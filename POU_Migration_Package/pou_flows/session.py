"""POU-Session: badge login / logout. The badge is IDENTIFICATION only; the session is bound to the Microsoft account that called."""
from __future__ import annotations

from .common import DEFAULT_SITE_URL, L_EMPLOYEES, L_SESSIONS, L_STATIONS, MESSAGES, load_settings, ops_event, preamble, cfgi
from .core import checks, code_if, in_, msg_of
from .dsl import ALL, Block, Ex, Flow, X, and_, cat, coalesce, eq, f, if_, is_null, not_, nz, o, or_, powerapps_trigger, qv, trig_input, v

RESP_SCHEMA = {"type": "object", "properties": {k: {"type": "string"} for k in ("ok", "code", "message", "sessionId", "employeeName", "role", "idleMinutes")}}

SESSION_MESSAGES = {
    "INVALID_BADGE": "Badge not recognised. Try again or see a supervisor.",
    "BADGE_INACTIVE": "This badge is not active. See a supervisor.",
    "STATION_INVALID": "This station is not set up or is inactive. See a supervisor.",
    "STATION_ACCOUNT_MISMATCH": "This station only accepts its assigned Microsoft account.",
    "BAD_MODE": "Unknown session request.",
}


def build(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-Session", "POU - Session (badge login/logout)",
              "Instant flow. LOGIN validates the badge and station and creates a session bound to the calling Microsoft account. LOGOUT ends it.",
              powerapps_trigger([("Mode", "LOGIN or LOGOUT"), ("BadgeID", "Typed or scanned badge"), ("StationID", "Station"),
                                 ("SessionID", "For LOGOUT"), ("ClientAccount", "Signed-in account as reported by the app (used only if the platform header is absent)")]))
    root = preamble(fl, site_url)
    for n, t, val in [("vOk", "string", "no"), ("vCode", "string", "ERROR"),
                      ("vMessage", "string", "Could not complete the request. Try again."), ("vSessionId", "string", ""),
                      ("vName", "string", ""), ("vRole", "string", "")]:
        root.init_var(n, t, val)
    root.compose("Compose_Mode", X("toUpper(trim(string(coalesce(" + str(trig_input(0)) + ", ''))))"))
    root.compose("Compose_Badge", X("trim(replace(string(coalesce(" + str(trig_input(1)) + ", '')), '*', ''))"))
    root.compose("Compose_StationIn", X("trim(string(coalesce(" + str(trig_input(2)) + ", '')))"))
    root.compose("Compose_SessionIn", X("trim(string(coalesce(" + str(trig_input(3)) + ", '')))"))
    root.compose("Compose_Header", X("coalesce(triggerOutputs()?['headers']?['x-ms-user-email-encoded'], '')"))
    root.compose("Compose_AppAccount", X("toLower(if(empty(outputs('Compose_Header')), trim(string(coalesce(" + str(trig_input(4)) + ", ''))), decodeBase64(outputs('Compose_Header'))))"))

    def work(w: Block):
        load_settings(w)
        w.compose("Compose_Messages", {**MESSAGES, **SESSION_MESSAGES})
        w.cond("If_login", eq(o("Compose_Mode"), "LOGIN"), login)
        w.cond("If_logout", eq(o("Compose_Mode"), "LOGOUT"), logout)
        w.cond("If_bad_mode", Ex("not(contains(createArray('LOGIN', 'LOGOUT'), outputs('Compose_Mode')))"),
               lambda u: u.set_many("Set_bad_mode", {"vCode": "BAD_MODE", "vMessage": X(msg_of("BAD_MODE"))}))

    def login(t: Block):
        t.sp_get("Get_employee", L_EMPLOYEES, ["BadgeID eq '", qv(coalesce(o("Compose_Badge"), "NONE")), "'"], select="Id,BadgeID,EmployeeName,Active,Role", top=2)
        t.compose("Compose_Emp", X("first(body('Get_employee')?['d']?['results'])"))
        t.sp_get("Get_station", L_STATIONS, ["StationID eq '", qv(coalesce(o("Compose_StationIn"), "NONE")), "'"], select="Id,StationID,Active,ExpectedAccountUPN", top=2)
        t.compose("Compose_Stn", X("first(body('Get_station')?['d']?['results'])"))
        checks(t, "Login", [
            ("badge_known", code_if(is_null(o("Compose_Emp")), "INVALID_BADGE")),
            ("badge_active", code_if(and_(not_(is_null(o("Compose_Emp"))), not_(eq(Ex("outputs('Compose_Emp')?['Active']"), True))), "BADGE_INACTIVE")),
            ("station_ok", code_if(or_(is_null(o("Compose_Stn")), not_(eq(Ex("outputs('Compose_Stn')?['Active']"), True))), "STATION_INVALID")),
            ("station_account", code_if(and_(nz(coalesce(Ex("outputs('Compose_Stn')?['ExpectedAccountUPN']"), "")),
                                             not_(eq(f("toLower", coalesce(Ex("outputs('Compose_Stn')?['ExpectedAccountUPN']"), "")), o("Compose_AppAccount")))), "STATION_ACCOUNT_MISMATCH")),
        ])
        lr = o("Login_Result")

        def fail(u: Block):
            u.set_many("Set_login_fail", {"vCode": X(lr), "vMessage": X(msg_of(Ex(str(lr))))})
            u.cond("If_log_bad_badge", eq(lr, "INVALID_BADGE"),
                   lambda w: ops_event(w, "Badge", cat("BADGEFAIL|", o("Compose_StationIn"), "|", f("formatDateTime", f("utcNow"), "yyyy-MM-dd")),
                                       "BADGE_FAILURES", "Warning", cat("Unknown badge scanned at ", o("Compose_StationIn")),
                                       cat("Unrecognised badge attempts today at station ", o("Compose_StationIn"),
                                           ". Repeated failures may mean guessing. Last typed value length: ", f("string", f("length", o("Compose_Badge"))))),
                   always=True)
        t.cond("If_login_fail", nz(lr), fail)

        def ok_(u: Block):
            u.compose("Compose_NewSessionId", X("replace(guid(), '-', '')"))
            u.attempt("Create_session", lambda s, n: s.sp_create(n, L_SESSIONS, {
                "Title": cat("Session ", Ex("outputs('Compose_Emp')?['EmployeeName']"), " @ ", o("Compose_StationIn")),
                "SessionID": X(o("Compose_NewSessionId")), "BadgeID": X(Ex("outputs('Compose_Emp')?['BadgeID']")),
                "EmployeeName": X(Ex("outputs('Compose_Emp')?['EmployeeName']")), "StationID": X(o("Compose_StationIn")),
                "AppAccountUPN": X(o("Compose_AppAccount")), "StartedUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"),
                "LastActivityUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"), "SessionState": "Active"}))
            u.cond("If_session_created", Ex(f"equals(actions('Create_session')?['status'], 'Succeeded')"),
                   lambda w: w.set_many("Set_login_ok", {"vOk": "yes", "vCode": "OK", "vMessage": X(cat("Welcome, ", Ex("outputs('Compose_Emp')?['EmployeeName']"))),
                                                         "vSessionId": X(o("Compose_NewSessionId")), "vName": X(Ex("outputs('Compose_Emp')?['EmployeeName']")),
                                                         "vRole": X(Ex("coalesce(outputs('Compose_Emp')?['Role'], 'Operator')"))}),
                   lambda w: w.set_many("Set_login_error", {"vCode": "SESSION_NOT_CREATED", "vMessage": "Could not start a session. Try again."}), always=True)
        t.cond("If_login_ok", eq(lr, ""), ok_)

    def logout(t: Block):
        t.sp_get("Get_session_out", L_SESSIONS, ["SessionID eq '", qv(coalesce(o("Compose_SessionIn"), "NONE")), "'"], select="Id,AppAccountUPN,SessionState", top=2)
        t.compose("Compose_SessOut", X("first(body('Get_session_out')?['d']?['results'])"))

        def end(u: Block):
            u.attempt("End_session", lambda s, n: s.sp_update(n, L_SESSIONS, X(Ex("outputs('Compose_SessOut')?['Id']")),
                                                              {"SessionState": "Ended", "EndedReason": "logout"}))
            u.cond("If_ended", Ex("equals(actions('End_session')?['status'], 'Succeeded')"),
                   lambda w: w.set_many("Set_logout_ok", {"vOk": "yes", "vCode": "OK", "vMessage": "Signed out."}), always=True)
        t.cond("If_can_end", Ex("and(not(equals(outputs('Compose_SessOut'), null)), equals(toLower(coalesce(outputs('Compose_SessOut')?['AppAccountUPN'], '')), outputs('Compose_AppAccount')))"), end)

    root.scope("Work", work)
    root.respond("Respond", {"ok": X(v("vOk")), "code": X(v("vCode")), "message": X(v("vMessage")), "sessionId": X(v("vSessionId")),
                             "employeeName": X(v("vName")), "role": X(v("vRole")), "idleMinutes": X(cfgi("IdleTimeoutMinutes", 3, "").__str__() and Ex("string(" + str(cfgi("IdleTimeoutMinutes", 3)) + ")"))},
                 RESP_SCHEMA, after={"Work": list(ALL)})
    return fl
