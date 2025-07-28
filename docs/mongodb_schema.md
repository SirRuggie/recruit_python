# MongoDB Schema Documentation

## Collections

### auto_recruit
Stores automatic recruitment posting schedules.

**Document Structure:**
```json
{
  "_id": "ObjectId or string",  // MongoDB document ID
  "discord_id": "string",        // Discord user ID (e.g., "123456789012345678")
  "clan_tag": "string",          // Clan tag with # (e.g., "#2PYLUR2PV")
  "channel_id": "string",        // Discord channel ID for posting
  "guild_id": "string",          // Discord guild ID
  "post_time": "string",         // Time in 24-hour format (e.g., "14:00")
  "timezone": "string",          // Timezone (e.g., "America/New_York")
  "enabled": boolean,            // Whether auto-posting is enabled
  "last_posted": "datetime",     // Last successful post timestamp
  "last_message_id": "string",   // ID of last posted message
  "error": "string"              // Last error message if any
}
```

### recruit_data
Stores recruitment post data and saved templates.

**Document Structure:**
```json
{
  "_id": "string",               // Discord user ID
  "clan_tag": "string",          // Clan tag with #
  "description": "string",       // Recruitment message
  "image_url": "string",         // Optional image URL
  "discord_link": "string",      // Optional Discord invite link
  "posted_by": "number",         // Discord user ID (numeric)
  "posted_at": "datetime",       // When saved/posted
  "guild_id": "string",          // Discord guild ID
  "message_id": "string",        // Last posted message ID
  "channel_id": "string"         // Last posted channel ID
}
```

### recruitment_info_message
Special document to track the recruitment info message.

**Document Structure:**
```json
{
  "_id": "recruitment_info_message",  // Fixed ID
  "message_id": "string",             // Discord message ID
  "channel_id": "string",             // Discord channel ID
  "updated_at": "datetime"            // Last update timestamp
}
```

## Notes

1. The `auto_recruit` collection uses MongoDB-generated ObjectIds as `_id` but stores the Discord user ID in the `discord_id` field for easier manual management.

2. The `recruit_data` collection uses Discord user IDs directly as `_id` for backward compatibility.

3. When creating new auto_recruit documents manually:
   - Let MongoDB generate the `_id` automatically
   - Always include the `discord_id` field with the user's Discord ID
   - Set `enabled: true` to activate auto-posting
   - Use 24-hour time format for `post_time`