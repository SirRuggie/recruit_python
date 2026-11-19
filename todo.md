# Recruit-Python Bot - Todo List

## Current Plan: Pick or upload the post image in the dashboard
**Date**: 2026-11-19
**Status**: Code done and tested 2026-11-19. Deploy (step 7) needs Ruggie.

Goal: in the post editor, choose the image from the WU images already in R2, or upload a new one that goes to R2 under `jo-nation/`, instead of hunting for a URL.

How WU stores images (read from the WU repo): bucket behind `https://wu-media.ruggie.zone`, clan logos and banners under `clans/<Clan Name>/`, keys like `logo.<sha10>.png`, uploaded with boto3 using `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL`.

- [x] 1. Add `boto3` to `requirements.txt` (same as WU). Pillow is already there.
- [x] 2. `dashboard/media.py`: list images under `clans/` and `jo-nation/` (cached 5 minutes), and upload: check the file is a real PNG/JPEG/GIF/WEBP under 10 MB, store it as `jo-nation/recruit/<clan-name>.<hash>.<ext>` with a long cache header (same rules as WU's media_store), return the public URL.
- [x] 3. Routes: `GET /api/images`, `POST /api/images` (logged in + CSRF, like the rest).
- [x] 4. Editor: "Choose image" next to the Image URL field opens a picker with two tabs. **Library**: thumbnails grouped by clan folder, search box, the folder matching the post's clan shown first. **Upload**: pick or drop a file; it uploads and fills the field. Pasting a URL still works. Clear button to remove the image.
- [x] 5. Same `.env` key names as WU. If R2 keys are missing, the picker says so and the rest of the dashboard still works.
- [x] 6. Test with a fake R2 (moto or a stub): list, upload valid image, reject non-image and oversized file, logged-out 401. Screenshots at 360x800 and 1440x1000.
- [ ] 7. Deploy: pull, `pip install -r requirements.txt` in the venv, add the R2 keys to `.env`, restart `jo-nation-dash.service`.

Ruggie chose a new R2 API token for Jo Nation (Object Read & Write on the WU bucket), created 2026-11-19.

### Review
- `dashboard/media.py`: lists `clans/` and `jo-nation/` image keys (5-minute cache, cleared after an upload) and uploads after checking the bytes with Pillow (PNG/JPEG/GIF/WEBP, 10 MB, 40 MP). Key `jo-nation/recruit/<clan-name>.<sha10>.<ext>`, immutable cache header, same R2 client settings as WU.
- `server.py`: `GET/POST /api/images` (login + CSRF), request size raised to 11 MB, CSP allows `blob:` images for the upload preview.
- Editor: current image shown, "Choose image" and "Remove" buttons, paste field kept. Picker: Library tab groups the newest logo/banner per WU clan folder (older copies hidden), the post's clan first, then Jo Nation uploads, with search. Upload tab: pick or drop, preview, "Upload and use".
- `requirements.txt`: `boto3==1.44.6`.
- Tested with a fake bucket: 9 image API checks (logged out 401 on list and upload, missing CSRF 403, a JPEG named .png stored as .jpg, uploaded file served, new upload in library at once, HTML file rejected, over 10 MB rejected, no file 400), missing R2 keys returns a clear 503 message, the 17 earlier API checks still pass. Playwright at 1440x1000 and 360x800: open picker, groups in the right order, search, pick fills the field, upload fills the field; no page errors.
- Not tested: the real R2 bucket. Checked after deploy.

## Done: Scheduled posts dashboard
**Date**: 2026-11-19
**Status**: Live at https://jonation.ruggie.zone since 2026-11-19 (Cloudflare Tunnel route to localhost:8790, no Caddy).

Goal: a small web dashboard where Ruggie can see every scheduled recruitment post the bot sends (MongoDB `settings.auto_recruit`), edit the time, timezone and on/off state, edit what gets posted, and add new ones. Not a long scrolling list. Look and feel taken from dash.warriorsunited.cc (WU's dark theme, gold accent, Inter, 44px controls, mobile-first).

### How it fits with the bot (no change to how posts are sent)
- The bot already re-reads `auto_recruit` from MongoDB every 5 minutes and reschedules every enabled post. The dashboard only reads and writes MongoDB. The bot and the dashboard never talk to each other directly.
- One small bot change: poll every 1 minute instead of 5, so a saved edit takes effect within a minute.

### Ruggie's answers (2026-11-19)
- Hostname: `jonation.ruggie.zone`.
- Only Ruggie logs in.
- Each post sends daily at one or more set times (e.g. twice a day, 12 hours apart).
- Content comes from the saved /post-clan template (stored data). Editing it there is fine.
- Only the 4-5 posts Ruggie schedules show up. Those are exactly the documents in `auto_recruit`; manual /post-clan posts never go there, so nothing else appears.

### Layout (one screen, no long list)
- **Header**: "Next send" countdown (clan, time) and counts: active / paused / errors.
- **24-hour timeline strip**: every send time is a marker on a 0-24h bar in Eastern time. Tap a marker to edit that post.
- **Card grid**: one card per scheduled post (4-5 fit on one screen). Clan badge and name, its send times, posted-as user, last sent, status chip (Active / Paused / Error).
- **Editor drawer** (side panel on desktop, full screen sheet on phone): send times (add/remove, one or more per day), timezone, on/off, clan tag, channel, and the stored post content (description, image URL, Discord link) with a preview. Save, Pause, Delete (with confirm).
- **Add new**: same drawer, empty. Pick who it posts as from saved /post-clan templates.

### Build steps
- [x] 1. `dashboard/server.py`: aiohttp app. Routes: login, logout, list posts, create, update, delete. Reads/writes `auto_recruit` and `recruit_data`. Clan names and badges from the Clash API (`COC_API_TOKEN`, cached). User names from Discord with the bot token (cached).
- [x] 2. Login: "Sign in with Discord" (OAuth2, `identify` scope) with the Jo Nation Helper app. Only IDs in `DASHBOARD_ALLOWED_IDS` get in (just Ruggie). Signed session cookie (HttpOnly, Secure, SameSite=Lax) plus a CSRF header on writes.
- [x] 3. Server-side checks: times HH:MM, real IANA timezone, clan tag exists, IDs are digits. Save fails with "changed elsewhere, reload" if the document changed since it was opened.
- [x] 4. `dashboard/static/`: `index.html`, `app.css`, `app.js`. Plain HTML/CSS/JS, no build step. WU tokens, Lucide icons as inline SVG.
- [x] 5. Bot (`extensions/scheduler/auto_recruit.py`): support a `post_times` list next to the old `post_time` field (one job, fires at each time; old docs keep working), and reload every 1 minute instead of 5.
- [x] 6. Test locally with a throwaway MongoDB and fixture data: list, add, edit, pause, delete, bad inputs, logged-out access. Screenshots at 360x800 and 1440x1000.
- [x] 7. Deploy files: `deploy/jo-nation-dash.service` (as `jonation`, `127.0.0.1:8790`), Caddy site block, `docs/deployment.md` section.
- [x] 8. Go live (Ruggie runs the sudo steps one at a time): `.env` keys, unit, Caddy block, DNS record for `jonation.ruggie.zone`, OAuth redirect URL in the Discord Developer Portal.

### Review (code)
- **Dashboard** (`dashboard/`): `server.py` is the aiohttp app (login, posts API, input checks, Clash and Discord name lookups with a cache). `static/` holds one HTML page, one CSS file (WU tokens, Inter font copied from WU) and one JS file. No build step, no new Python packages.
- **Layout**: next-send countdown and counts at the top, a 24-hour timeline with one marker per send time (stacked when close, paused dimmed, errors red, next one gold), then one card per post with times, posts-as user, channel, last sent, error text, and Edit / Pause buttons. Editor is a side panel (full screen on phone) with on/off, send times (Add time, "Twice a day (+12h)"), timezone, posts-as, clan tag (checked live against the Clash API), channel, description/image/link, and a Discord-style preview.
- **Content rule**: editing text in the dashboard stores it on that post only. The user's saved /post-clan template is not changed. Text equal to the template is not stored, so the template still applies. "Use saved template" resets it. A new post for a user without a template creates one, because the bot disables posts whose user has none.
- **Bot** (`extensions/scheduler/auto_recruit.py`): reads `post_times` (falls back to `post_time`), one job per post using an OR of daily cron triggers, reload every 1 minute, and only reschedules a post when its times or timezone changed (before, every reload removed and re-added every job). Reload log lines moved to debug so the journal isn't flooded every minute. Post text uses the post's own text first, then the template.
- **Security**: Discord OAuth `identify` only; allowlist checked on every request; HMAC-signed HttpOnly cookie; CSRF header on every write; CSP that only allows the page's own scripts; dev login refuses to start unless bound to 127.0.0.1.
- **Tested** (Python 3.12.3, in-memory Mongo via mongomock, fake Clash/Discord lookups): 17 API checks pass (logged out 401, missing CSRF 403, forged cookie 401, every bad field rejected, unknown clan tag rejected, create normalises tag and times and uses the default channel, custom text stays on the post, stale edit 409, reset clears override, pause, resume clears error, template list skips the info-message doc, delete, edit after delete 404, logout). Scheduler: first reload schedules 2 enabled posts (one with two times), second reload reschedules nothing, editing times reschedules only that post, disabled and deleted posts are removed. Browser (Playwright, 1440x1000 and 360x800): no page errors; add a post through the UI, it appears, delete it, it's gone; field errors clear when the field changes.
- **Not tested**: live Discord login, live Clash API and real MongoDB. Those get checked on agent-forge in step 8.

## Done: Host Jo Nation bot on agent-forge and fix bugs
**Date**: 2026-11-19
**Status**: Done 2026-11-19. Bot is live on agent-forge.

Goal: run this bot on agent-forge the same way WU Wizard runs (own OS user, own venv, own .env, own systemd unit), and fix the bugs that stop it from working fully.

### Part A: Code changes (one PR on this repo)
- [x] A1. `/post-edit` no longer resets the 12-hour cooldown. Edits stop overwriting `posted_at`; they set a separate `edited_at` field instead. (`extensions/commands/post_edit.py`)
- [x] A2. Read the recruitment channel ID from `.env` (`RECRUITMENT_CHANNEL_ID`), with the current ID `1144471630614114454` as the default. Put it in one place (`utils/constants.py`) instead of 4 files.
- [x] A3. Pin dependency versions in `requirements.txt` to match the WU bot (hikari 2.6.0, hikari-lightbulb 3.2.6, coc.py 3.10.0, pymongo 4.17.0, APScheduler 3.11.3, and the rest).
- [x] A4. "Use Stored Data" checks the cooldown before opening the form, the same way "Create New Post" already does. (`extensions/commands/post_clan.py`)
- [x] A5. Buttons clicked after a bot restart reply "Session expired, run the command again" instead of "This interaction failed". (`post_clan.py`)
- [x] A6. Add `deploy/jo-nation.service` (systemd unit, copied from the WU Wizard pattern) and a `docs/deployment.md` with the setup and update commands below.
- [x] A8. (Added by Ruggie) Use the official Clash of Clans API instead of the ClashKing proxy, built the same way as the WU bot: `COC_API_TOKEN` in `.env`, client created in `utils/startup.py`, logged in before extensions load. Commands and posts look and work the same.
- [x] A7. Update README: `.env` keys, Python 3.12, how it runs on agent-forge.

### Part B: Host setup on agent-forge (needs Ruggie's computer and sudo)
- [x] B1. Create OS user `jonation` (own home, mode 750, no sudo). Check first that it doesn't already exist.
- [x] B2. As `jonation`: install uv and Python 3.12.3, clone `SirRuggie/recruit_python` to `/home/jonation/recruit_python`, create `venv/`, `pip install -r requirements.txt`.
- [x] B3. Ruggie puts the `.env` in place by file (mode 600, owner jonation): `DISCORD_TOKEN` (the Jo Nation Helper bot's own token, never WU Wizard's), `MONGODB_URI`, `COC_API_TOKEN`, optional `RECRUITMENT_CHANNEL_ID`, `CLOUDINARY_*` optional.
- [x] B4. Install `/etc/systemd/system/jo-nation.service` from `deploy/`, `daemon-reload`, `enable --now`.
- [x] B5. Add `/etc/sudoers.d/jo-nation` so ruggie can run commands as jonation and start/stop/restart/status jo-nation.service only.
- [x] B6. Check `journalctl -u jo-nation.service`, then test `/post-clan` and `/post-edit` in Discord.
- [x] B7. Stop `recruit-bot.service` on the old Hetzner box once the new one works, so two copies don't answer every command twice.

### Follow-ups done during setup
- [x] Removed the Server Members and Message Content intents (Discord returned 4014; the app can't enable them without review, and no code uses them).
- [x] Info-message image moved from Cloudinary (`_archive/`) to the WU R2 bucket: `https://wu-media.ruggie.zone/jo-nation/recruit_info.jpg`.
- [x] Old `recruit-bot.service` on Hetzner (user `recruitbot`) disabled and stopped; its files remain there.

### Things Ruggie must do or confirm
- Discord Developer Portal, Jo Nation Helper app: copy the token and turn on the **Server Members** and **Message Content** intents.
- Get a `COC_API_TOKEN` from developer.clashofclans.com for agent-forge's public IP (or reuse the WU bot's key, which already allows that IP; a separate key keeps the rate limits separate).
- Confirm the recruitment channel ID above is still right.
- Decide whether Jo Nation uses the same Atlas cluster as WU Wizard (shares the Free tier limits) or its own.
- Approve sudo steps B1, B4, B5 when they come up.

### Review (Part A)
- **Clash API**: `main.py` no longer uses `proxy.clashk.ing`. On startup it logs in to `api.clashofclans.com` with `COC_API_TOKEN` (same helper code as WU's `utils/startup.py`). If the token is missing the bot stops with a clear error instead of starting and failing on every command.
- **Cooldown**: `/post-edit` keeps the original `posted_at` and writes `edited_at`, so editing no longer blocks the next post for 12 hours.
- **Channel ID**: one setting, `RECRUITMENT_CHANNEL_ID` in `utils/constants.py`, read from `.env` with the old ID as default. The 4 files import it.
- **Buttons**: both `/post-clan` buttons share one cooldown check (`send_cooldown_if_active`) and reply "Session expired" after a restart.
- **Versions**: pinned to WU's versions. coc.py stays on 3.10.0 like WU; 4.0.0 is a major release WU has not adopted.
- **Deploy**: `deploy/jo-nation.service` and `docs/deployment.md` (setup, `.env` keys, update and rollback commands).
- **Tested** (Python 3.12.3): all extensions load in lightbulb, `/post-clan` and `/post-edit` register, the post layout builds from sample official-API clan data, cooldown and expired-button paths return the right replies, missing token raises the startup error. Not tested: a live call to the Clash API or Discord, because this sandbox cannot reach them.


## Completed Tasks

### Family Links Command Implementation
**Date**: 2025-07-22
**Developer**: Claude with Shaun

#### Changes Made:
1. **Created new standalone command `/family-links`**
   - New file: `extensions/commands/family_links.py`
   - Standalone command (not part of recruit group)
   - Accessible to all server members for self-service role management

2. **Implemented main embed panel with server icon**
   - Dynamic server icon as thumbnail using `guild.make_icon_url()`
   - Title: "Family Clan Links:"
   - Organized sections with separators
   - Warriors United gif as footer image

3. **Town Hall Roles Section**
   - Dropdown with TH17-TH2 (TH17 at top)
   - Uses TH emojis from `utils.emoji`
   - Supports multiple TH role selection
   - Smart role management (only changes what's needed)

4. **Server Roles Section**
   - 6 server roles with descriptions:
     - Base Builder
     - Bot Developer
     - NASDAQ
     - Graphic Designer
     - LazyCWL Participant
     - VC Participant
   - Multiple selection support
   - Clear descriptions for each role

5. **Warriors United Clans Section**
   - 3 buttons: War Clans, FWA Clans, CWL Clans
   - War Clans shows Tactical (top) and Flexible Fun types
   - Each clan list shows emoji, name, and type/tag
   - Back button to return to main panel

#### Technical Details:
- **Interaction Persistence**: Uses MongoDB button_store for session data
- **Error Handling**: Session expiry and member validation
- **Role Management**: Add/remove only changed roles (efficient)
- **Custom Emoji Support**: Handles clan custom emojis properly
- **Component Patterns**: Follows existing codebase conventions

#### Review Summary:
The family links command provides a comprehensive self-service interface for members to manage their roles and explore clan options. It combines TH roles, server activity roles, and clan discovery in one convenient location. 

### Recruit Dashboard - Clan Roles Feature Refactor
**Date**: 2025-07-21
**Developer**: Claude with Shaun

#### Changes Made:
1. **Fixed incorrect MongoDB collection reference**
   - Changed `mongo.onboarding_logs` to `mongo.recruit_onboarding` in server_walkthrough.py
   - Collection was already defined but referenced incorrectly

2. **Refactored clan roles to match townhall roles pattern**
   - Removed "ALL" from button label ("Add Clan Roles to Recruit")
   - Created reusable `build_clan_menu()` helper function
   - Implemented edit-in-place pattern (no new messages)
   - Added multi-select dropdown with clan emoji, name, and tag

3. **Performance optimizations**
   - Replaced individual role add/remove API calls with batched operations
   - Used `member.edit(roles=...)` for single API call updates
   - Reduced operation time from ~1 minute to instant

4. **Fixed clan role selection behavior**
   - Changed from REPLACE to ADD behavior
   - Existing clan roles are now preserved when adding new ones
   - Updated instructions to clarify additive behavior

5. **UI/UX improvements**
   - Removed "Clan Roles Updated!" heading from success messages
   - Shows inline updates: "**Added:** clan1, clan2"
   - Consistent button layout with smart disabled states
   - Clan tags show as just "#ABC123" (removed "Tag: " prefix)

#### Technical Details:
- **Batched Operations**: All role updates now use a single Discord API call
- **Set Operations**: Used Python sets for efficient role calculations
- **Code Reuse**: Created common button row to reduce duplication
- **Error Handling**: Graceful fallbacks if batch operations fail

#### Review Summary:
The clan roles feature now provides a fast, intuitive experience that matches the townhall roles pattern exactly. Users can add clans without losing existing assignments, and all operations complete instantly.

### Post-Clan 12-Hour Cooldown Implementation
**Date**: 2025-07-29
**Developer**: Claude with Shaun

#### Changes Made:
1. **Added 12-hour cooldown system to `/post-clan` command**
   - Imported `timedelta` from datetime module
   - Checks `posted_at` timestamp from recruit_data collection
   - Prevents posting if less than 12 hours since last post

2. **Implemented cooldown check logic**
   - Added check after retrieving stored_data (line 105)
   - Calculates time remaining until next allowed post
   - Shows hours and minutes in user-friendly format

3. **Created informative cooldown error message**
   - Red embed with "⏰ Cooldown Active" title
   - Shows exact time remaining (X hours and Y minutes)
   - Suggests using `/post-edit` to modify existing post

4. **Enhanced stored data display**
   - Updated embed to show "Last Posted: Xh Ym ago" instead of date
   - Helps users understand their cooldown status at a glance

5. **Verified data persistence**
   - Confirmed `posted_at` is saved in all code paths:
     - When save=True (line 431)
     - When updating existing data (line 604)
     - When creating minimal data (line 620)

#### Technical Details:
- **Cooldown Duration**: 12 hours (configurable via `cooldown_hours` variable)
- **Time Calculations**: Uses UTC timezone for consistency
- **Error Handling**: Gracefully handles missing `posted_at` field
- **User Experience**: Clear messaging with actionable alternatives

#### Review Summary:
The 12-hour cooldown system prevents spam while allowing users to edit their existing posts at any time. The implementation provides clear feedback about when users can post again and guides them to use `/post-edit` for modifications.

## Future Tasks

### High Priority
- [ ] Test clan roles with large numbers of clans (25+)
- [ ] Add logging for role operation failures
- [ ] Consider adding individual clan removal (not just "Remove All")

### Medium Priority
- [ ] Add role operation history tracking
- [ ] Create admin command to audit clan role assignments
- [ ] Add bulk operations for multiple users

### Low Priority
- [ ] Add role assignment animations/feedback
- [ ] Create statistics dashboard for clan memberships
- [ ] Add role assignment shortcuts for common combinations

## Notes
- The `__pycache__` directories are Python bytecode caches (add to .gitignore)
- All MongoDB operations should use the collections defined in utils/mongo.py
- Always batch Discord API operations when possible for performance