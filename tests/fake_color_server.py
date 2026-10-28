"""A stand-in for rnv-color-mcp, for the tests only.

Same stack as production (FastMCP 3.4.7, Streamable HTTP, stateful sessions) and
the same answer shape as its api.convert_color with `to` given: {"rgb": [...]}.
FAKE_WRONG=1 makes it answer one step off, so the tests can see a wrong answer.
Run: python fake_color_server.py <port>
"""
import os
import sys

from fastmcp import FastMCP

from engine.brand import RNV_BRAND

mcp = FastMCP("fake-rnv-color")


@mcp.tool
def convert_color(color: str, to: str | None = None) -> dict:
    h = RNV_BRAND[color].lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    if os.environ.get("FAKE_WRONG") == "1":
        rgb[0] -= 1
    return {"rgb": rgb} if to == "rgb" else {"hex": "#" + h, "rgb": rgb}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=int(sys.argv[1]), show_banner=False)
