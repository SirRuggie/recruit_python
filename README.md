# Recruit-Python

A Discord bot for managing Clash of Clans recruitment posts with automatic scheduling.

## Features

- **Recruitment Posts**: Create formatted clan recruitment posts with `/post-clan`
- **Post Editing**: Edit existing recruitment posts with `/post-edit`
- **Auto-Posting**: Automatic daily recruitment posts managed through MongoDB
- **MongoDB Persistence**: Save recruitment templates for reuse

## Auto-Recruitment System

The bot includes an automatic recruitment posting system that:
- Posts recruitment messages at scheduled times daily
- Managed entirely through MongoDB (no Discord commands)
- Reloads schedules from database every 5 minutes
- Posts in Eastern timezone (America/New_York)

### Managing Auto-Posts

Auto-recruitment is managed by adding/editing documents in the MongoDB `auto_recruit` collection:

```json
{
  "discord_id": "123456789012345678",
  "clan_tag": "#2PYLUR2PV",
  "channel_id": "987654321098765432",
  "guild_id": "111222333444555666",
  "post_time": "14:00",
  "timezone": "America/New_York",
  "enabled": true
}
```

See `docs/manual_auto_recruit_example.md` for detailed instructions.

## Setup

1. Create a `.env` file with:
   ```
   DISCORD_TOKEN=your_bot_token
   MONGODB_URI=your_mongodb_uri
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the bot:
   ```bash
   python main.py
   ```

## MongoDB Collections

- `recruit_data`: Stores recruitment post templates
- `auto_recruit`: Stores automatic posting schedules
- `button_store`: Internal button state management

## Commands

- `/post-clan [save]` - Create a recruitment post
- `/post-edit` - Edit your last recruitment post