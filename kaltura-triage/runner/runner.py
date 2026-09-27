#!/usr/bin/env python3
"""Kaltura bug-bounty triage — local runner (macOS, launchd; no cloud/server).

Architecture (this machine): DETECTOR + MANUAL. Endpoint-security tooling
(AgenShield) holds a bare `claude` exec, so unattended headless `claude -p` cannot
run. The scheduler therefore only DETECTS new-to-scope tickets and queues them; a
human investigates each in the Claude desktop app with the skill, then applies the
reviewed result back to Jira over REST via `writeback`.

Subcommands:
  doctor       Preflight: environment, Jira REST, headless-claude probe, gh, config,
               launchd. READY/BLOCKED. (Headless probe is expected to fail here.)
  activate     Record the activation baseline (now + current epic membership) so
               "new-to-scope" has a fixed meaning. Does not start the schedule.
  poll         DETECTOR: one cycle — recover, detect eligible new-to-scope tickets,
               enqueue them for manual triage, print the to-do list. Never runs claude.
  run-ticket K Stage one ticket (fetch to cases/<KEY>/input.json) and print the manual
               desktop-app steps. --headless runs the in-process investigator where
               a bare `claude` exec is permitted (non-AgenShield / allowlisted).
  writeback K  Apply a reviewed assessment (cases/<KEY>/assessment.json) to Jira over
               REST with the full safety plan. Dry-run by default; --apply to perform.
  done K       Mark a queued ticket completed without a runner writeback (handled in-app).
  status       Print mode flags + queue counts.
  queue        Print every tracked ticket and its state (+ the pending to-do list).
  fail-summary Print failed / needs-input tickets and why.
  set-mode K V Toggle a mode: scheduler_enabled|reproduction_enabled|writeback_enabled true|false.
  start|stop   launchctl load/unload the user agent (only after doctor is READY).

Modes default to read-only. Nothing here changes system sleep settings; launchd
runs the detector only while you are logged in and awake, and runs a missed interval
once on wake — the watermark + baseline provide downtime catch-up on top of that.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time, datetime
from pathlib import Path

ROOT = Path(os.environ.get("KTRI_ROOT", Path.home() / ".claude" / "kaltura-triage"))
sys.path.insert(0, str(ROOT))
from runner import state as S            # noqa: E402
from runner import jira as J             # noqa: E402
from runner import credentials as CRED   # noqa: E402

LABEL = "com.kaltura.bugbounty-triage"
PLIST = ROOT / "launchd" / f"{LABEL}.plist"


def load_cfg():
    cfg = json.loads((ROOT / "config.json").read_text())
    # Portability: if the configured claude binary doesn't exist on THIS machine,
    # fall back to whatever `claude` is on PATH so the runner works after a handoff.
    cbin = cfg.get("investigator", {}).get("claude_bin")
    if not cbin or not Path(cbin).exists():
        found = shutil.which("claude")
        if found:
            cfg["investigator"]["claude_bin"] = found
    return cfg


def save_cfg(cfg):
    (ROOT / "config.json").write_text(json.dumps(cfg, indent=2))


def store(cfg):
    return S.Store(str(ROOT / cfg["paths"]["state_db"]))


def claude_env(cfg):
    """os.environ plus CLAUDE_CODE_OAUTH_TOKEN from the Keychain, so headless
    `claude -p` is authenticated without the token ever touching config/plist/logs."""
    env = dict(os.environ)
    email = cfg.get("jira_rest", {}).get("account_email")
    tok = CRED.get_token(email, CRED.SERVICE_CLAUDE)
    if tok:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    return env


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat() if ts else "-"


# ---------------- doctor ----------------
def cmd_doctor(cfg, args):
    ok = True
    def line(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"  [{'ok ' if good else 'XX '}] {msg}")

    print("Kaltura triage — doctor")
    cbin = cfg["investigator"]["claude_bin"]
    line(Path(cbin).exists(), f"claude CLI present: {cbin}")
    # Jira access = direct REST backend + token in Keychain (no MCP connector needed).
    backend = cfg["investigator"].get("backend")
    email = cfg.get("jira_rest", {}).get("account_email")
    jira_ok = False
    if backend == "rest":
        tok = CRED.token_present(email)
        line(tok, f"Jira API token in Keychain for {email} "
                  + ("" if tok else "(MISSING — run `runner.py set-token`)"))
        if tok:
            try:
                probe = J.make_client(cfg).search(f"project = {cfg['jira']['project']}", fields=["key"])
                jira_ok = True
                line(True, f"Jira REST reachable (probe returned {len(probe)} issue(s))")
            except Exception as e:  # noqa: BLE001
                line(False, f"Jira REST probe failed: {str(e)[:160]}")
    else:
        line(False, f"backend={backend!r} (expected 'rest' for the token path)")
    # Optional: headless `claude -p` for the --headless investigator path. This is
    # NOT required for detector+manual operation, so it is INFORMATIONAL only and does
    # not affect READY. On this machine it is expected to be blocked by AgenShield.
    cli_login = False
    def note(good, msg):  # prints a status marker WITHOUT gating `ok`
        print(f"  [{'ok ' if good else '-- '}] {msg}")
    try:
        pr = subprocess.run([cbin, "-p", "reply with: OK", "--output-format", "json"],
                            capture_output=True, text=True, timeout=40, env=claude_env(cfg),
                            stdin=subprocess.DEVNULL)
        cli_login = ('"is_error":false' in pr.stdout.replace(" ", "")) or ("OK" in pr.stdout and "Not logged in" not in pr.stdout)
        note(cli_login, "headless `claude -p` ran in THIS context "
                        + ("(works only when launched from a sanctioned desktop-app session; "
                           "launchd/plain-terminal exec is still held by AgenShield, so automation "
                           "stays detector-only)" if cli_login
                           else "(not logged in — optional; run `claude setup-token`)"))
    except subprocess.TimeoutExpired:
        note(False, "headless `claude -p` blocked at exec by endpoint-security/AgenShield "
                    "(expected here). Not needed for detector+manual: investigate in the desktop app.")
    except Exception as e:  # noqa: BLE001
        note(False, f"headless `claude -p` probe failed: {str(e)[:100]} (optional; not needed for detector+manual)")
    # gh
    try:
        gh = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=30)
        line(gh.returncode == 0, "gh authenticated")
    except Exception as e:  # noqa: BLE001
        line(False, f"gh not available: {e}")
    line(shutil.which("python3") is not None, "python3 present")
    line((ROOT / "config.json").exists(), "config.json present")
    line((ROOT / "product-notes" / "INDEX.md").exists(), "product-notes present")
    comps = cfg["jira"].get("components", {})
    team = comps.get("team", {})
    line(comps.get("always_add", {}).get("id") == "61351" and len(team) == 5,
         f"components configured: Agent Check + {list(team)} "
         + ("" if len(team) == 5 else "(MISSING team components)"))
    base = cfg["activation"]["baseline_recorded_at"]
    line(True, f"activation baseline: {base or 'NOT SET (run `activate`)'}")
    m = cfg["modes"]
    print(f"  modes: scheduler={m['scheduler_enabled']} reproduction={m['reproduction_enabled']} "
          f"writeback={m['writeback_enabled']} scheduler_writeback={m.get('scheduler_writeback')}")
    line(PLIST.exists(), f"launchd plist staged: {PLIST}")
    ready = ok and jira_ok
    print("\nRESULT:", "READY (detector + manual)" if ready else
          "BLOCKED — resolve the [XX] items above (manual/desktop triage still works)")
    if ready and not cli_login:
        print("  note: headless investigator unavailable (AgenShield) — this is expected; the "
              "detector queues tickets and you investigate them in the desktop app.")
    return 0


def cmd_set_token(cfg, args):
    email = cfg.get("jira_rest", {}).get("account_email")
    if not email:
        print("Set jira_rest.account_email in config.json first."); return 1
    print(f"Storing Jira API token for {email} in the macOS Keychain "
          f"(service '{CRED.SERVICE}').")
    print("Create a token at https://id.atlassian.com/manage-profile/security/api-tokens")
    rc = CRED.set_token_interactive(email, from_stdin=getattr(args, "stdin", False))
    print("stored and verified (round-trips from Keychain)." if rc == 0
          else "NOT stored — try again.")
    return rc


def cmd_set_claude_token(cfg, args):
    email = cfg.get("jira_rest", {}).get("account_email")
    if not args.stdin:
        print("Recommended (paste-proof): copy the token from `claude setup-token`, then run:")
        print("  pbpaste | python3 -m runner.runner set-claude-token --stdin")
    rc = CRED.set_token_interactive(email, CRED.SERVICE_CLAUDE, "Claude OAuth token",
                                    from_stdin=args.stdin)
    if rc != 0:
        print("NOT stored — try again.")
        return rc
    tok = CRED.get_token(email, CRED.SERVICE_CLAUDE) or ""
    if not (tok.startswith("sk-ant-oat") and len(tok) > 60):
        print(f"stored value looks wrong (len={len(tok)}, prefix={tok[:12]!r}); expected an "
              "'sk-ant-oat…' token. Re-copy the FULL token and use the --stdin method.")
        return 1
    print("verifying headless auth (up to ~40s)…")
    try:
        pr = subprocess.run([cfg["investigator"]["claude_bin"], "-p", "reply with: OK",
                             "--output-format", "json"], capture_output=True, text=True,
                            timeout=40, env=claude_env(cfg), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        print("stored, but the headless verify probe TIMED OUT. On this machine a bare `claude`\n"
              "  process is held at exec by endpoint-security tooling (AgenShield), so unattended\n"
              "  `claude -p` cannot start — this is below the auth layer, not a token problem.\n"
              "  The token is saved for if/when that exec path is allowlisted. Manual triage in\n"
              "  the desktop app is unaffected. Run `doctor` for the full picture.")
        return 1
    good = "Not logged in" not in pr.stdout and "Invalid" not in pr.stdout and "OK" in pr.stdout
    print("stored and verified — headless claude is authenticated." if good
          else "stored, but headless auth check did NOT pass; the token may be wrong/expired.")
    return 0 if good else 1


# ---------------- activate (baseline only) ----------------
def cmd_activate(cfg, args):
    st = store(cfg)
    client = J.make_client(cfg)
    try:
        members = client.search(cfg["jira"]["epic_child_jql"], fields=["key"])
        keys = sorted({m["key"] for m in members})
    except Exception as e:  # noqa: BLE001
        print(f"Could not read epic membership (connector needed): {e}")
        print("Baseline NOT recorded. Run `doctor`, add the connector, then `activate`.")
        return 1
    t = S.now()
    st.kv_set("activation_baseline_ts", t)
    st.kv_set("activation_membership", keys)
    st.kv_set("watermark_ts", t)
    cfg["activation"]["baseline_recorded_at"] = iso(t)
    save_cfg(cfg)
    print(f"Activation baseline recorded at {iso(t)}.")
    print(f"Current epic membership snapshot: {len(keys)} tickets (these are treated as "
          "pre-existing; only tickets that become new-to-scope AFTER now are eligible).")
    st.close()
    return 0


# ---------------- eligibility ----------------
def eligible_candidates(cfg, st, client):
    """Return keys that are new-to-scope AND in an eligible status, per the
    activation policy. Never relies on 'created in last N minutes' alone."""
    baseline_ts = st.kv_get("activation_baseline_ts")
    baseline_members = set(st.kv_get("activation_membership", []))
    include_existing = cfg["activation"]["include_existing_backlog"]
    statuses = cfg["jira"]["eligible_statuses"]
    status_clause = " OR ".join(f'status = "{s}"' for s in statuses)
    jql = f'{cfg["jira"]["epic_child_jql"]} AND ({status_clause})'
    rows = client.search(jql, fields=["key", "status", "updated", "created"])
    out = []
    for r in rows:
        key = r["key"]
        if include_existing:
            out.append(r)
            continue
        # new-to-scope only: not in the baseline membership snapshot
        if key not in baseline_members:
            out.append(r)
    return out


# ---------------- poll (one cycle) — DETECTOR ONLY ----------------
def cmd_poll(cfg, args):
    """One detection cycle: find new-to-scope eligible tickets and enqueue them for
    MANUAL investigation. This path NEVER spawns `claude -p`. On this machine a bare
    `claude` exec is held at the process layer by endpoint-security (AgenShield), so
    unattended headless investigation is impossible; the scheduler's job is therefore
    detection + durable queueing, and a human investigates each queued ticket in the
    Claude desktop app with the skill (`run-ticket K` stages one; `writeback K`
    applies the reviewed result over REST)."""
    if not cfg["modes"]["scheduler_enabled"] and not args.force:
        print("scheduler_enabled=false; not polling. Use --force for a manual cycle, "
              "or `set-mode scheduler_enabled true` to enable.")
        return 0
    st = store(cfg)
    recovered = st.recover_abandoned(cfg["limits"]["claim_stale_seconds"])
    if recovered:
        print(f"recovered abandoned claims: {recovered}")
    try:
        client = J.make_client(cfg)
        cands = eligible_candidates(cfg, st, client)
    except Exception as e:  # noqa: BLE001
        print(f"poll blocked (Jira read failed): {e}")
        st.close(); return 1
    newly = []
    for r in cands:
        try:
            full = client.get_issue(r["key"])
            fp = S.report_fingerprint(full)
            outcome = st.upsert_pending(r["key"], fp)
            if outcome != "unchanged":
                print(f"enqueued {r['key']} ({outcome})")
                newly.append(r["key"])
        except Exception as e:  # noqa: BLE001
            print(f"skip {r['key']}: {e}")
    st.kv_set("watermark_ts", S.now())
    pending = st.list_by_status(S.PENDING)
    print(f"detector cycle done: {len(newly)} new/updated this cycle, "
          f"{len(pending)} awaiting manual triage.")
    if pending:
        print("to triage — open the desktop app and run the skill on each:")
        for r in pending:
            print(f"  {r['key']}")
    st.close()
    return 0


def _investigate(cfg, st, key, source="manual", force_readonly=False):
    """Assess one ticket. The RUNNER fetches the ticket over REST (so the headless
    investigator needs no Jira connector — it uses gh + web for code/docs), then
    the investigator writes assessment.md + assessment.json. Writeback (only if
    enabled) is applied by the runner via REST, after the safety plan.

    Writeback gating: a MANUAL run (source='manual') may write when writeback_enabled.
    A SCHEDULED run (source='scheduler') writes only when BOTH writeback_enabled and
    scheduler_writeback are true — so automation stays assessment-only by default."""
    from runner import writeback as WB
    case_dir = ROOT / cfg["paths"]["cases_dir"] / key
    case_dir.mkdir(parents=True, exist_ok=True)
    out = case_dir / "assessment.md"
    ajson = case_dir / "assessment.json"

    # 1) Fetch the ticket over REST and stage it for the investigator.
    try:
        client = J.make_client(cfg)
        issue = client.get_issue(key)
    except Exception as e:  # noqa: BLE001
        st.needs_input(key, f"could not fetch ticket over REST: {str(e)[:200]}")
        return
    (case_dir / "input.json").write_text(json.dumps(issue, indent=2, default=str))

    # 2) Investigate headlessly (read-only; no Jira tools needed — data is on disk).
    disallow = cfg["investigator"]["disallowed_write_tools"]
    prompt = (
        f"Invoke the '{cfg['investigator']['skill_name']}' skill to triage Kaltura security "
        f"ticket {key}. The full ticket JSON is at {case_dir/'input.json'} (use it as the report; "
        "do NOT call Jira). Use gh and the web for GitHub code tracing and product docs. Assess "
        "validity, severity, confidence, remediation priority, investigation urgency, and choose "
        "components (Agent Check + one team component). Make NO production requests and NO Jira "
        f"writes. Write the human assessment to {out}, and a machine-readable summary to {ajson} "
        'with keys: validity, severity, confidence, reproduction, priority_id, team_component, '
        'comment, visibility_established (bool), conflicts_with_human (bool). If interactive access '
        "or a human decision is needed, write NEEDS-INPUT into the assessment and say why.")
    cmd = [cfg["investigator"]["claude_bin"], "-p", prompt,
           "--permission-mode", cfg["investigator"]["permission_mode"],
           "--add-dir", str(ROOT), "--output-format", "json"]
    if cfg["investigator"].get("model"):
        cmd += ["--model", cfg["investigator"]["model"]]
    for t in cfg["investigator"].get("allowed_tools", []):
        cmd += ["--allowed-tools", t]
    for t in disallow:
        cmd += ["--disallowed-tools", t]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=cfg["limits"]["per_run_timeout_seconds"], env=claude_env(cfg))
    except subprocess.TimeoutExpired:
        st.finish(key, S.FAILED, error="timeout",
                  backoff=tuple(cfg["limits"]["retry_backoff_seconds"]),
                  max_attempts=cfg["limits"]["max_attempts_per_ticket"])
        return
    tokens = 0
    try:
        tokens = json.loads(p.stdout).get("usage", {}).get("total_tokens", 0)
    except Exception:  # noqa: BLE001
        pass
    if p.returncode != 0:
        st.finish(key, S.FAILED, error=f"investigator rc={p.returncode}: {p.stderr[:300]}",
                  backoff=tuple(cfg["limits"]["retry_backoff_seconds"]),
                  max_attempts=cfg["limits"]["max_attempts_per_ticket"])
        return
    if out.exists() and "NEEDS-INPUT" in out.read_text():
        st.needs_input(key, "investigator reported NEEDS-INPUT")
        return

    # 3) Writeback only if enabled for THIS source; otherwise record the dry-run.
    may_write = (not force_readonly) and cfg["modes"]["writeback_enabled"] and (
        source == "manual" or cfg["modes"].get("scheduler_writeback", False))
    outcome = "dry-run (read-only)"
    if may_write and ajson.exists():
        try:
            a = json.loads(ajson.read_text())
            fresh = client.get_issue(key)                       # recheck eligibility + concurrency
            if fresh.get("fields", {}).get("status", {}).get("name") not in cfg["jira"]["eligible_statuses"]:
                st.needs_input(key, "no longer in an eligible status at writeback time")
                return
            plan = WB.plan_writeback(a, fresh,
                                     visibility_established=a.get("visibility_established", True))
            res = WB.apply_writeback(client, plan, dry_run=False)
            outcome = ("written: " + "; ".join(res.performed)) if res.ok else \
                      ("write incomplete: " + "; ".join(res.errors))
            if not res.ok:
                st.finish(key, S.FAILED, assessment_path=str(out), writeback_outcome=outcome,
                          error=outcome, backoff=tuple(cfg["limits"]["retry_backoff_seconds"]),
                          max_attempts=cfg["limits"]["max_attempts_per_ticket"])
                return
        except Exception as e:  # noqa: BLE001
            st.finish(key, S.FAILED, error=f"writeback error: {str(e)[:200]}",
                      backoff=tuple(cfg["limits"]["retry_backoff_seconds"]),
                      max_attempts=cfg["limits"]["max_attempts_per_ticket"])
            return
    st.finish(key, S.COMPLETED, assessment_path=str(out), writeback_outcome=outcome, tokens=tokens)


def cmd_run_ticket(cfg, args):
    """Manual per-ticket entry point.

    Default (this machine): STAGE the ticket for manual investigation in the Claude
    desktop app — fetch it over REST to cases/<KEY>/input.json and print the exact
    steps. Headless `claude -p` is blocked here by AgenShield, so investigation runs
    in the sanctioned desktop app, not a subprocess.

    --headless: run the in-process investigator (`_investigate`) instead. Only works
    where a bare `claude` exec is permitted (a non-AgenShield machine, or once the
    exec path is allowlisted). Kept for portability."""
    st = store(cfg)
    if args.headless:
        st.upsert_pending(args.key, "manual")
        st.db.execute("UPDATE tickets SET status='running',run_id=?,attempts=attempts+1 WHERE key=?",
                      (f"manual-{S.now()}", args.key))
        st.db.execute("INSERT OR IGNORE INTO runs(run_id,ticket,started_at,status) VALUES(?,?,?,?)",
                      (f"manual-{S.now()}", args.key, S.now(), "running"))
        wb = cfg["modes"]["writeback_enabled"] and not args.dry_run
        print(f"investigating {args.key} ({'writeback ENABLED' if wb else 'read-only (dry-run)'}, headless)…")
        _investigate(cfg, st, args.key, source="manual", force_readonly=args.dry_run)
        row = st.db.execute("SELECT status,assessment_path,last_error FROM tickets WHERE key=?",
                            (args.key,)).fetchone()
        print(f"  -> {row['status']}  {row['assessment_path'] or row['last_error'] or ''}")
        st.close(); return 0

    # Default: stage for manual desktop-app investigation.
    try:
        client = J.make_client(cfg)
        issue = client.get_issue(args.key)
    except Exception as e:  # noqa: BLE001
        print(f"could not fetch {args.key} over REST: {e}"); st.close(); return 1
    case_dir = ROOT / cfg["paths"]["cases_dir"] / args.key
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(json.dumps(issue, indent=2, default=str))
    st.upsert_pending(args.key, S.report_fingerprint(issue))
    st.close()
    print(f"staged {args.key} -> {case_dir / 'input.json'}")
    print("\nInvestigate it manually (headless claude is blocked by AgenShield on this machine):")
    print(f"  1) Open the Claude desktop app with this folder: {ROOT}")
    print(f"  2) Prompt: \"Use the kaltura-bug-bounty-triage skill to triage {args.key}. "
          f"The ticket JSON is at cases/{args.key}/input.json. Write the human assessment to "
          f"cases/{args.key}/assessment.md and a machine-readable summary to "
          f"cases/{args.key}/assessment.json with these keys:")
    print("       validity: \"Valid\" | \"Not a vulnerability\" | \"Unresolved\"")
    print("       severity: \"Critical\" | \"High\" | \"Medium\" | \"Low\" | null")
    print("       priority: \"1-Essential\" | \"2-High\" | \"3-Medium\" | \"4-Low\" | \"5 - Not prioritized\" | null")
    print("       team_component: \"Sec-KMS\" | \"Sec-EP\" | \"Sec-BE\" | \"Devops OVP-Sec\" | \"Devops OTT-Sec\"")
    print("       comment: string (begin it with 'Security triage assessment:' so re-runs don't double-post)")
    print("       visibility_established: bool   conflicts_with_human: bool\"")
    print("  3) Review the assessment, then apply the writeback over REST:")
    print(f"       python3 -m runner.runner writeback {args.key}           # dry-run diff")
    print(f"       python3 -m runner.runner writeback {args.key} --apply   # perform it")
    print(f"     (or, if you updated Jira yourself in the app: python3 -m runner.runner done {args.key})")
    return 0


def cmd_status(cfg, args):
    st = store(cfg); m = cfg["modes"]
    print("mode: DETECTOR + MANUAL (scheduler detects & queues; investigation is manual "
          "in the desktop app; writeback is manual over REST)")
    print(f"modes: scheduler={m['scheduler_enabled']} reproduction={m['reproduction_enabled']} "
          f"writeback={m['writeback_enabled']} scheduler_writeback={m.get('scheduler_writeback')} "
          "(scheduler_writeback is inert — automation never investigates or writes here)")
    print(f"epic {cfg['jira']['intake_epic']} statuses {cfg['jira']['eligible_statuses']} "
          f"baseline {cfg['activation']['baseline_recorded_at']}")
    print("queue:", st.counts() or "(empty)")
    st.close(); return 0


def cmd_queue(cfg, args):
    st = store(cfg)
    rows = st.all_tickets()
    for r in rows:
        print(f"  {r['key']:12s} {r['status']:11s} att={r['attempts']} "
              f"upd={iso(r['updated_at'])} {r['assessment_path'] or r['writeback_outcome'] or r['last_error'] or ''}")
    pending = [r["key"] for r in rows if r["status"] == S.PENDING]
    if pending:
        print(f"\n{len(pending)} awaiting manual triage: {', '.join(pending)}")
        print("  stage one:  python3 -m runner.runner run-ticket <KEY>")
    st.close(); return 0


def cmd_fail_summary(cfg, args):
    st = store(cfg)
    for status in (S.FAILED, S.NEEDS_INPUT):
        rows = st.list_by_status(status)
        print(f"{status}: {len(rows)}")
        for r in rows:
            print(f"  {r['key']}: {r['last_error']}")
    st.close(); return 0


def cmd_writeback(cfg, args):
    """Apply the reviewed assessment for one ticket to Jira over REST, with the full
    safety plan (human-override guard, provisional-vs-confirmed severity, unrelated
    label/component preservation, comment de-dup, comment-visibility gate, optimistic
    concurrency). Default is a DRY-RUN diff; pass --apply to perform it.

    This is the MANUAL writeback path used after you investigate a ticket in the
    desktop app. Automation never writes — the scheduler only detects and queues."""
    from runner import writeback as WB
    if not cfg["modes"]["writeback_enabled"]:
        print("writeback_enabled=false; run `set-mode writeback_enabled true` first.")
        return 1
    case_dir = ROOT / cfg["paths"]["cases_dir"] / args.key
    src = Path(args.from_file) if args.from_file else (case_dir / "assessment.json")
    if not src.exists():
        print(f"no assessment file at {src}.")
        print(f"Produce one by running the skill on {args.key} in the desktop app (have it write "
              f"cases/{args.key}/assessment.json), or pass --from PATH.")
        return 1
    try:
        a = json.loads(src.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"could not parse {src}: {e}"); return 1

    # Normalize priority: accept an explicit priority_id, or a band name mapped via config.
    if not a.get("priority_id") and a.get("priority"):
        a["priority_id"] = cfg["jira"]["priority_ids"].get(a["priority"])

    st = store(cfg)
    try:
        client = J.make_client(cfg)
        fresh = client.get_issue(args.key)
    except Exception as e:  # noqa: BLE001
        print(f"could not fetch {args.key} over REST: {e}"); st.close(); return 1

    # Eligibility recheck — same guard the automation uses: only write in an eligible status.
    status_name = (fresh.get("fields", {}).get("status") or {}).get("name")
    if status_name not in cfg["jira"]["eligible_statuses"] and not args.force_status:
        print(f"{args.key} is in status {status_name!r}, not in eligible "
              f"{cfg['jira']['eligible_statuses']}. Refusing to write (eligibility guard).")
        print("Pass --force-status to override intentionally.")
        st.close(); return 1

    # Idempotency: read skill-comment presence from the LIVE ticket so re-runs don't
    # double-post. skill_comment_unchanged=True => the comment is skipped this run.
    comments = ((fresh.get("fields", {}).get("comment") or {}).get("comments")) or []
    present = any("Security triage assessment" in str(c.get("body", "")) for c in comments)
    a.setdefault("is_skill_comment_present", present)
    a.setdefault("skill_comment_unchanged", present and not args.force_comment)

    plan = WB.plan_writeback(a, fresh, visibility_established=a.get("visibility_established", True))
    print(f"{args.key}: plan action = {plan.action}" + (f" ({plan.reason})" if plan.reason else ""))
    if plan.action != "write":
        # stop_human_override / block_visibility / skip_unchanged — explain, write nothing.
        for s in WB.apply_writeback(client, plan, dry_run=True).skipped:
            print("  -", s)
        st.close(); return 0
    print("  " + plan.label_diff())
    print("  " + plan.component_diff())
    if plan.set_priority_id:
        print(f"  priority -> id {plan.set_priority_id}")
    if plan.comment_body:
        print(f"  comment ({plan.comment_visibility}, {len(plan.comment_body)} chars)")

    if not args.apply:
        print("\nDRY-RUN — nothing written. Re-run with --apply to perform this.")
        st.close(); return 0

    res = WB.apply_writeback(client, plan, dry_run=False)
    if res.ok:
        outcome = "written: " + "; ".join(res.performed)
        amd = case_dir / "assessment.md"
        st.finish(args.key, S.COMPLETED,
                  assessment_path=str(amd) if amd.exists() else None, writeback_outcome=outcome)
        print("APPLIED:", outcome)
        st.close(); return 0
    outcome = ("version conflict" if res.version_conflict else "incomplete") + ": " + "; ".join(res.errors)
    st.needs_input(args.key, outcome)
    print("NOT fully applied:", outcome)
    print("(state set to needs_input; re-fetch, re-plan, then retry.)")
    st.close(); return 1


def cmd_done(cfg, args):
    """Mark a queued ticket COMPLETED without a runner writeback — e.g. you updated
    Jira yourself in the desktop app, or decided no change is needed. Clears it from
    the pending to-do list."""
    st = store(cfg)
    st.finish(args.key, S.COMPLETED,
              writeback_outcome=args.note or "resolved manually (no runner writeback)")
    st.close()
    print(f"{args.key} marked completed: {args.note or 'resolved manually'}")
    return 0


def cmd_set_mode(cfg, args):
    if args.key not in cfg["modes"]:
        print(f"unknown mode {args.key}; one of {list(cfg['modes'])}"); return 1
    cfg["modes"][args.key] = (args.value.lower() == "true")
    save_cfg(cfg)
    print(f"{args.key} = {cfg['modes'][args.key]}")
    if args.key == "writeback_enabled" and cfg["modes"][args.key]:
        print("NOTE: writeback also requires the connector (doctor) and per-run eligibility recheck.")
    return 0


def cmd_start(cfg, args):
    if not PLIST.exists():
        print(f"plist missing: {PLIST}"); return 1
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    print("loaded" if r.returncode == 0 else f"load failed: {r.stderr}")
    return r.returncode


def cmd_stop(cfg, args):
    r = subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True, text=True)
    print("unloaded" if r.returncode == 0 else f"unload failed: {r.stderr}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(prog="runner.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor"); sub.add_parser("activate")
    pp = sub.add_parser("poll"); pp.add_argument("--force", action="store_true")
    rt = sub.add_parser("run-ticket"); rt.add_argument("key")
    rt.add_argument("--dry-run", action="store_true", help="force read-only even if writeback is enabled (headless only)")
    rt.add_argument("--headless", action="store_true",
                    help="run the in-process `claude -p` investigator (only where AgenShield permits it); "
                         "default stages the ticket for manual desktop-app investigation")
    wb = sub.add_parser("writeback"); wb.add_argument("key")
    wb.add_argument("--from", dest="from_file", help="assessment JSON path (default cases/<KEY>/assessment.json)")
    wb.add_argument("--apply", action="store_true", help="perform the writeback (default is a dry-run diff)")
    wb.add_argument("--force-comment", action="store_true", help="post the comment even if a skill comment already exists")
    wb.add_argument("--force-status", action="store_true", help="write even if the ticket left an eligible status")
    dn = sub.add_parser("done"); dn.add_argument("key"); dn.add_argument("--note", default="")
    sub.add_parser("status"); sub.add_parser("queue"); sub.add_parser("fail-summary")
    sm = sub.add_parser("set-mode"); sm.add_argument("key"); sm.add_argument("value")
    stk = sub.add_parser("set-token"); stk.add_argument("--stdin", action="store_true")
    sct = sub.add_parser("set-claude-token"); sct.add_argument("--stdin", action="store_true")
    sub.add_parser("start"); sub.add_parser("stop")
    args = ap.parse_args()
    cfg = load_cfg()
    fn = {"doctor": cmd_doctor, "activate": cmd_activate, "poll": cmd_poll,
          "run-ticket": cmd_run_ticket, "writeback": cmd_writeback, "done": cmd_done,
          "status": cmd_status, "queue": cmd_queue,
          "fail-summary": cmd_fail_summary, "set-mode": cmd_set_mode,
          "set-token": cmd_set_token, "set-claude-token": cmd_set_claude_token,
          "start": cmd_start, "stop": cmd_stop}[args.cmd]
    return fn(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
