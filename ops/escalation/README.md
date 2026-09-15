# Escalation relay

The direct channel between tkfacade's CI agents and the maintainer
(SPEC.md 5.4). Three pieces, all stdlib-only, no third-party services:

- `relay.py` — the queue server: agents post questions, the maintainer's
  browser answers them.
- `mcp_server.py` — the MCP wrapper the fix agent runs: exposes the
  `ask_user` tool, posts to the relay, blocks until answered.
- `ui.html` — the browser client the relay serves at `/`: desktop
  notifications, a beep, reply boxes, history.

Flow: fix agent hits a point where it needs maintainer intent → calls
`ask_user` → relay stores the question → your browser tab notifies → you
type the answer → the agent unblocks and continues. If no answer arrives
within the timeout (default 120 minutes), the tool returns a `[TIMEOUT]`
marker and the agent falls back to GitHub escalation (issue comment +
`escalation` label), so nothing is silently dropped while you are away.

## Deployment (always-on home machine, Tailscale)

The relay binds `127.0.0.1` by design. GitHub Actions runners are not on
the tailnet, so public ingress comes from **Tailscale Funnel**, which
terminates TLS and forwards to localhost. Funnel must be enabled once for
the tailnet (`tailscale funnel --bg <port>` prints the admin URL when it is
not; enabling requires a tailnet admin). Any other TLS-terminating reverse
proxy works too — the relay itself speaks plain HTTP to localhost only.

The reference deployment (the live one) is **user-level, no sudo**: files
under `~/tkfacade-escalation/`, a systemd *user* unit, and `linger` enabled
for the user so the service survives logout and reboot
(`loginctl enable-linger <user>`). A system-level install under `/opt` with
the `escalation-relay.service` template works the same way; adjust
`User=`/paths and add the hardening directives if you prefer it.

1. **Copy the files** to the host: `relay.py` and `ui.html` into
   `~/tkfacade-escalation/` (`mcp_server.py` is CI-side only — it runs from
   the repo checkout inside the workflow).

2. **Generate the two tokens** (on the host, so the UI token never
   travels):

   ```sh
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"  # ASK token
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"  # UI token
   ```

3. **Write the environment file** `~/tkfacade-escalation/env`
   (`chmod 600`):

   ```ini
   ESCALATION_ASK_TOKEN=<the ASK token>
   ESCALATION_UI_TOKEN=<the UI token>
   ESCALATION_STATE=/home/<user>/tkfacade-escalation/state.json
   ```

   Keep the UI token retrievable only by you (e.g. a `ui-token.txt` beside
   it, `chmod 600`).

4. **Install the user unit** `~/.config/systemd/user/tkfacade-escalation.service`:

   ```ini
   [Unit]
   Description=tkfacade escalation relay
   After=network-online.target

   [Service]
   ExecStart=/usr/bin/python3 %h/tkfacade-escalation/relay.py
   EnvironmentFile=%h/tkfacade-escalation/env
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

   then:

   ```sh
   loginctl enable-linger <user>   # once, so the unit runs without a login
   systemctl --user daemon-reload
   systemctl --user enable --now tkfacade-escalation
   curl -s http://127.0.0.1:8787/api/ping
   ```

5. **Expose via Funnel** (persists in tailscaled across reboots):

   ```sh
   tailscale funnel --bg 8787
   tailscale funnel status   # shows the public https://<machine>.<tailnet>.ts.net URL
   ```

   Note: the newer funnel CLI hangs an SSH session if output is not
   detached — run it as `nohup tailscale funnel --bg 8787 >/tmp/funnel.log 2>&1 </dev/null &`
   when deploying over SSH. The public side lands on port 443.

6. **Open the UI** at `https://<machine>.<tailnet>.ts.net/`, paste the
   **UI token**, click Save, then Enable notifications. Leave the tab open
   (pin it). Keep the URL+token somewhere durable — this is your
   escalation inbox.

7. **Wire GitHub Actions** (repo secrets):

   ```sh
   gh secret set ESCALATION_RELAY_URL --body "https://<machine>.<tailnet>.ts.net"
   gh secret set ESCALATION_TOKEN     # paste the ASK token
   ```

   `fix.yml` injects both into the MCP server's environment. Until they
   exist, `ask_user` returns `[UNAVAILABLE]` and agents fall back to
   GitHub escalation — the pipeline degrades safely, it does not break.

8. **Verify end-to-end**:

   ```sh
   curl https://<machine>.<tailnet>.ts.net/api/ping
   curl -X POST https://<machine>.<tailnet>.ts.net/api/ask \
     -H "Authorization: Bearer <ASK token>" -H "Content-Type: application/json" \
     -d '{"question":"deployment self-test","timeout_minutes":5}'
   # answer from the browser tab, then poll with the ask token:
   curl -H "Authorization: Bearer <ASK token>" \
     https://<machine>.<tailnet>.ts.net/api/ask/<id>
   ```

## Operations

- **State**: one JSON file (`ESCALATION_STATE`), rewritten atomically;
  survives restarts; bounded to the last 500 questions. Back it up with
  whatever covers the machine — it is regenerable-by-nature (a lost answer
  falls back to GitHub).
- **Token rotation**: edit the env file, `systemctl restart`, update the
  browser localStorage / the GitHub secret.
- **Updates**: `git pull` a new `relay.py`/`ui.html` into place, restart
  the service. The MCP wrapper ships from the repo checkout inside CI, so
  it is always current with the workflow that runs it.
- **Security notes**: tokens are bearer secrets — the ASK token can file
  questions (nuisance at worst), the UI token can answer them (that is the
  sensitive one; it lives only in your browser and never in CI). Funnel
  serves plain HTTPS to anyone with the URL; without a token every
  non-ping endpoint answers 401.
