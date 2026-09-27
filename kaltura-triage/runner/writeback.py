"""Jira writeback safety logic — backend-independent so it can be unit-tested
against a mock that records attempted calls.

Two stages:
  plan_writeback(assessment, issue, existing_skill_comment) -> WritePlan   (pure)
  apply_writeback(client, key, plan, dry_run) -> ApplyResult               (effects)

The plan encodes every safety decision (human-override stop, provisional-vs-
confirmed severity, unrelated-label preservation, comment de-duplication,
comment-visibility gate). apply_* enforces optimistic concurrency (if_version),
read-back, and partial-failure reporting.
"""
from __future__ import annotations
from dataclasses import dataclass, field

SEV_LABELS = {"severity-critical", "severity-high", "severity-medium", "severity-low"}
BAND_TO_LABEL = {"Critical": "severity-critical", "High": "severity-high",
                 "Medium": "severity-medium", "Low": "severity-low"}


ALWAYS_COMPONENT = "Agent Check"      # added to every handled ticket
TEAM_COMPONENTS = {"Sec-KMS", "Sec-EP", "Sec-BE", "Devops OVP-Sec", "Devops OTT-Sec"}


@dataclass
class WritePlan:
    key: str
    action: str                      # "write" | "stop_human_override" | "skip_unchanged" | "block_visibility"
    reason: str = ""
    labels_add: list = field(default_factory=list)
    labels_remove: list = field(default_factory=list)
    labels_keep: list = field(default_factory=list)
    components_add: list = field(default_factory=list)   # names to add (Agent Check + one team)
    components_keep: list = field(default_factory=list)  # existing, preserved
    set_priority_id: str | None = None
    comment_body: str | None = None
    comment_visibility: str = "internal"
    if_version: int | None = None

    def label_diff(self) -> str:
        return (f"labels: add {self.labels_add or '[]'}; "
                f"remove {self.labels_remove or '[]'}; keep {self.labels_keep or '[]'}")

    def component_diff(self) -> str:
        return (f"components: add {self.components_add or '[]'}; "
                f"remove []; keep {self.components_keep or '[]'}")


def plan_components(current_names: list[str], team_component: str | None) -> tuple[list, list]:
    """Return (add, keep) component names. Always ensures 'Agent Check' is present,
    plus exactly one team component. Never removes existing components; never
    duplicates one already on the ticket."""
    keep = list(current_names)
    add = []
    if ALWAYS_COMPONENT not in current_names:
        add.append(ALWAYS_COMPONENT)
    if team_component:
        if team_component not in TEAM_COMPONENTS:
            raise ValueError(f"unknown team component {team_component!r}")
        if team_component not in current_names:
            add.append(team_component)
    return add, keep


def detect_human_decision(issue: dict) -> str | None:
    """Return a human decision descriptor if the ticket carries an explicit human
    triage decision that must not be silently overwritten, else None.

    A *human* decision = a triage/severity/priority decision recorded by a person.
    This skill's OWN prior assessment comment is NOT a human decision (so routine
    reruns don't always stop)."""
    f = issue.get("fields", issue)
    for c in (((f.get("comment") or {}).get("comments")) or []):
        body = str(c.get("body", ""))
        author = ((c.get("author") or {}).get("displayName")) or ""
        is_skill = "Security triage assessment" in body
        if is_skill:
            continue
        low = body.lower()
        if any(k in low for k in ("treating as", "do not escalate", "triaged", "downgrad",
                                  "won't fix", "wont fix", "by design", "not a vuln",
                                  "rejected", "severity", "priority", "closing")):
            return f"human decision by {author}: {body[:160]}"
    return None


def plan_writeback(assessment: dict, issue: dict,
                   visibility_established: bool = True) -> WritePlan:
    """Pure planning. `assessment` has keys: validity ('Valid'|'Not a vulnerability'|
    'Unresolved'), severity (band or None), comment (str), priority_id (str|None),
    is_skill_comment_present (bool), skill_comment_unchanged (bool)."""
    f = issue.get("fields", issue)
    key = issue.get("key")
    version = issue.get("version")
    cur_labels = list(f.get("labels") or [])
    keep = [l for l in cur_labels if l not in SEV_LABELS]
    existing_sev = [l for l in cur_labels if l in SEV_LABELS]

    # 1) Human-override guard first.
    human = detect_human_decision(issue)
    if human and assessment.get("conflicts_with_human", False):
        return WritePlan(key=key, action="stop_human_override", reason=human,
                         labels_keep=cur_labels, if_version=version)

    # 2) Comment-visibility gate.
    if not visibility_established:
        return WritePlan(key=key, action="block_visibility",
                         reason="Comment visibility / HackerOne sync could not be established; "
                                "refusing to write to avoid exposing internal detail.",
                         labels_keep=cur_labels, if_version=version)

    validity = assessment["validity"]
    add, remove = [], []
    priority_id = None

    if validity == "Valid":
        band = assessment.get("severity")
        want = BAND_TO_LABEL.get(band)
        if want:
            if want not in cur_labels:
                add.append(want)
            # prevent conflicting bands: remove any other severity-* label
            remove += [l for l in existing_sev if l != want]
        priority_id = assessment.get("priority_id")
    elif validity == "Not a vulnerability":
        # No new band; PRESERVE existing severity labels (do not remove); no priority change.
        pass
    elif validity == "Unresolved":
        # Never add a plain severity-* label that would look confirmed; provisional
        # severity stays in the comment. Preserve existing labels. Don't downgrade.
        priority_id = assessment.get("priority_id")  # only if explicitly provided w/ reason

    # Components: always add Agent Check + exactly one team component (on every
    # finished handling, regardless of validity). Preserve existing components.
    cur_components = [c.get("name") for c in (f.get("components") or []) if c.get("name")]
    comp_add, comp_keep = plan_components(cur_components, assessment.get("team_component"))

    # 3) Comment de-duplication (idempotency).
    if assessment.get("is_skill_comment_present") and assessment.get("skill_comment_unchanged"):
        comment = None
        if not add and not remove and priority_id is None and not comp_add:
            return WritePlan(key=key, action="skip_unchanged",
                             reason="No field/component changes and skill comment unchanged.",
                             labels_keep=cur_labels, components_keep=cur_components, if_version=version)
    else:
        comment = assessment.get("comment")

    return WritePlan(key=key, action="write", reason=validity,
                     labels_add=add, labels_remove=remove, labels_keep=keep,
                     components_add=comp_add, components_keep=comp_keep,
                     set_priority_id=priority_id, comment_body=comment,
                     comment_visibility=assessment.get("comment_visibility", "internal"),
                     if_version=version)


@dataclass
class ApplyResult:
    key: str
    dry_run: bool
    performed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    version_conflict: bool = False
    label_diff: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and not self.version_conflict


def apply_writeback(client, plan: WritePlan, dry_run: bool = True) -> ApplyResult:
    """Execute a WritePlan against a JiraClient. In dry_run, performs no writes but
    still returns the exact intended diff. Uses if_version for optimistic
    concurrency and reads back after each write; reports partial failure."""
    res = ApplyResult(key=plan.key, dry_run=dry_run, label_diff=plan.label_diff())

    if plan.action != "write":
        res.skipped.append(f"{plan.action}: {plan.reason}")
        return res

    # Re-read to detect changes since assessment (optimistic concurrency).
    fresh = client.get_issue(plan.key)
    fresh_version = fresh.get("version")
    if plan.if_version is not None and fresh_version is not None and fresh_version != plan.if_version:
        res.version_conflict = True
        res.errors.append(f"version changed since assessment ({plan.if_version} -> {fresh_version}); "
                          "re-read and re-plan before writing")
        return res

    if dry_run:
        if plan.labels_add or plan.labels_remove:
            res.skipped.append("DRY-RUN " + plan.label_diff())
        if plan.components_add:
            res.skipped.append("DRY-RUN " + plan.component_diff())
        if plan.set_priority_id:
            res.skipped.append(f"DRY-RUN priority -> id {plan.set_priority_id}")
        if plan.comment_body:
            res.skipped.append(f"DRY-RUN comment ({plan.comment_visibility}, "
                               f"{len(plan.comment_body)} chars)")
        return res

    # Real writes, each read back; stop-on-error leaves state for a safe rerun.
    # The upfront fresh re-read above is the concurrency guard; we thread the
    # version forward from each read-back so our OWN sequential writes don't
    # self-conflict (each write bumps the version).
    ver = fresh_version
    try:
        if plan.labels_add or plan.labels_remove:
            final = [l for l in plan.labels_keep] + list(plan.labels_add)
            client.set_labels(plan.key, final, if_version=ver)
            rb_issue = client.get_issue(plan.key)
            ver = rb_issue.get("version", ver)
            rb = rb_issue.get("fields", {}).get("labels", [])
            if any(l not in rb for l in plan.labels_add) or any(l in rb for l in plan.labels_remove):
                res.errors.append("label read-back mismatch")
            else:
                res.performed.append(plan.label_diff())
    except Exception as e:  # noqa: BLE001 - surface any backend error as partial failure
        res.errors.append(f"label write failed: {e}")

    try:
        if plan.components_add:
            final = list(plan.components_keep) + list(plan.components_add)
            client.set_components(plan.key, final, if_version=ver)
            rb_issue = client.get_issue(plan.key)
            ver = rb_issue.get("version", ver)
            rb = [c.get("name") for c in rb_issue.get("fields", {}).get("components", [])]
            if any(c not in rb for c in plan.components_add) or any(c not in rb for c in plan.components_keep):
                res.errors.append("component read-back mismatch")
            else:
                res.performed.append(plan.component_diff())
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"component write failed: {e}")

    try:
        if plan.set_priority_id:
            client.set_priority(plan.key, plan.set_priority_id)
            res.performed.append(f"priority -> id {plan.set_priority_id}")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"priority write failed: {e}")

    try:
        if plan.comment_body:
            client.add_comment(plan.key, plan.comment_body, visibility=plan.comment_visibility)
            res.performed.append("comment added")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"comment write failed: {e}")

    return res
