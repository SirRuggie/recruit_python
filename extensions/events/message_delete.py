"""
Message Auto-Delete Event Handler
Automatically deletes messages in the recruitment channel that are not from the bot
"""

import lightbulb
import hikari
import logging

loader = lightbulb.Loader()

# Configuration
RECRUITMENT_CHANNEL_ID = 1144471630614114454

# Logger for debugging
logger = logging.getLogger(__name__)


@loader.listener(hikari.MessageCreateEvent)
async def on_message_create(event: hikari.MessageCreateEvent) -> None:
    """Auto-delete messages in recruitment channel that aren't from the bot"""
    
    # Check if message is in the recruitment channel
    if event.channel_id != RECRUITMENT_CHANNEL_ID:
        return
    
    # Get the bot's user ID
    bot_user = event.app.get_me()
    if not bot_user:
        return
    
    # Check if message is from the bot itself
    if event.author_id == bot_user.id:
        return
    
    # Delete the message since it's not from the bot
    try:
        await event.app.rest.delete_message(
            channel=event.channel_id,
            message=event.message_id
        )
        logger.info(f"Deleted message from {event.author_id} in recruitment channel")
    except hikari.ForbiddenError:
        logger.error(f"No permission to delete message {event.message_id}")
    except hikari.NotFoundError:
        logger.error(f"Message {event.message_id} already deleted")
    except Exception as e:
        logger.error(f"Error deleting message {event.message_id}: {e}")