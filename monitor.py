"""rnv-monitors: does everything RNVizion has told people about answer right now?

Reads probes.json, runs every probe, prints a report, writes status.json, and
exits with the same four codes as rnv-brand's checker:

  0  every probe agrees
  1  something disagrees: a surface is down, or answered wrong
  2  the monitor could not run at all (bad probes.json, the brand register
     would not import, a bug here); nothing about the surfaces is known
  3  the sweep was incomplete: some probe is unknown and none disagrees

Every probe ends in one of three states:

  agrees     it answered, and the answer is the expected one
  disagrees  it answered wrong, or it did not answer while its platform's
             control did, so the outage is ours
  unknown    it did not answer and neither did the control, so the platform
             is down and nothing can be said about our surface

Expected answers are read, never typed: the color server's probe expects the
value rnv-brand's register holds for that color, at the pinned commit.

Run:  python monitor.py [--probes probes.json] [--status status.json] [--report report.txt]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

import requests

TIMEOUT = 20
UA = "rnv-monitors (+https://github.com/RNVizion/rnv-monitors)"
KINDS = {"http", "mcp_tool"}
EXIT = {"clean": 0, "disagrees": 1, "could_not_run": 2, "incomplete": 3}
FUSE_WARN_DAYS = 45  # GitHub disables a public repo's schedules after 60 idle days


class NoAnswer(Exception):
    """The surface did not answer at all (connection refused, timeout, DNS)."""


class WrongAnswer(Exception):
    """The surface answered, and the answer was not the expected one."""


class ConfigError(Exception):
    """probes.json, or a sabotage request, cannot be run as written."""


# --- expectations ----------------------------------------------------------

def expected_from_brand(spec: dict):
    """The value the brand register holds, in the requested format."""
    from engine.brand import RNV_BRAND  # rnv-brand, pinned in requirements.txt

    try:
        hex_value = RNV_BRAND[spec["color"]].lstrip("#").lower()
    except KeyError:
        raise ConfigError(f"rnv-brand has no color named {spec['color']!r}") from None
    if spec["format"] == "rgb":
        return [int(hex_value[i:i + 2], 16) for i in (0, 2, 4)]
    if spec["format"] == "hex":
        return "#" + hex_value
    raise ConfigError(f"expect_brand format {spec['format']!r} is not rgb or hex")


# --- transports ------------------------------------------------------------

def http_status(url: str) -> int:
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True).status_code
    except requests.RequestException as exc:
        raise NoAnswer(type(exc).__name__) from exc


def _reply(resp: requests.Response, want_id: int) -> dict:
    """One JSON-RPC reply, from a JSON body or a server-sent event stream."""
    try:
        if "text/event-stream" in resp.headers.get("content-type", ""):
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    message = json.loads(line[5:].strip())
                    if message.get("id") == want_id:
                        return message
            raise WrongAnswer(f"the event stream carried no reply to request {want_id}")
        return resp.json()
    except ValueError:
        raise WrongAnswer(f"request {want_id} got a reply that is not JSON-RPC: {resp.text[:120]!r}") from None


def mcp_call(url: str, tool: str, arguments: dict) -> dict:
    """Call one tool over MCP's Streamable HTTP transport and return its structured result.

    The handshake by hand, so the monitor depends on nothing but requests:
    initialize, the initialized notification, tools/call, then end the session.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    })
    try:
        r = s.post(url, timeout=TIMEOUT, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "rnv-monitors", "version": "1"}},
        })
    except requests.RequestException as exc:
        raise NoAnswer(type(exc).__name__) from exc
    if r.status_code != 200:
        raise WrongAnswer(f"initialize returned HTTP {r.status_code}")
    hello = _reply(r, 1)
    if "result" not in hello:
        raise WrongAnswer(f"initialize was refused: {hello.get('error')}")
    headers = {"MCP-Protocol-Version": hello["result"].get("protocolVersion", "2025-06-18")}
    if r.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = r.headers["mcp-session-id"]
    try:
        s.post(url, timeout=TIMEOUT, headers=headers,
               json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = s.post(url, timeout=TIMEOUT, headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        })
    except requests.RequestException as exc:
        raise NoAnswer(type(exc).__name__) from exc
    if r.status_code != 200:
        raise WrongAnswer(f"tools/call returned HTTP {r.status_code}")
    message = _reply(r, 2)
    if "Mcp-Session-Id" in headers:
        try:
            s.delete(url, timeout=5, headers=headers)
        except requests.RequestException:
            pass  # ending the session is courtesy; the answer is already in hand
    if "error" in message:
        raise WrongAnswer(f"{tool} was refused: {message['error']}")
    result = message["result"]
    texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    if result.get("isError"):
        raise WrongAnswer(f"{tool} returned an error: {' '.join(texts)[:200]}")
    if isinstance(result.get("structuredContent"), dict):
        content = result["structuredContent"]
        return content.get("result", content) if set(content) == {"result"} else content
    try:
        return json.loads(texts[0])
    except (IndexError, ValueError):
        raise WrongAnswer(f"{tool} returned no structured result: {texts[:1]}") from None


# --- probes ----------------------------------------------------------------

def check(probe: dict, sabotaged: bool) -> str:
    """Run one probe. Returns a detail string when it agrees; raises otherwise."""
    if probe["kind"] == "http":
        want = 599 if sabotaged else probe["expect_status"]
        got = http_status(probe["url"])
        if got != want:
            raise WrongAnswer(f"HTTP {got}, expected {want}")
        return f"HTTP {got}"
    # mcp_tool
    spec = probe["expect_brand"]
    want = expected_from_brand(spec)
    if sabotaged:
        want = "a value no server returns (sabotage)"
    answer = mcp_call(probe["url"], probe["tool"], probe["arguments"])
    got = answer.get(spec["format"]) if isinstance(answer, dict) else answer
    if got != want:
        raise WrongAnswer(f"{probe['tool']} answered {got!r}, expected {want!r} from rnv-brand")
    return f"{probe['tool']} answered {got!r}, as rnv-brand holds"


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    probes, controls = config.get("probes"), config.get("controls")
    if not isinstance(probes, list) or not probes or not isinstance(controls, dict):
        raise ConfigError(f"{path} needs a non-empty 'probes' list and a 'controls' map")
    seen = set()
    for p in probes:
        pid = p.get("id")
        if not pid or pid in seen:
            raise ConfigError(f"probe id {pid!r} is missing or repeated")
        seen.add(pid)
        if p.get("kind") not in KINDS:
            raise ConfigError(f"{pid}: kind {p.get('kind')!r} is not one of {sorted(KINDS)}")
        if not str(p.get("url", "")).startswith(("https://", "http://")):
            raise ConfigError(f"{pid}: url {p.get('url')!r} is not a web address")
        if p.get("platform") not in controls:
            raise ConfigError(f"{pid}: platform {p.get('platform')!r} has no control")
        if p["kind"] == "http" and not isinstance(p.get("expect_status"), int):
            raise ConfigError(f"{pid}: an http probe needs an integer expect_status")
        if p["kind"] == "mcp_tool" and not all(k in p for k in ("tool", "arguments", "expect_brand")):
            raise ConfigError(f"{pid}: an mcp_tool probe needs tool, arguments and expect_brand")
    return config


def run(config: dict, sabotage: str | None = None) -> dict:
    ids = [p["id"] for p in config["probes"]]
    if sabotage and sabotage not in ids:
        raise ConfigError(f"sabotage names {sabotage!r}, which is not a probe: {ids}")
    controls: dict[str, bool] = {}

    def control_answers(platform: str) -> bool:
        if platform not in controls:
            try:
                controls[platform] = http_status(config["controls"][platform]) < 500
            except NoAnswer:
                controls[platform] = False
        return controls[platform]

    results = []
    for p in config["probes"]:
        start = time.monotonic()
        try:
            state, detail = "agrees", check(p, sabotaged=(p["id"] == sabotage))
        except WrongAnswer as exc:
            state, detail = "disagrees", str(exc)
        except NoAnswer as exc:
            if control_answers(p["platform"]):
                state, detail = "disagrees", f"no answer ({exc}); the {p['platform']} control answered, so the outage is ours"
            else:
                state, detail = "unknown", f"no answer ({exc}); the {p['platform']} control did not answer either"
        results.append({"id": p["id"], "what": p.get("what", ""), "url": p["url"], "state": state,
                        "detail": detail, "ms": round((time.monotonic() - start) * 1000)})

    states = {r["state"] for r in results}
    code = EXIT["disagrees"] if "disagrees" in states else EXIT["incomplete"] if "unknown" in states else EXIT["clean"]
    overall = {0: "agrees", 1: "disagrees", 3: "unknown"}[code]
    return {"overall": overall, "exit_code": code, "probes": results, "controls": controls, "sabotage": sabotage}


def brand_version() -> str:
    try:
        from importlib.metadata import version
        return version("rnv-brand")
    except Exception:
        return "unknown"


def fuse(main_commit_date: str | None) -> dict | None:
    if not main_commit_date:
        return None
    last = dt.datetime.fromisoformat(main_commit_date.replace("Z", "+00:00"))
    days = (dt.datetime.now(dt.timezone.utc) - last).days
    return {"last_main_commit": main_commit_date, "days_since": days, "warn_after_days": FUSE_WARN_DAYS}


def report_text(status: dict) -> str:
    lines = []
    if status.get("sabotage"):
        lines.append(f"SABOTAGE RUN: probe {status['sabotage']}'s expectation was made wrong on purpose.")
    lines.append(f"rnv-monitors at {status['checked_at']}: {status['overall'].upper()} (exit {status['exit_code']})")
    for r in status["probes"]:
        lines.append(f"  {r['state']:<9}  {r['id']:<22} {r['detail']}")
    f = status.get("fuse")
    if f and f["days_since"] >= FUSE_WARN_DAYS:
        lines.append(f"WARNING: main's last commit is {f['days_since']} days old; GitHub disables this "
                     f"schedule at 60. Push any commit to main to reset it.")
    if status.get("run_url"):
        lines.append(f"Run: {status['run_url']}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--probes", default="probes.json")
    ap.add_argument("--status", default="status.json")
    ap.add_argument("--report", default="report.txt")
    args = ap.parse_args(argv)
    try:
        status = run(load(args.probes), sabotage=os.environ.get("SABOTAGE_PROBE") or None)
    except ConfigError as exc:
        print(f"rnv-monitors could not run: {exc}", file=sys.stderr)
        return EXIT["could_not_run"]
    except Exception as exc:  # a bug here is not a finding about any surface
        print(f"rnv-monitors crashed, which is not a finding about any surface: {exc!r}", file=sys.stderr)
        return EXIT["could_not_run"]

    server, repo, run_id = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    status = {
        "checked_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        **status,
        "rnv_brand": brand_version(),
        "fuse": fuse(os.environ.get("MAIN_COMMIT_DATE")),
        "run_url": f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None,
    }
    text = report_text(status)
    print(text, end="")
    with open(args.status, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
        f.write("\n")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(text)
    return status["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
