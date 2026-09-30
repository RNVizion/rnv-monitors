"""Writes the rnv-monitors project into the folder this file sits in.

    python3 ck.py

Every file is checked against the tested version, by hash, before anything is
written. An existing file with other content stops the run with nothing written,
except GitHub's starter README, which is replaced. A second run changes nothing.
"""
import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

FILES = {
    'package.json': r'''{
  "name": "rnv-monitors",
  "private": true,
  "description": "Monitoring as code for rnvizion.dev, run by Checkly.",
  "scripts": {
    "check": "checkly test",
    "sabotage": "checkly test -e SABOTAGE=1",
    "deploy": "checkly deploy"
  },
  "devDependencies": {
    "checkly": "^9.5.0"
  },
  "engines": {
    "node": ">=22.13.0"
  }
}
''',
    'checkly.config.ts': r'''import { defineConfig } from 'checkly'
import { Frequency } from 'checkly/constructs'

// Monitoring as code for rnvizion.dev. Checks live in __checks__.
export default defineConfig({
  projectName: 'RNV Monitors',
  logicalId: 'rnv-monitors',
  repoUrl: 'https://github.com/RNVizion/rnv-monitors',
  checks: {
    activated: true,
    muted: false,
    // Hourly from one location keeps this check inside the free plan's monthly browser runs.
    frequency: Frequency.EVERY_1H,
    locations: ['us-east-1'],
    tags: ['rnvizion.dev'],
    checkMatch: '**/__checks__/**/*.check.ts',
  },
  cli: {
    runLocation: 'us-east-1',
  },
})
''',
    '.gitignore': r'''node_modules/
.env
test-results/
*.log
''',
    '__checks__/mark-font.check.ts': r'''import { BrowserCheck } from 'checkly/constructs'

// The check is the Playwright code in mark-font.spec.ts. This file gives it a name;
// the schedule and location come from checkly.config.ts.
new BrowserCheck('mark-font-aiii', {
  name: 'Mark renders in Montserrat 900 on /aiii/',
  code: { entrypoint: './mark-font.spec.ts' },
  tags: ['rnvizion.dev', 'brand', 'fonts'],
})
''',
    '__checks__/mark-font.spec.ts': r'''/**
 * The RNVizion mark on /aiii/ renders in Montserrat 900.
 *
 * Why this exists: on 2026-09-28 a check of this page passed with no fonts loaded.
 * document.fonts.check() returns true for a face nobody declared, so its "true"
 * proved nothing. Each step below can fail on its own, for its own reason:
 *
 *   1. asks    the mark's computed style asks for Montserrat at weight 900
 *   2. loads   the page declares a Montserrat 900 face, and one finishes loading
 *   3. paints  Chrome reports the mark's glyphs were drawn with a downloaded Montserrat
 *
 * Break it on purpose before trusting it:
 *   npx checkly test -e SABOTAGE=1
 * That blocks the Google Fonts stylesheet, the condition the old check passed under:
 * no faces declared at all. Step 2 must fail.
 */
import { test, expect } from '@playwright/test'

const PAGE = 'https://rnvizion.dev/aiii/'
const MARK = 'nav a.logo'

test('mark renders in Montserrat 900 on /aiii/', async ({ page }) => {
  if (process.env.SABOTAGE === '1') {
    await page.route('https://fonts.googleapis.com/**', (route) => route.abort())
  }

  const response = await page.goto(PAGE)
  expect(response?.status(), `status of ${PAGE}`).toBe(200)
  const mark = page.locator(MARK)
  await expect(mark).toContainText('RNVizion')

  await test.step('1. the mark asks for Montserrat 900', async () => {
    const style = await mark.evaluate((el) => {
      const s = getComputedStyle(el)
      return { family: s.fontFamily, weight: s.fontWeight }
    })
    const first = style.family.split(',')[0].trim().replace(/^["']|["']$/g, '')
    expect(first, `font-family is ${style.family}`).toBe('Montserrat')
    expect(style.weight, 'font-weight').toBe('900')
  })

  await test.step('2. a Montserrat 900 face is declared and loads', async () => {
    const statuses = () =>
      page.evaluate(() =>
        [...document.fonts]
          .filter((f) => f.family.replace(/["']/g, '') === 'Montserrat' && f.weight === '900')
          .map((f) => f.status),
      )
    await expect
      .poll(statuses, { message: 'the page declares a Montserrat 900 face', timeout: 10_000 })
      .not.toEqual([])
    await expect
      .poll(statuses, { message: 'a Montserrat 900 face finished loading', timeout: 10_000 })
      .toContain('loaded')
  })

  await test.step('3. Chrome painted the mark with a downloaded Montserrat', async () => {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('DOM.enable')
    await cdp.send('CSS.enable')
    const { root } = await cdp.send('DOM.getDocument')
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: MARK })
    const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId })
    const painted = fonts.map((f) => `${f.familyName} (${f.isCustomFont ? 'downloaded' : 'system'})`)
    expect(fonts.length, 'fonts Chrome used for the mark').toBeGreaterThan(0)
    expect(
      fonts.every((f) => f.isCustomFont && /montserrat/i.test(f.familyName)),
      `fonts Chrome used for the mark: ${painted.join(', ')}`,
    ).toBe(true)
  })
})
''',
    'README.md': r'''# rnv-monitors

Monitoring as code for rnvizion.dev, run by [Checkly](https://www.checklyhq.com). One check so far.

## The check

`__checks__/mark-font.spec.ts` opens rnvizion.dev/aiii/ in Chromium every hour from `us-east-1` and proves the RNVizion mark renders in Montserrat 900. It asks three questions, and each one can fail on its own:

| Step | Question | Fails when |
|---|---|---|
| 1. asks | Does the mark’s computed style ask for Montserrat 900? | the CSS stops naming it |
| 2. loads | Does the page declare a Montserrat 900 face, and does one finish loading? | the font link loses Montserrat, or the stylesheet or the font file doesn’t arrive |
| 3. paints | Which font did Chrome actually draw the mark with? | anything but a downloaded Montserrat, even another file served under Montserrat’s name |

It exists because a quicker check of this page passed on 2026-09-28 with no fonts loaded at all: `document.fonts.check()` answers `true` for a face nobody declared.

## Proved before it shipped

The same spec, run in Chromium against local stand-ins for the site (a fresh clone of `main`) and for Google Fonts:

| Condition | Result | Caught at |
|---|---|---|
| the font served normally | passes | |
| the stylesheet blocked (`SABOTAGE=1`) | fails | step 2: no face declared |
| Montserrat removed from the font link | fails | step 2: no face declared |
| the font file missing | fails | step 2: the face errors instead of loading |
| the mark’s CSS no longer asks for Montserrat | fails | step 1 |
| a different font served under Montserrat’s name | fails | step 3: Chrome painted Inter |

Under the `SABOTAGE=1` condition, the old call still returns `true` while Chrome paints the mark in a system font. The Checkly CLI’s own parser loads this project as one browser check, hourly, from `us-east-1`.

## Run it

You need a Checkly account (the free Hobby plan takes no card) and Node 22.13 or newer.

1. **Keys, kept off the screen.** In Checkly, create an API key under User Settings → API keys, and copy your Account ID from Account Settings → General. In GitHub, add both as Codespaces secrets named `CHECKLY_API_KEY` and `CHECKLY_ACCOUNT_ID`, with access to this repository (Settings → Codespaces → Secrets).
2. **A Codespace on this repository.** Create it after the secrets exist, or restart it; secrets load when a Codespace starts.
3. **Install, and confirm the CLI can see your account:**
   ```
   node -v              # 22.13 or newer; if not: nvm install 22
   npm install
   npx checkly whoami
   ```
4. **Run it, then break it:**
   ```
   npx checkly test                  # should pass
   npx checkly test -e SABOTAGE=1    # must fail at step 2
   ```
   A failure anywhere else is a finding.
5. **Deploy:** `npx checkly deploy` turns it into an hourly monitor.
6. **Decide who hears about it.** In the Checkly app, open the check and make sure an alert channel is subscribed; your email at least. A check that alerts nobody is a control nobody reads.

Shortcuts: `npm run check`, `npm run sabotage`, `npm run deploy`.

## If step 3 errors

Step 3 asks Chrome, over the DevTools Protocol, which font it painted. It works in Playwright’s Chromium; whether Checkly’s runtime allows it wasn’t confirmed before shipping. If step 3 fails with a protocol error instead of a font name, that’s the runtime, not the site: note it below and delete step 3.

## Cost

Hourly from one location comes to about 720 browser-check runs a month; the Hobby plan included 1,000 as of September 2026.

## Friction log

What got in the way during setup, written down as it happened.

-
''',
}

SHA256 = {
    'package.json': 'b46a9887e5e3f9695e27cdc39a0597734f945a262a55fb2480eb5df1a9f7ac97',
    'checkly.config.ts': '03c97c5e21e969506e7cd31fb458cc47563cd2c03b140f954fd4d5fdec0af092',
    '.gitignore': 'f4a57102c1c5453dc979ced13814ef5d9a1d0e6d687add5f5dcfdeff701c071c',
    '__checks__/mark-font.check.ts': '36aba94762fa62f5f6e9934cc1ad06026cc50f21e0ca542e2c0a559507f7403a',
    '__checks__/mark-font.spec.ts': 'd8671081dc1c3a5bdee6c18b4dfb80acde7444fc06b8581da45b2ff67406d459',
    'README.md': 'a5d373d260afdbade75b0dbd7a05574a0b6fcdf0da4c70b72319089b203c0968',
}


def is_starter_readme(path):
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return 0 < len(lines) <= 3 and lines[0] == "# rnv-monitors"


def main():
    mangled = [p for p, t in FILES.items() if hashlib.sha256(t.encode()).hexdigest() != SHA256[p]]
    if mangled:
        sys.exit("STOP: these didn't paste cleanly, so nothing was written: " + ", ".join(mangled))

    plan = []
    for p, t in FILES.items():
        f = HERE / p
        if not f.exists():
            plan.append((p, "write"))
        elif f.read_bytes() == t.encode():
            plan.append((p, "same"))
        elif p == "README.md" and is_starter_readme(f):
            plan.append((p, "replace GitHub's starter README"))
        else:
            sys.exit(f"STOP: {p} already exists with other content, so nothing was written.")

    for p, action in plan:
        if action != "same":
            f = HERE / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(FILES[p].encode())
        print(f"  {action:<32} {p}")

    written = [p for p in FILES if hashlib.sha256((HERE / p).read_bytes()).hexdigest() == SHA256[p]]
    assert len(written) == len(FILES), "a file on disk doesn't match what was tested"
    print("\nAll files match the tested versions. Next:")
    for line in ("rm ck.py", "node -v             (22.13 or newer; if not: nvm install 22)",
                 "npm install", "npx checkly whoami", "npm run check       (should pass)",
                 "npm run sabotage    (must fail at step 2)", "npm run deploy"):
        print("  " + line)


main()
