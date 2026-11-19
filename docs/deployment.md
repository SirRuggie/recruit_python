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

## Deploy an update

```bash
sudo -n -u jonation git -C /home/jonation/recruit_python pull
sudo -n -u jonation /home/jonation/recruit_python/venv/bin/pip install -r /home/jonation/recruit_python/requirements.txt
sudo -n systemctl restart jo-nation.service
journalctl -u jo-nation.service -f
```

Rollback: `sudo -n -u jonation git -C /home/jonation/recruit_python reset --hard <old-sha>`, then restart.

Never run `main.py` by hand while the service is up. Two copies on one token answer every command twice. The same applies to the old `recruit-bot.service` on the Hetzner box: stop it once this one works.
