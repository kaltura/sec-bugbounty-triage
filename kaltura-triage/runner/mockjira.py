"""In-memory mock Jira that RECORDS every attempted call. Used by the operational-
risk tests to prove the writeback logic behaves safely without touching real Jira.
Because it records attempts, it can demonstrate that unauthorized writes are NOT
attempted (an offline test with no write tools could not show that)."""
from __future__ import annotations
import copy


class MockJira:
    def __init__(self, issues: dict):
        # issues: {key: {"key":..., "version":int, "fields":{...}}}
        self.issues = copy.deepcopy(issues)
        self.calls = []                      # every attempted call (audit log)
        self.fail_on = set()                 # call names to simulate failing, e.g. {"add_comment"}
        self.mutate_before = {}              # key -> fn(issue) applied before next get_issue (races)

    # ---- reads ----
    def get_issue(self, key, fields=None):
        self.calls.append(("get_issue", key))
        if key in self.mutate_before:
            self.mutate_before.pop(key)(self.issues[key])
        return copy.deepcopy(self.issues[key])

    def search(self, jql, fields=None):
        self.calls.append(("search", jql))
        return list(self.issues.values())

    # ---- writes (recorded; enforce if_version) ----
    def set_labels(self, key, labels, if_version=None):
        self.calls.append(("set_labels", key, tuple(labels), if_version))
        if "set_labels" in self.fail_on:
            raise RuntimeError("simulated label write failure")
        self._check_version(key, if_version)
        self.issues[key]["fields"]["labels"] = list(labels)
        self.issues[key]["version"] += 1

    def set_priority(self, key, priority_id):
        self.calls.append(("set_priority", key, priority_id))
        if "set_priority" in self.fail_on:
            raise RuntimeError("simulated priority write failure")
        self.issues[key]["fields"].setdefault("priority", {})["id"] = priority_id
        self.issues[key]["version"] += 1

    def set_components(self, key, names, if_version=None):
        self.calls.append(("set_components", key, tuple(names), if_version))
        if "set_components" in self.fail_on:
            raise RuntimeError("simulated component write failure")
        self._check_version(key, if_version)
        self.issues[key]["fields"]["components"] = [{"name": n} for n in names]
        self.issues[key]["version"] += 1

    def add_comment(self, key, body, visibility="internal"):
        self.calls.append(("add_comment", key, visibility, body))
        if "add_comment" in self.fail_on:
            raise RuntimeError("simulated comment write failure")
        self.issues[key]["fields"].setdefault("comment", {}).setdefault("comments", []).append(
            {"id": f"c{len(self.calls)}", "body": body, "visibility": visibility,
             "author": {"displayName": "Kaltura Triage (local)"}})
        self.issues[key]["version"] += 1

    def transition(self, *a, **k):          # must never be called by the skill/runner
        self.calls.append(("transition", a, k))
        raise AssertionError("transition() must not be called by triage writeback")

    # ---- helpers ----
    def _check_version(self, key, if_version):
        if if_version is not None and self.issues[key]["version"] != if_version:
            raise RuntimeError(f"version conflict: have {self.issues[key]['version']}, expected {if_version}")

    def write_calls(self):
        return [c for c in self.calls if c[0] in ("set_labels", "set_priority", "add_comment",
                                                  "set_components", "transition")]
