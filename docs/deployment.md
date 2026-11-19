# Deployment (agent-forge)

The bot runs on agent-forge the same way the WU bot does: its own OS user, its own Python and venv, its own `.env`, and its own systemd unit.

| Item | Value |
|---|---|
| OS user | `jonation` (no sudo) |
| Code | `/home/jonation/recruit_python` (git clone of SirRuggie/recruit_python, branch `main`) |
| Python | 3.12.3, installed with uv for `jonation` |
| Venv | `/home/jonation/recruit_python/venv` |
| Secrets | `/home/jonation/recruit_python/.env`, mode 600, owner `jonation` |
| Service | `jo-nation.service` (copy of `deploy/jo-nation.service`) |
| Logs | `journalctl -u jo-nation.service -f` |

## .env keys

| Key | Required | What it is |
|---|---|---|
| `DISCORD_TOKEN` | yes | Token of the Jo Nation Helper Discord app. Never reuse the WU Wizard token. |
| `MONGODB_URI` | yes | MongoDB connection string. The bot uses the `settings` database. |
| `COC_API_TOKEN` | yes | Official Clash of Clans API key from developer.clashofclans.com, created for agent-forge's public IP. The bot will not start without it. |
| `RECRUITMENT_CHANNEL_ID` | no | Channel for recruitment posts. Defaults to `1144471630614114454`. |
| `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | no | Not used by any current command. |

Move a `.env` as a file, never paste it in chat. Install it with:

```bash
sudo install -o jonation -g jonation -m 600 <file> /home/jonation/recruit_python/.env
```

## First-time setup

```bash
# 1. OS user
sudo useradd --create-home --shell /bin/bash jonation
sudo chmod 750 /home/jonation

# 2. Python, code and venv (as jonation)
sudo -u jonation -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u jonation -H bash -lc '~/.local/bin/uv python install 3.12.3'
sudo -u jonation -H git clone https://github.com/SirRuggie/recruit_python.git /home/jonation/recruit_python
sudo -u jonation -H bash -lc 'cd ~/recruit_python && ~/.local/bin/uv venv --seed --python 3.12.3 venv && venv/bin/pip install -r requirements.txt'

# 3. .env (see above)

# 4. Service
sudo install -m 644 /home/jonation/recruit_python/deploy/jo-nation.service /etc/systemd/system/jo-nation.service
sudo systemctl daemon-reload
sudo systemctl enable --now jo-nation.service

# 5. Let ruggie manage it without a password (edit with visudo only)
sudo visudo -f /etc/sudoers.d/jo-nation
```

Contents of `/etc/sudoers.d/jo-nation`:

```
ruggie ALL=(jonation) NOPASSWD: ALL
ruggie ALL=(root) NOPASSWD: /usr/bin/systemctl start jo-nation.service, /usr/bin/systemctl stop jo-nation.service, /usr/bin/systemctl restart jo-nation.service, /usr/bin/systemctl status jo-nation.service
```

The rule matches the exact command, so add no extra flags: `sudo -n systemctl status jo-nation.service` works, `... --no-pager` asks for a password.

## Deploy an update

```bash
sudo -n -u jonation git -C /home/jonation/recruit_python pull
sudo -n -u jonation /home/jonation/recruit_python/venv/bin/pip install -r /home/jonation/recruit_python/requirements.txt
sudo -n systemctl restart jo-nation.service
journalctl -u jo-nation.service -f
```

Rollback: `sudo -n -u jonation git -C /home/jonation/recruit_python reset --hard <old-sha>`, then restart.

Never run `main.py` by hand while the service is up. Two copies on one token answer every command twice. The same applies to the old `recruit-bot.service` on the Hetzner box: stop it once this one works.

## Scheduled posts dashboard

A small web app at https://jonation.ruggie.zone to view, edit, add, pause and delete the bot's scheduled posts (`settings.auto_recruit`). Code is in `dashboard/`. It runs from the same checkout, venv and `.env` as the bot, as its own systemd unit.

| Item | Value |
|---|---|
| Service | `jo-nation-dash.service` (copy of `deploy/jo-nation-dash.service`) |
| Listens on | `127.0.0.1:8790`, behind Caddy (`deploy/Caddyfile.jo-nation-dash`) |
| Logs | `journalctl -u jo-nation-dash.service -f` |
| Login | Discord OAuth2 with the Jo Nation Helper app. Only IDs in `DASHBOARD_ALLOWED_IDS` get in. |

Extra `.env` keys:

| Key | What it is |
|---|---|
| `DASHBOARD_PUBLIC_URL` | `https://jonation.ruggie.zone` |
| `DISCORD_CLIENT_ID` | Jo Nation Helper app's Application ID (Developer Portal, General Information) |
| `DISCORD_CLIENT_SECRET` | Jo Nation Helper app's OAuth2 Client Secret (Developer Portal, OAuth2) |
| `DASHBOARD_SECRET` | Random string that signs the login cookie: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing it signs everyone out. |
| `DASHBOARD_ALLOWED_IDS` | Comma-separated Discord user IDs allowed to sign in |

In the Developer Portal, OAuth2, add the redirect `https://jonation.ruggie.zone/auth/callback`.

How it works with the bot: the dashboard only reads and writes MongoDB. The bot re-reads `auto_recruit` every minute and reschedules a post when its times or timezone change. A post can have several daily times (`post_times`, with `post_time` kept as the first one for older code). Text edited in the dashboard is stored on the post itself (`description`, `image_url`, `discord_link`) and wins over the user's saved /post-clan template; text left equal to the template is not stored, so later /post-edit changes still apply.

Update after a code change: pull as for the bot, then `sudo systemctl restart jo-nation-dash.service`.

Local run with fake data (no Mongo, Discord or Clash calls): not part of the repo; the dashboard can be started with `DASHBOARD_DEV_LOGIN=1` on 127.0.0.1, which skips Discord and signs in as the first allowed ID.

