"""Direct Jira Cloud REST backend (stdlib only, no MCP, no third-party deps).

Implements the same interface the runner/writeback use (get_issue, search,
set_labels, set_components, set_priority, add_comment). Auth is HTTP Basic with
the user's email + an API token read from the macOS Keychain at call time; the
token is never logged and never stored in config.

Optimistic concurrency: Jira has no simple integer version, so `version` is the
issue's `fields.updated` timestamp. writeback captures it at plan time and the
runner re-reads before writing; if `updated` changed, the write is aborted.

Least privilege: an Atlassian API token acts as the user's own Jira identity, so
blast radius is bounded by that account's permissions. The code additionally
refuses to touch anything outside the configured project and only ever sets the
approved fields (labels, components, priority) + one comment.
"""
from __future__ import annotations
import base64, json, urllib.request, urllib.parse, urllib.error
from . import credentials


class RestError(RuntimeError):
    pass


class RestJira:
    def __init__(self, cfg):
        jr = cfg["jira"]
        self.cfg = cfg
        self.base = f"https://{jr['site']}"
        self.project = jr["project"]
        self.email = cfg.get("jira_rest", {}).get("account_email")
        self.timeout = cfg.get("jira_rest", {}).get("timeout_seconds", 30)
        # name -> id maps for components (labels are plain strings; priority passed by id)
        comps = jr.get("components", {})
        self.component_ids = {comps.get("always_add", {}).get("name"): comps.get("always_add", {}).get("id")}
        for name, meta in (comps.get("team") or {}).items():
            self.component_ids[name] = meta["id"]

    # ---- auth / transport ----
    def _auth_header(self) -> str:
        tok = credentials.get_token(self.email)
        if not tok:
            raise RestError("Jira API token not found in Keychain — run `runner.py set-token`.")
        raw = f"{self.email}:{tok}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _request(self, method: str, path: str, body: dict | None = None,
                 query: dict | None = None):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth_header())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            # Never include auth header in errors; include status + short body.
            detail = e.read().decode(errors="replace")[:300]
            raise RestError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise RestError(f"{method} {path} -> {e.reason}") from None

    def _guard_project(self, key: str):
        if not key.startswith(self.project + "-"):
            raise RestError(f"refusing to touch {key}: outside project {self.project}")

    # ---- reads ----
    def get_issue(self, key: str, fields=None) -> dict:
        self._guard_project(key)
        f = ",".join(fields or ["summary", "description", "status", "labels", "priority",
                               "components", "comment", "attachment", "updated", "parent"])
        raw = self._request("GET", f"/rest/api/3/issue/{key}", query={"fields": f})
        raw["version"] = (raw.get("fields", {}) or {}).get("updated")   # concurrency token
        return raw

    def search(self, jql: str, fields=None) -> list[dict]:
        body = {"jql": jql, "maxResults": 100,
                "fields": fields or ["summary", "status", "labels", "created", "updated"]}
        try:
            res = self._request("POST", "/rest/api/3/search/jql", body=body)
        except RestError:
            res = self._request("POST", "/rest/api/3/search", body=body)   # older endpoint
        out = []
        for it in res.get("issues", []):
            row = {"key": it["key"]}
            row.update(it.get("fields", {}))
            out.append(row)
        return out

    # ---- writes (only approved fields; each is small and explicit) ----
    def set_labels(self, key, labels, if_version=None):
        self._guard_project(key)
        self._request("PUT", f"/rest/api/3/issue/{key}", body={"fields": {"labels": list(labels)}})

    def set_components(self, key, names, if_version=None):
        self._guard_project(key)
        comps = []
        for n in names:
            cid = self.component_ids.get(n)
            comps.append({"id": cid} if cid else {"name": n})
        self._request("PUT", f"/rest/api/3/issue/{key}", body={"fields": {"components": comps}})

    def set_priority(self, key, priority_id):
        self._guard_project(key)
        self._request("PUT", f"/rest/api/3/issue/{key}", body={"fields": {"priority": {"id": str(priority_id)}}})

    def add_comment(self, key, body, visibility="internal"):
        self._guard_project(key)
        # SECF is a software project with no external reporter portal, so a normal
        # comment is internal to project members. ADF plain-text body.
        adf = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": body}]}]}
        self._request("POST", f"/rest/api/3/issue/{key}/comment", body={"body": adf})

    def transition(self, *a, **k):
        raise AssertionError("RestJira.transition disabled: this skill never changes status")
