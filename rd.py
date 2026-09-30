"""Retires the README's step-3 caution now that the first live run answered it.

    python3 rd.py

Each anchor must occur exactly once or nothing is written. A second run changes nothing.
"""
import pathlib
import sys

README = pathlib.Path(__file__).resolve().parent / "README.md"

EDITS = [
    (
        "## If step 3 errors\n\n"
        "Step 3 asks Chrome, over the DevTools Protocol, which font it painted. It works in "
        "Playwright’s Chromium; whether Checkly’s runtime allows it wasn’t confirmed before "
        "shipping. If step 3 fails with a protocol error instead of a font name, that’s the "
        "runtime, not the site: note it below and delete step 3.\n",
        "## Step 3 on Checkly’s runtime\n\n"
        "Step 3 asks Chrome, over the DevTools Protocol, which font it painted. Checkly’s "
        "runtime allows it: the first live run passed all three steps on runtime 2026.04.\n",
    ),
    (
        "The Checkly CLI’s own parser loads this project as one browser check, hourly, from "
        "`us-east-1`.\n",
        "The Checkly CLI’s own parser loads this project as one browser check, hourly, from "
        "`us-east-1`.\n\n"
        "Then on Checkly itself, against the live site from `us-east-1`: `npx checkly test` "
        "passed, and `npx checkly test -e SABOTAGE=1` failed at step 2 with “the page declares "
        "a Montserrat 900 face”.\n",
    ),
]

text = README.read_text(encoding="utf-8")
for old, new in EDITS:
    if text.count(new) == 1:  # an insertion keeps its anchor, so test for the result
        print("  already done:", new.splitlines()[0][:60])
        continue
    n = text.count(old)
    if n != 1:
        sys.exit(f"STOP: an anchor was found {n} times, so nothing was written:\n  {old[:70]}")
    text = text.replace(old, new)
    print("  changed:", new.splitlines()[0][:60])
README.write_text(text, encoding="utf-8")
print("README.md is current. Next: rm rd.py")
