# Manual Auto-Recruit Document Example

When manually adding documents to the `auto_recruit` collection in MongoDB, use this structure:

## Example Document

```json
{
  "discord_id": "123456789012345678",
  "clan_tag": "#2PYLUR2PV",
  "channel_id": "987654321098765432",
  "guild_id": "111222333444555666",
  "post_time": "14:00",
  "timezone": "America/New_York",
  "enabled": true,
  "last_posted": null,
  "last_message_id": null,
  "error": null
}
```

## Important Notes

1. **Do NOT set the `_id` field** - Let MongoDB generate it automatically
2. **Required fields:**
   - `discord_id`: The Discord user ID (as a string)
   - `clan_tag`: The clan tag with # symbol
   - `channel_id`: Discord channel ID where posts should go
   - `guild_id`: Discord server/guild ID
   - `post_time`: Time in 24-hour format (e.g., "14:00" for 2:00 PM)
   - `timezone`: Always use "America/New_York" for Eastern time
   - `enabled`: Set to `true` to enable auto-posting

3. **Optional fields:**
   - `last_posted`: Leave as `null` for new entries
   - `last_message_id`: Leave as `null` for new entries
   - `error`: Leave as `null` for new entries

## MongoDB Compass Instructions

1. Open MongoDB Compass
2. Navigate to your database
3. Open the `settings` database
4. Open the `auto_recruit` collection
5. Click "Add Data" → "Insert Document"
6. Paste the JSON example above and modify the values
7. Click "Insert"

The scheduler will pick up the new document within 5 minutes and start posting at the specified time.