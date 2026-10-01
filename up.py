"""Gets rnv-monitors ready to go public. No license is added, on purpose.

    python3 pub.py

1. Fills the README's friction log.
2. Retires the README's step-3 caution, if rd.py never ran.
3. Lists every file this repo has ever committed, and flags any Checkly key or
   account ID written out in plain text anywhere in its history.

Each anchor must occur exactly once or nothing is written. A second run changes
nothing. It commits nothing and pushes nothing.
"""
import hashlib
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
README = HERE / "README.md"
LICENSE = HERE / "LICENSE"

EDITS = [
    (
        r'''## If step 3 errors

Step 3 asks Chrome, over the DevTools Protocol, which font it painted. It works in Playwright’s Chromium; whether Checkly’s runtime allows it wasn’t confirmed before shipping. If step 3 fails with a protocol error instead of a font name, that’s the runtime, not the site: note it below and delete step 3.
''',
        r'''## Step 3 on Checkly’s runtime

Step 3 asks Chrome, over the DevTools Protocol, which font it painted. Checkly’s runtime allows it: the first live run passed all three steps on runtime 2026.04.
''',
    ),
    (
        r'''The Checkly CLI’s own parser loads this project as one browser check, hourly, from `us-east-1`.
''',
        r'''The Checkly CLI’s own parser loads this project as one browser check, hourly, from `us-east-1`.

Then on Checkly itself, against the live site from `us-east-1`: `npx checkly test` passed, and `npx checkly test -e SABOTAGE=1` failed at step 2 with “the page declares a Montserrat 900 face”.
''',
    ),
    (
        r'''## Friction log

What got in the way during setup, written down as it happened.

-
''',
        r'''## Friction log

What got in the way during setup, written down as it happened.

- **No zip upload from a phone.** I couldn’t upload a zip into a Codespace from my phone, so the project went in as one pasted script that writes every file and checks each one against the tested version by hash.
- **The trial turns into a Hobby account.** After 14 days without an upgrade, the trial becomes the free Hobby plan; the pricing page didn’t say so as of September 2026.
- **A failure pointed into Checkly’s runtime.** The stack trace named `vm2/lib/bridge.js` and called the spec `test.spec.js`, so the step names and assertion messages had to carry the meaning on their own.
''',
    ),
]

SHA256_EDITS = "773a503eb71ef1715fcce6bba7497c26f053c75bb84f463e0c0275e9acf363e1"

# Files the setup is known to produce. Anything else in history gets a second look.
KNOWN = {
    "README.md", "package.json", "package-lock.json", "checkly.config.ts", ".gitignore",
    "__checks__/mark-font.check.ts", "__checks__/mark-font.spec.ts",
}
SETUP_SCRIPTS = {"ck.py", "rd.py", "pb.py", "pub.py"}
SECRET = re.compile(r"CHECKLY_(?:API_KEY|ACCOUNT_ID)\s*[=:]\s*[\"']?[A-Za-z0-9_-]{8,}")


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout


def main():
    if sha("".join(o + n for o, n in EDITS)) != SHA256_EDITS:
        sys.exit("STOP: the script didn't paste cleanly, so nothing was written.")

    text = README.read_text(encoding="utf-8")
    report = []
    for old, new in EDITS:
        head = new.splitlines()[0][:60]
        if text.count(new) == 1:  # an insertion keeps its anchor, so test for the result
            report.append(("already done", head))
            continue
        n = text.count(old)
        if n != 1:
            sys.exit(f"STOP: an anchor in README.md was found {n} times, so nothing was written:\n  {old[:70]!r}")
        text = text.replace(old, new)
        report.append(("changed", head))

    README.write_text(text, encoding="utf-8")
    for action, head in report:
        print(f"  {action:<13} README: {head}")
    if LICENSE.exists():
        print("\nA LICENSE file is here. You chose no license for now, so delete it before you commit: rm LICENSE")

    print("\nEvery file this repo has ever committed:")
    try:
        paths = sorted(set(git("log", "--all", "--name-only", "--format=").split()))
        patch = git("log", "--all", "-p")
    except Exception as e:
        print("  couldn't read the history:", e)
        return
    odd = 0
    for p in paths:
        if p in KNOWN:
            note = ""
        elif p in SETUP_SCRIPTS:
            note = "   setup script: harmless, it holds only the project files"
        else:
            note = "   <- not from the setup; look at it before going public"
            odd += 1
        print("  " + p + note)
    hits = SECRET.findall(patch)
    if hits:
        n = len(hits)
        print(f"\nSTOP BEFORE GOING PUBLIC: a Checkly key or account ID is written out in this repo's history, in {n} place{'s' if n != 1 else ''}.")
        print("Making the repo public would publish it. If it's the API key, rotate it in Checkly; either way, keep the repo private until the history is cleaned.")
        print("Committing and pushing are still fine while it stays private.")
    elif odd:
        print("\nNo Checkly key or account ID in the history. Check the flagged file before going public.")
    else:
        print("\nNo Checkly key or account ID in the history, and nothing unexpected.")
    print("Next: rm pub.py, then commit and push.")


main()
