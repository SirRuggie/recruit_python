# Recruit-Python Bot - Todo List

## Current Plan: Host Jo Nation bot on agent-forge and fix bugs
**Date**: 2026-11-19
**Status**: Waiting for Ruggie's OK

Goal: run this bot on agent-forge the same way WU Wizard runs (own OS user, own venv, own .env, own systemd unit), and fix the bugs that stop it from working fully.

### Part A: Code changes (one PR on this repo)
- [ ] A1. `/post-edit` no longer resets the 12-hour cooldown. Edits stop overwriting `posted_at`; they set a separate `edited_at` field instead. (`extensions/commands/post_edit.py`)
- [ ] A2. Read the recruitment channel ID from `.env` (`RECRUITMENT_CHANNEL_ID`), with the current ID `1144471630614114454` as the default. Put it in one place (`utils/constants.py`) instead of 4 files.
- [ ] A3. Pin dependency versions in `requirements.txt` to the versions tested on 2026-11-19 (hikari 2.6.0, hikari-lightbulb 3.2.7, coc.py 4.0.0, APScheduler 3.11.3, pymongo 4.20.0, pendulum 3.3.0, and the rest).
- [ ] A4. "Use Stored Data" checks the cooldown before opening the form, the same way "Create New Post" already does. (`extensions/commands/post_clan.py`)
- [ ] A5. Buttons clicked after a bot restart reply "Session expired, run the command again" instead of "This interaction failed". (`post_clan.py`)
- [ ] A6. Add `deploy/jo-nation.service` (systemd unit, copied from the WU Wizard pattern) and a `docs/deployment.md` with the setup and update commands below.
- [ ] A7. Update README: `.env` keys, Python 3.12, how it runs on agent-forge.

### Part B: Host setup on agent-forge (needs Ruggie's computer and sudo)
- [ ] B1. Create OS user `jonation` (own home, mode 750, no sudo). Check first that it doesn't already exist.
- [ ] B2. As `jonation`: install uv and Python 3.12.3, clone `SirRuggie/recruit_python` to `/home/jonation/recruit_python`, create `venv/`, `pip install -r requirements.txt`.
- [ ] B3. Ruggie puts the `.env` in place by file (mode 600, owner jonation): `DISCORD_TOKEN` (the Jo Nation Helper bot's own token, never WU Wizard's), `MONGODB_URI`, optional `RECRUITMENT_CHANNEL_ID`, `CLOUDINARY_*` optional.
- [ ] B4. Install `/etc/systemd/system/jo-nation.service` from `deploy/`, `daemon-reload`, `enable --now`.
- [ ] B5. Add `/etc/sudoers.d/jo-nation` so ruggie can run commands as jonation and start/stop/restart/status jo-nation.service only.
- [ ] B6. Check `journalctl -u jo-nation.service`, then test `/post-clan` and `/post-edit` in Discord.
- [ ] B7. Stop `recruit-bot.service` on the old Hetzner box once the new one works, so two copies don't answer every command twice.

### Things Ruggie must do or confirm
- Discord Developer Portal, Jo Nation Helper app: copy the token and turn on the **Server Members** and **Message Content** intents.
- Confirm the recruitment channel ID above is still right.
- Decide whether Jo Nation uses the same Atlas cluster as WU Wizard (shares the Free tier limits) or its own.
- Approve sudo steps B1, B4, B5 when they come up.


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