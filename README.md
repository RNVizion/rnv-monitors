# rnv-monitors

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

Then on Checkly itself, against the live site from `us-east-1`: `npx checkly test` passed, and `npx checkly test -e SABOTAGE=1` failed at step 2 with “the page declares a Montserrat 900 face”.

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

## Step 3 on Checkly’s runtime

Step 3 asks Chrome, over the DevTools Protocol, which font it painted. Checkly’s runtime allows it: the first live run passed all three steps on runtime 2026.04.

## Cost

Hourly from one location comes to about 720 browser-check runs a month; the Hobby plan included 1,000 as of September 2026.

## Friction log

What got in the way during setup, written down as it happened.

- **No zip upload from a phone.** I couldn’t upload a zip into a Codespace from my phone, so the project went in as one pasted script that writes every file and checks each one against the tested version by hash.
- **The trial turns into a Hobby account.** After 14 days without an upgrade, the trial becomes the free Hobby plan; the pricing page didn’t say so as of September 2026.
- **A failure pointed into Checkly’s runtime.** The stack trace named `vm2/lib/bridge.js` and called the spec `test.spec.js`, so the step names and assertion messages had to carry the meaning on their own.
