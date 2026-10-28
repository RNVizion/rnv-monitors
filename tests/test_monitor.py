"""rnv-monitors' own logic, against local stand-ins: no network, no production calls.

Each state a probe can end in is produced here on purpose, so a green run of this
file means the monitor can say agrees, disagrees and unknown, and exit with each
of its four codes, for the reasons it claims.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import monitor
from engine.brand import RNV_BRAND

HERE = Path(__file__).parent
REPO = HERE.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = {"/ok": 200, "/missing": 404, "/boom": 503}.get(self.path, 404)
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"x")

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def web():
    server = ThreadingHTTPServer(("127.0.0.1", free_port()), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def start_fake_mcp(wrong: bool):
    port = free_port()
    env = {**os.environ, "FAKE_WRONG": "1" if wrong else ""}
    proc = subprocess.Popen([sys.executable, str(HERE / "fake_color_server.py"), str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("the fake color server never started")
    return proc, f"http://127.0.0.1:{port}/mcp"


@pytest.fixture(scope="module")
def mcp_right():
    proc, url = start_fake_mcp(wrong=False)
    yield url
    proc.kill()


@pytest.fixture(scope="module")
def mcp_wrong():
    proc, url = start_fake_mcp(wrong=True)
    yield url
    proc.kill()


DEAD = "http://127.0.0.1:9/"  # port 9 (discard) answers nothing


def config(web, probes, control_up=True):
    return {"controls": {"p": web + "/ok" if control_up else DEAD}, "probes": probes}


def http_probe(pid, url, expect=200):
    return {"id": pid, "kind": "http", "url": url, "expect_status": expect, "platform": "p"}


def mcp_probe(url):
    return {"id": "gold", "kind": "mcp_tool", "url": url, "tool": "convert_color",
            "arguments": {"color": "brand gold", "to": "rgb"},
            "expect_brand": {"color": "brand gold", "format": "rgb"}, "platform": "p"}


# --- positive controls -----------------------------------------------------

def test_expected_value_is_read_from_the_brand_register():
    h = RNV_BRAND["brand gold"].lstrip("#")
    assert monitor.expected_from_brand({"color": "brand gold", "format": "rgb"}) == [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def test_the_repository_probes_file_is_valid():
    cfg = monitor.load(str(REPO / "probes.json"))
    assert {p["platform"] for p in cfg["probes"]} <= set(cfg["controls"])


# --- the three states ------------------------------------------------------

def test_http_agrees(web):
    out = monitor.run(config(web, [http_probe("a", web + "/ok")]))
    assert (out["overall"], out["exit_code"]) == ("agrees", 0)


def test_http_wrong_status_disagrees(web):
    out = monitor.run(config(web, [http_probe("a", web + "/boom")]))
    assert out["probes"][0]["state"] == "disagrees" and out["exit_code"] == 1


def test_expected_404_agrees(web):
    out = monitor.run(config(web, [http_probe("a", web + "/missing", expect=404)]))
    assert out["exit_code"] == 0


def test_no_answer_while_the_control_answers_is_our_outage(web):
    out = monitor.run(config(web, [http_probe("a", DEAD)], control_up=True))
    assert out["probes"][0]["state"] == "disagrees" and "outage is ours" in out["probes"][0]["detail"]


def test_no_answer_while_the_control_is_down_is_unknown(web):
    out = monitor.run(config(web, [http_probe("a", DEAD)], control_up=False))
    assert (out["probes"][0]["state"], out["exit_code"]) == ("unknown", 3)


def test_a_control_answering_5xx_counts_as_the_platform_down(web):
    """On 2026-09-28 Hugging Face's edge answered every Space with a 502: an answer, but not a working platform."""
    cfg = {"controls": {"p": web + "/boom"}, "probes": [http_probe("a", DEAD)]}
    assert monitor.run(cfg)["probes"][0]["state"] == "unknown"


def test_disagrees_outranks_unknown(web):
    probes = [http_probe("a", web + "/boom"), {**http_probe("b", DEAD), "platform": "q"}]
    cfg = {"controls": {"p": web + "/ok", "q": DEAD}, "probes": probes}
    assert monitor.run(cfg)["exit_code"] == 1


# --- the color server, over real MCP ---------------------------------------

def test_mcp_known_answer_agrees(web, mcp_right):
    out = monitor.run(config(web, [mcp_probe(mcp_right)]))
    assert out["exit_code"] == 0, out["probes"][0]["detail"]


def test_mcp_wrong_answer_disagrees(web, mcp_wrong):
    out = monitor.run(config(web, [mcp_probe(mcp_wrong)]))
    assert out["probes"][0]["state"] == "disagrees" and "expected" in out["probes"][0]["detail"]


def test_mcp_unknown_tool_disagrees(web, mcp_right):
    probe = {**mcp_probe(mcp_right), "tool": "no_such_tool"}
    assert monitor.run(config(web, [probe]))["probes"][0]["state"] == "disagrees"


# --- sabotage and refusals -------------------------------------------------

def test_sabotage_turns_an_agreeing_probe_red(web, mcp_right):
    cfg = config(web, [http_probe("a", web + "/ok"), mcp_probe(mcp_right)])
    assert monitor.run(cfg)["exit_code"] == 0
    for target in ("a", "gold"):
        out = monitor.run(cfg, sabotage=target)
        assert out["exit_code"] == 1 and out["sabotage"] == target


def test_sabotage_naming_no_probe_is_refused(web):
    with pytest.raises(monitor.ConfigError):
        monitor.run(config(web, [http_probe("a", web + "/ok")]), sabotage="typo")


@pytest.mark.parametrize("bad", [
    {"probes": [], "controls": {}},
    {"controls": {"p": "x"}, "probes": [{"id": "a", "kind": "ftp", "url": "https://x", "platform": "p"}]},
    {"controls": {"p": "x"}, "probes": [{"id": "a", "kind": "http", "url": "https://x", "expect_status": 200, "platform": "nope"}]},
    {"controls": {"p": "x"}, "probes": [{"id": "a", "kind": "http", "url": "https://x", "expect_status": 200, "platform": "p"},
                                        {"id": "a", "kind": "http", "url": "https://x", "expect_status": 200, "platform": "p"}]},
])
def test_a_probes_file_that_cannot_run_exits_2(tmp_path, bad):
    path = tmp_path / "probes.json"
    path.write_text(json.dumps(bad))
    assert monitor.main(["--probes", str(path), "--status", str(tmp_path / "s.json"),
                         "--report", str(tmp_path / "r.txt")]) == 2


def test_main_writes_status_and_report(tmp_path, web):
    path = tmp_path / "probes.json"
    path.write_text(json.dumps(config(web, [http_probe("a", web + "/ok")])))
    code = monitor.main(["--probes", str(path), "--status", str(tmp_path / "s.json"), "--report", str(tmp_path / "r.txt")])
    status = json.loads((tmp_path / "s.json").read_text())
    assert code == 0 and status["overall"] == "agrees" and status["checked_at"] and status["rnv_brand"]
    assert "AGREES" in (tmp_path / "r.txt").read_text()
