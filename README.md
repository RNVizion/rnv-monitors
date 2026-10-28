# rnv-monitors

Does everything RNVizion has told people about answer right now? Every 30 minutes, GitHub Actions checks each public surface from outside, opens an issue when one is down, and publishes the answer as `status.json` for the RNV Dashboard to read.

It checks whether things **answer**. Whether they are **right** is [rnv-site-tests](https://github.com/RNVizion/rnv-site-tests)' job.

## What it watches

The probes live in [`probes.json`](probes.json), the one definition of each check; anything else that wants the same check reads that file instead of writing its own.

| Probe | Answer it expects |
|---|---|
| `site-home` | rnvizion.dev returns 200 |
| `site-card` | the contact card returns 200; it's printed and handed to people |
| `color-mcp-glama` | the color server's `/.well-known/glama.json` returns 200 |
| `color-mcp-auth-off` | the color server's OAuth metadata returns 404, because auth is off in production by decision |
| `color-mcp-brand-gold` | over MCP, `convert_color("brand gold", "rgb")` returns the value `rnv-brand`'s register holds, read at the pinned commit, never typed |
| `ask-the-corpus` | the Ask the Corpus demo returns 200 |

## Three states, four exit codes

Each probe ends **agrees**, **disagrees** or **unknown**:

- **agrees:** it answered, and the answer was the expected one.
- **disagrees:** it answered wrong, or it didn't answer while its platform's **control** did, so the outage is ours.
- **unknown:** it didn't answer and neither did the control, so the platform is down and nothing can be said about our surface. On 2026-09-28 Hugging Face's edge answered every Space with errors for about two and a half hours while the Space reported itself healthy; the control is what tells that apart from our own outage. A control answering 5xx counts as down.

The run exits like `rnv-brand`'s checker: **0** every probe agrees · **1** something disagrees · **2** the monitor couldn't run at all · **3** incomplete (something unknown, nothing disagrees). Disagrees outranks unknown.

## What a run leaves behind

- **`status.json` on the `status` branch,** overwritten each run, readable without a token at `https://raw.githubusercontent.com/RNVizion/rnv-monitors/status/status.json`. It carries `checked_at`, so a reader can tell a fresh answer from a stale one: **a status older than about two hours should be read as unknown,** because a schedule that stopped running looks exactly like one that last saw everything fine.
- **Two issues:** `monitor-down` opens on exit 1 and `monitor-coverage` on exit 3; both close when every probe agrees again. Opening one emails you only if you watch this repository (Watch → Custom → Issues): the bot opens issues as itself, so without a watch the issue opens in silence, as the first sabotage run on 2026-10-28 proved. Updates during an outage edit the body silently, so an outage is one email when it starts and one when it ends. Exit 2 touches nothing.
- **Run history** in Actions.

## How it proves it can fail

- **19 tests against local stand-ins,** no network: a small web server, and a stand-in color server on the production stack (FastMCP 3.4.7, Streamable HTTP). Each state and each exit code is produced on purpose, including a wrong MCP answer, an outage with the control up, and a control answering 5xx.
- **Sabotage runs:** Actions → *monitor* → *Run workflow*, with a probe's id in **sabotage_probe**. That probe gets a wrong expectation, so the run must go red and open `monitor-down`, which emails you. That proves the alert reaches you. A sabotage run is never published as the status, and the next scheduled run closes the issue, which proves the recovery path too. A sabotage naming no real probe is refused, never run clean.

## Limits, stated

- **Scheduled runs can start late,** and GitHub disables a public repository's schedules after 60 days without activity. Each status records how old `main`'s last commit is, and the report warns from day 45; any commit to `main` resets it. The dashboard's staleness rule above is the backstop.
- **The controls are other people's pages:** `pages.github.com` for GitHub Pages, and a popular public Space for Hugging Face. If a control disappears, its probes read unknown, never falsely down. Replace it in `probes.json`.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -v          # the monitor's own tests
python monitor.py            # probe the live surfaces once; writes status.json and report.txt
```

## History

From 2026-09-29 to 2026-10-27 this repository was one Checkly browser check, proving the RNVizion mark on `/aiii/` renders in Montserrat 900. It moved to `rnv-site-tests` on 2026-10-27, rewritten in Selenium. While moving it, we found its sabotage blocked Google Fonts, which the site had stopped using, so the sabotage could no longer fail. Checkly's config left in the same commit, and nothing here depends on a Checkly account. The old files are in this repository's history.
