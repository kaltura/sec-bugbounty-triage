"""Mock-Jira operational-risk tests (correction 10).

Run:  python3 -m runner.tests.test_operational_risks
from ~/.claude/kaltura-triage. Records attempted calls against a mock so we can
assert that unauthorized writes are NOT attempted — something an offline run with
no write tools cannot demonstrate.

Covers: human-override preservation; ticket changed between assessment and
writeback; duplicate prevention on rerun; unrelated-label preservation;
provisional vs confirmed severity; internal vs reporter-visible comments;
partial write failure + recovery; interruption recovery without duplicate
processing (state layer).
"""
from __future__ import annotations
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from runner import writeback as W          # noqa: E402
from runner.mockjira import MockJira       # noqa: E402
from runner import state as S              # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


def issue(key, labels=None, comments=None, version=1, priority_id="15", components=None):
    return {key: {"key": key, "version": version, "fields": {
        "labels": labels or [], "priority": {"id": priority_id},
        "summary": f"{key} summary", "description": "desc",
        "components": [{"name": n} for n in (components or [])],
        "comment": {"comments": comments or []}, "attachment": []}}}


# 1) Human override preservation — no writes attempted; plan stops.
def t_human_override():
    iss = issue("K-1", labels=["hackerone", "severity-medium"], comments=[
        {"id": "1", "body": "Triaged: treating as Medium, do not escalate. — Roei",
         "author": {"displayName": "Roei Somech"}}])
    m = MockJira(iss)
    a = {"validity": "Valid", "severity": "High", "priority_id": "12",
         "comment": "x", "conflicts_with_human": True}
    plan = W.plan_writeback(a, m.get_issue("K-1"))
    res = W.apply_writeback(m, plan, dry_run=False)
    check("human-override: plan stops", plan.action == "stop_human_override")
    check("human-override: no write calls attempted", m.write_calls() == [], str(m.write_calls()))
    check("human-override: severity-medium preserved",
          m.issues["K-1"]["fields"]["labels"] == ["hackerone", "severity-medium"])


# 2) Ticket changed between assessment and writeback — version guard blocks.
def t_version_race():
    iss = issue("K-2", labels=["hackerone"], version=5)
    m = MockJira(iss)
    a = {"validity": "Valid", "severity": "High", "priority_id": "12", "comment": "c"}
    plan = W.plan_writeback(a, m.get_issue("K-2"))          # captures version 5
    # a human edits the ticket before writeback -> version bumps to 6
    m.mutate_before["K-2"] = lambda i: i.__setitem__("version", 6)
    res = W.apply_writeback(m, plan, dry_run=False)
    check("version-race: detected as conflict", res.version_conflict)
    check("version-race: no field writes performed", m.write_calls() == [], str(m.write_calls()))


# 3) Duplicate prevention on rerun — unchanged skill comment + no field change +
#    components already present (from the prior run) -> skip.
def t_duplicate():
    iss = issue("K-3", labels=["hackerone", "severity-high"],
                components=["Agent Check", "Sec-BE"])
    m = MockJira(iss)
    a = {"validity": "Valid", "severity": "High", "priority_id": None, "team_component": "Sec-BE",
         "is_skill_comment_present": True, "skill_comment_unchanged": True, "comment": "same"}
    plan = W.plan_writeback(a, m.get_issue("K-3"))
    res = W.apply_writeback(m, plan, dry_run=False)
    check("duplicate: plan skips", plan.action == "skip_unchanged", plan.action)
    check("duplicate: no writes attempted", m.write_calls() == [], str(m.write_calls()))


# 4) Unrelated label preservation + conflicting-band removal on a Valid change.
def t_labels():
    iss = issue("K-4", labels=["hackerone", "h1-report-9", "cdn", "severity-medium"])
    m = MockJira(iss)
    a = {"validity": "Valid", "severity": "High", "priority_id": None, "comment": "c"}
    plan = W.plan_writeback(a, m.get_issue("K-4"))
    W.apply_writeback(m, plan, dry_run=False)
    final = set(m.issues["K-4"]["fields"]["labels"])
    check("labels: severity-high added", "severity-high" in final)
    check("labels: conflicting severity-medium removed", "severity-medium" not in final)
    check("labels: unrelated preserved", {"hackerone", "h1-report-9", "cdn"} <= final, str(final))


# 5) Provisional vs confirmed severity — Unresolved must NOT add a severity-* label.
def t_provisional():
    iss = issue("K-5", labels=["hackerone"])
    m = MockJira(iss)
    a = {"validity": "Unresolved", "severity": "Critical", "priority_id": None,
         "comment": "provisional Critical (assumptions...)"}
    plan = W.plan_writeback(a, m.get_issue("K-5"))
    W.apply_writeback(m, plan, dry_run=False)
    labels = m.issues["K-5"]["fields"]["labels"]
    check("provisional: no severity-* label added", not any(l in W.SEV_LABELS for l in labels), str(labels))
    check("provisional: comment carries the provisional severity",
          any(c[0] == "add_comment" and "provisional" in c[3].lower() for c in m.calls))
    # Not-a-vulnerability must also not add severity-low and must preserve existing.
    iss2 = issue("K-5b", labels=["hackerone", "severity-high"])
    m2 = MockJira(iss2)
    a2 = {"validity": "Not a vulnerability", "severity": None, "priority_id": None, "comment": "intended"}
    p2 = W.plan_writeback(a2, m2.get_issue("K-5b"))
    W.apply_writeback(m2, p2, dry_run=False)
    check("not-a-vuln: no severity-low added", "severity-low" not in m2.issues["K-5b"]["fields"]["labels"])
    check("not-a-vuln: existing severity-high preserved", "severity-high" in m2.issues["K-5b"]["fields"]["labels"])


# 6) Internal vs reporter-visible comments — unestablished visibility blocks the write.
def t_visibility():
    iss = issue("K-6", labels=["hackerone"])
    m = MockJira(iss)
    a = {"validity": "Valid", "severity": "High", "priority_id": None, "comment": "internal detail"}
    plan = W.plan_writeback(a, m.get_issue("K-6"), visibility_established=False)
    res = W.apply_writeback(m, plan, dry_run=False)
    check("visibility: plan blocks", plan.action == "block_visibility")
    check("visibility: no comment attempted", not any(c[0] == "add_comment" for c in m.calls))
    # And when established, the comment is marked internal.
    m2 = MockJira(issue("K-6b", labels=["hackerone"]))
    p2 = W.plan_writeback(a, m2.get_issue("K-6b"), visibility_established=True)
    W.apply_writeback(m2, p2, dry_run=False)
    check("visibility: established -> comment internal",
          any(c[0] == "add_comment" and c[2] == "internal" for c in m2.calls))


# 7) Partial write failure — label ok, comment fails -> reported, recoverable.
def t_partial_failure():
    iss = issue("K-7", labels=["hackerone"])
    m = MockJira(iss)
    m.fail_on.add("add_comment")
    a = {"validity": "Valid", "severity": "High", "priority_id": None, "comment": "c"}
    plan = W.plan_writeback(a, m.get_issue("K-7"))
    res = W.apply_writeback(m, plan, dry_run=False)
    check("partial: label performed", any("labels" in p for p in res.performed))
    check("partial: comment error surfaced", any("comment" in e for e in res.errors), str(res.errors))
    check("partial: result not ok (so ticket stays for safe rerun)", not res.ok)


# 7b) Components — always add Agent Check + exactly one team component; preserve existing; dedupe.
def t_components():
    iss = issue("K-9", labels=["hackerone"], components=["prod"])   # unrelated existing component
    m = MockJira(iss)
    a = {"validity": "Valid", "severity": "High", "priority_id": None,
         "team_component": "Sec-BE", "comment": "c"}
    plan = W.plan_writeback(a, m.get_issue("K-9"))
    W.apply_writeback(m, plan, dry_run=False)
    comps = {c["name"] for c in m.issues["K-9"]["fields"]["components"]}
    check("components: Agent Check added", "Agent Check" in comps)
    check("components: team Sec-BE added", "Sec-BE" in comps)
    check("components: exactly one team component", len(comps & W.TEAM_COMPONENTS) == 1, str(comps))
    check("components: unrelated 'prod' preserved", "prod" in comps, str(comps))
    # Not-a-vulnerability is still a finished handling -> still gets Agent Check + team.
    m2 = MockJira(issue("K-9b", components=[]))
    a2 = {"validity": "Not a vulnerability", "severity": None, "team_component": "Sec-KMS", "comment": "intended"}
    p2 = W.plan_writeback(a2, m2.get_issue("K-9b"))
    W.apply_writeback(m2, p2, dry_run=False)
    comps2 = {c["name"] for c in m2.issues["K-9b"]["fields"]["components"]}
    check("components: not-a-vuln still tagged (Agent Check + Sec-KMS)",
          {"Agent Check", "Sec-KMS"} <= comps2, str(comps2))
    # Rerun with labels + components already present -> no duplicate write at all.
    m3 = MockJira(issue("K-9c", labels=["hackerone", "severity-high"],
                        components=["Agent Check", "Sec-BE"]))
    a3 = {"validity": "Valid", "severity": "High", "team_component": "Sec-BE",
          "is_skill_comment_present": True, "skill_comment_unchanged": True, "comment": "x", "priority_id": None}
    p3 = W.plan_writeback(a3, m3.get_issue("K-9c"))
    check("components: rerun with same components skips", p3.action == "skip_unchanged", p3.action)


# 7c) REST backend request-building (no network): component name->id mapping,
#     project guard, and correct PUT/POST bodies.
def t_rest_backend():
    from runner.jira_rest import RestJira, RestError
    cfg = {"jira": {"site": "kaltura.atlassian.net", "project": "SECF",
                    "components": {"always_add": {"name": "Agent Check", "id": "61351"},
                                   "team": {"Sec-BE": {"id": "61352"}, "Sec-KMS": {"id": "61353"}}}},
           "jira_rest": {"account_email": "x@kaltura.com"}}
    rj = RestJira(cfg)
    recorded = []
    rj._request = lambda method, path, body=None, query=None: recorded.append((method, path, body, query)) or {}
    rj.set_components("SECF-1", ["Agent Check", "Sec-BE", "prod"])
    _, path, body, _ = recorded[-1]
    comps = body["fields"]["components"]
    check("rest: components mapped to ids",
          {"id": "61351"} in comps and {"id": "61352"} in comps, str(comps))
    check("rest: unknown component falls back to name", {"name": "prod"} in comps, str(comps))
    rj.set_priority("SECF-1", "16")
    check("rest: priority body by id", recorded[-1][2] == {"fields": {"priority": {"id": "16"}}})
    rj.add_comment("SECF-1", "hello", visibility="internal")
    _, path, body, _ = recorded[-1]
    check("rest: comment posts ADF to comment endpoint",
          path.endswith("/comment") and body["body"]["type"] == "doc")
    try:
        rj.set_labels("PROJX-9", ["x"])
        check("rest: project guard blocks foreign key", False, "no error raised")
    except RestError:
        check("rest: project guard blocks foreign key", True)


# 8) Interruption recovery without duplicate processing (state layer).
def t_interruption_recovery():
    with tempfile.TemporaryDirectory() as d:
        st = S.Store(os.path.join(d, "s.db"))
        st.upsert_pending("K-8", "fp1")
        claimed = st.claim_next("w1", daily_cap=100)
        check("recovery: claimed to running", claimed and claimed["status"] == "running")
        # simulate crash mid-run: claim is stale
        st.db.execute("UPDATE tickets SET claimed_at=claimed_at-99999 WHERE key='K-8'")
        recovered = st.recover_abandoned(stale_seconds=3600)
        check("recovery: abandoned claim recovered", recovered == ["K-8"], str(recovered))
        # completing it and re-seeing the SAME fingerprint must NOT reprocess
        st.claim_next("w1", 100); st.finish("K-8", S.COMPLETED, assessment_path="cases/K-8")
        outcome = st.upsert_pending("K-8", "fp1")
        check("recovery: unchanged fingerprint not reprocessed", outcome == "unchanged", outcome)
        # a substantive update (new fingerprint) DOES re-open
        outcome2 = st.upsert_pending("K-8", "fp2")
        check("recovery: new evidence re-opens", outcome2 == "updated", outcome2)
        st.close()


def main():
    for fn in [t_human_override, t_version_race, t_duplicate, t_labels, t_provisional,
               t_visibility, t_partial_failure, t_components, t_rest_backend,
               t_interruption_recovery]:
        fn()
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{npass}/{len(RESULTS)} checks passed")
    return 0 if npass == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
