"""
Auto Recruitment Scheduler - Automatically posts recruitment messages at scheduled times
"""

import lightbulb
import hikari
import coc
from datetime import datetime, timezone, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.mongo import MongoClient
from utils.constants import CYAN_ACCENT, GREEN_ACCENT
from utils import bot_data
import pendulum
import logging
from bson import ObjectId

from hikari.impl import (
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    MessageActionRowBuilder as ActionRow,
    LinkButtonBuilder as LinkButton,
    SectionComponentBuilder as Section,
    ThumbnailComponentBuilder as Thumbnail,
)

loader = lightbulb.Loader()

# Configuration
RECRUITMENT_CHANNEL_ID = 1144471630614114454

# Logger for debugging
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    """Initialize the scheduler when bot starts"""
    global scheduler
    
    # Get dependencies
    bot = event.app
    mongo = bot_data.data["mongo"]
    coc_client = bot_data.data["coc_client"]
    
    # Create scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # Load existing scheduled posts
    await load_scheduled_posts(bot, mongo, coc_client)
    
    # Schedule periodic reload of schedules from MongoDB (every 5 minutes)
    scheduler.add_job(
        func=reload_schedules_from_db,
        trigger='interval',
        minutes=5,
        args=[bot, mongo, coc_client],
        id='reload_schedules',
        replace_existing=True,
        misfire_grace_time=60
    )
    
    # Start scheduler
    scheduler.start()
    logger.info("Auto-recruitment scheduler started with MongoDB polling enabled")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    """Shutdown the scheduler when bot stops"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Auto-recruitment scheduler stopped")


async def load_scheduled_posts(bot: hikari.GatewayBot, mongo: MongoClient, coc_client: coc.Client) -> None:
    """Load all enabled auto-recruitment posts from database"""
    try:
        # Find all enabled auto-posts
        cursor = mongo.auto_recruit.find({"enabled": True})
        auto_posts = await cursor.to_list(None)
        
        for post_data in auto_posts:
            # Schedule the post using document _id as job identifier
            schedule_recruitment_post(
                bot=bot,
                mongo=mongo,
                coc_client=coc_client,
                doc_id=str(post_data["_id"]),  # MongoDB document ID
                discord_id=post_data["discord_id"],  # Discord user ID
                post_time=post_data["post_time"],
                timezone_str=post_data.get("timezone", "America/New_York")
            )
            
        logger.info(f"Loaded {len(auto_posts)} scheduled recruitment posts")
        
    except Exception as e:
        logger.error(f"Error loading scheduled posts: {e}")


async def reload_schedules_from_db(bot: hikari.GatewayBot, mongo: MongoClient, coc_client: coc.Client) -> None:
    """Reload schedules from MongoDB - called periodically to pick up changes"""
    global scheduler
    
    try:
        logger.info("Reloading schedules from MongoDB...")
        
        # Get all current jobs
        current_jobs = {job.id: job for job in scheduler.get_jobs() if job.id.startswith("auto_recruit_")}
        
        # Find all auto-posts in database (both enabled and disabled)
        cursor = mongo.auto_recruit.find({})
        all_posts = await cursor.to_list(None)
        
        # Track which jobs we've seen
        seen_jobs = set()
        
        for post_data in all_posts:
            doc_id = str(post_data["_id"])  # MongoDB document ID
            discord_id = post_data.get("discord_id")  # Discord user ID
            job_id = f"auto_recruit_{doc_id}"
            seen_jobs.add(job_id)
            
            if not discord_id:
                logger.warning(f"Document {doc_id} missing discord_id field")
                continue
            
            if post_data.get("enabled", False):
                # Should be scheduled
                if job_id in current_jobs:
                    # Always reschedule to ensure any changes are picked up
                    post_time = post_data.get("post_time", "14:00")
                    timezone_str = post_data.get("timezone", "America/New_York")
                    
                    logger.info(f"Updating schedule for document {doc_id} (Discord user {discord_id})")
                    schedule_recruitment_post(
                        bot=bot,
                        mongo=mongo,
                        coc_client=coc_client,
                        doc_id=doc_id,
                        discord_id=discord_id,
                        post_time=post_time,
                        timezone_str=timezone_str
                    )
                else:
                    # New job - schedule it
                    logger.info(f"Scheduling new job for document {doc_id} (Discord user {discord_id})")
                    schedule_recruitment_post(
                        bot=bot,
                        mongo=mongo,
                        coc_client=coc_client,
                        doc_id=doc_id,
                        discord_id=discord_id,
                        post_time=post_data.get("post_time", "14:00"),
                        timezone_str=post_data.get("timezone", "America/New_York")
                    )
            else:
                # Should not be scheduled
                if job_id in current_jobs:
                    logger.info(f"Removing disabled job for document {doc_id}")
                    scheduler.remove_job(job_id)
        
        # Remove jobs that no longer exist in database
        for job_id in current_jobs:
            if job_id not in seen_jobs and job_id != 'reload_schedules':
                logger.info(f"Removing orphaned job {job_id}")
                scheduler.remove_job(job_id)
                
        logger.info("Schedule reload complete")
        
    except Exception as e:
        logger.error(f"Error reloading schedules: {e}")


def schedule_recruitment_post(
    bot: hikari.GatewayBot,
    mongo: MongoClient,
    coc_client: coc.Client,
    doc_id: str,
    discord_id: str,
    post_time: str,
    timezone_str: str = "America/New_York"
) -> None:
    """Schedule a recruitment post for a specific user"""
    global scheduler
    
    try:
        # Parse time (format: "HH:MM")
        hour, minute = map(int, post_time.split(":"))
        
        # Get timezone
        tz = pendulum.timezone(timezone_str)
        
        # Create job ID using document ID
        job_id = f"auto_recruit_{doc_id}"
        
        # Remove existing job if any
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        
        # Schedule the job - pass both doc_id and discord_id
        scheduler.add_job(
            func=post_recruitment,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            args=[bot, mongo, coc_client, doc_id, discord_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600  # Allow up to 1 hour late
        )
        
        logger.info(f"Scheduled recruitment post for Discord user {discord_id} (doc {doc_id}) at {post_time} {timezone_str}")
        
    except Exception as e:
        logger.error(f"Error scheduling post for Discord user {discord_id}: {e}")


async def post_recruitment(
    bot: hikari.GatewayBot,
    mongo: MongoClient,
    coc_client: coc.Client,
    doc_id: str,
    discord_id: str
) -> None:
    """Post a recruitment message for a user"""
    try:
        # Get auto-post data using document ID
        # Try to find by ObjectId first, then by string if that fails
        try:
            auto_data = await mongo.auto_recruit.find_one({"_id": ObjectId(doc_id)})
        except:
            # If ObjectId conversion fails, try as string
            auto_data = await mongo.auto_recruit.find_one({"_id": doc_id})
        
        if not auto_data or not auto_data.get("enabled"):
            logger.info(f"Auto-post disabled or not found for document {doc_id}")
            return
        
        # Get recruitment data using discord_id
        recruit_data = await mongo.recruit_data.find_one({"_id": discord_id})
        if not recruit_data:
            logger.error(f"No recruitment data found for Discord user {discord_id}")
            # Disable auto-post
            # Update using the same ID type we found the document with
            update_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
            await mongo.auto_recruit.update_one(
                {"_id": update_id},
                {"$set": {"enabled": False, "error": "No recruitment data found"}}
            )
            return
        
        # Get clan data - prioritize auto_data clan_tag (the one they specifically set up)
        clan_tag = auto_data.get("clan_tag")
        if not clan_tag:
            # Fallback to recruit_data clan_tag if not in auto_data
            clan_tag = recruit_data.get("clan_tag")
            if not clan_tag:
                logger.error(f"No clan tag found for Discord user {discord_id}")
                return
        
        try:
            clan = await coc_client.get_clan(clan_tag)
        except coc.NotFound:
            logger.error(f"Clan {clan_tag} not found for Discord user {discord_id}")
            # Disable auto-post
            # Update using the same ID type we found the document with
            update_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
            await mongo.auto_recruit.update_one(
                {"_id": update_id},
                {"$set": {"enabled": False, "error": f"Clan {clan_tag} not found"}}
            )
            return
        except Exception as e:
            logger.error(f"Error fetching clan {clan_tag}: {e}")
            return
        
        # Build the recruitment message
        channel_id = auto_data.get("channel_id", RECRUITMENT_CHANNEL_ID)
        if not channel_id:
            logger.error(f"No channel ID found for Discord user {discord_id}")
            return
        
        # Create the message components
        components = await create_recruitment_components(
            clan=clan,
            recruitment_message=recruit_data.get("description", "Join our clan!"),
            image_url=recruit_data.get("image_url"),
            discord_link=recruit_data.get("discord_link"),
            posted_by_id=int(discord_id)
        )
        
        # Send the message
        try:
            message = await bot.rest.create_message(
                channel=channel_id,
                components=components
            )
            
            # Update last posted time
            update_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
            await mongo.auto_recruit.update_one(
                {"_id": update_id},
                {
                    "$set": {
                        "last_posted": datetime.now(timezone.utc),
                        "last_message_id": message.id,
                        "error": None
                    }
                }
            )
            
            # Update recruit_data with new message ID
            await mongo.recruit_data.update_one(
                {"_id": discord_id},
                {
                    "$set": {
                        "message_id": message.id,
                        "channel_id": channel_id
                    }
                }
            )
            
            # Check if there's an existing recruitment info message and delete it
            recruitment_info_data = await mongo.recruit_data.find_one({"_id": "recruitment_info_message"})
            if recruitment_info_data and "message_id" in recruitment_info_data and "channel_id" in recruitment_info_data:
                try:
                    await bot.rest.delete_message(
                        channel=recruitment_info_data["channel_id"],
                        message=recruitment_info_data["message_id"]
                    )
                except Exception:
                    # Ignore errors if message doesn't exist
                    pass
            
            # Create recruitment info embed
            info_container = Container(
                accent_color=GREEN_ACCENT,
                components=[
                    Text(content="## 📢 **Jo Nation Recruitment Post Process**"),
                    Separator(divider=True),
                    Text(content=(
                        "Our recruitment channels use the **@Jo Nation Helper** to post your recruitment ads. "
                        "This ensures they match our post guidelines. To post, run command `/post-clan`. "
                        "Then, add your clan tag, description, and an optional image. You can also save this info for next time. "
                        "Remember, you can post once every 12 hours."
                    )),
                    Separator(divider=True),
                    Media(items=[MediaItem(media="https://res.cloudinary.com/dxmtzuomk/image/upload/v1753197822/misc_images/image.jpg")])
                ]
            )
            
            # Send recruitment info message
            info_message = await bot.rest.create_message(
                channel=channel_id,
                components=[info_container]
            )
            
            # Store the message ID for future deletion
            await mongo.recruit_data.replace_one(
                {"_id": "recruitment_info_message"},
                {
                    "_id": "recruitment_info_message",
                    "message_id": info_message.id,
                    "channel_id": channel_id,
                    "updated_at": datetime.now(timezone.utc)
                },
                upsert=True
            )
            
            logger.info(f"Successfully posted recruitment and info message for Discord user {discord_id}")
            
        except Exception as e:
            logger.error(f"Error posting message for Discord user {discord_id}: {e}")
            # Update error status
            update_id = ObjectId(doc_id) if ObjectId.is_valid(doc_id) else doc_id
            await mongo.auto_recruit.update_one(
                {"_id": update_id},
                {"$set": {"error": str(e)}}
            )
            
    except Exception as e:
        logger.error(f"Unexpected error in post_recruitment for Discord user {discord_id}: {e}")


async def create_recruitment_components(
    clan: coc.Clan,
    recruitment_message: str,
    image_url: str = None,
    discord_link: str = None,
    posted_by_id: int = None
) -> list:
    """Create the recruitment message components"""
    # Calculate capital hall level
    if clan and clan.capital_districts:
        peak = max(d.hall_level for d in clan.capital_districts)
    else:
        peak = 0
    
    # Get clan tag without #
    clan_tag_clean = clan.tag.replace("#", "")
    
    # Use the clan's share link if available
    clan_link = clan.share_link if hasattr(clan, 'share_link') and clan.share_link else f"https://link.clashofclans.com/en?action=OpenClanProfile&tag={clan_tag_clean}"
    
    # Build components
    components = []
    
    # Create container
    container = Container(
        accent_color=CYAN_ACCENT,
        components=[
            # Title
            Text(content=f"## ⚔️ **{clan.name} Recruitment**"),
            Separator(divider=True),
            
            # Clan Basic Info Section with Badge
            Section(
                components=[
                    Text(content=(
                        f"📌 **Clan Tag:** `{clan.tag}`\n"
                        f"🎖️ **Clan Level:** {clan.level}\n"
                        f"⛰️ **Capital Hall:** Level {peak}\n"
                        f"🏆 **Trophies:** {clan.points:,}\n"
                        f"👥 **Members:** {clan.member_count}\n"
                        f"🌐 **Location:** {clan.location.name if clan.location else 'International'}\n"
                        f"🗣️ **Language:** {clan.chat_language.name if hasattr(clan, 'chat_language') and clan.chat_language else 'Unknown'}"
                    ))
                ],
                accessory=Thumbnail(media=clan.badge.url) if hasattr(clan, 'badge') and clan.badge else None
            ),
            
            Separator(divider=True),
            
            # Clan Stats
            Text(content=(
                f"## 📊 **War Information**\n"
                f"• **War League:** {clan.war_league.name if clan.war_league else 'Unranked'}\n"
                f"• **War Wins:** {clan.war_wins}\n"
                f"• **War Frequency:** {clan.war_frequency if hasattr(clan, 'war_frequency') else 'Always'}\n"
                f"• **Win Streak:** {clan.war_win_streak if hasattr(clan, 'war_win_streak') else 0}"
            )),
            
            Separator(divider=True),
            
            # Recruitment Message
            Text(content="## 📋 **About Our Clan**"),
            Text(content=recruitment_message),
        ]
    )
    
    # Add image if provided
    if image_url:
        container.add_component(Separator(divider=True))
        container.add_component(Media(items=[MediaItem(media=image_url)]))
    
    # Add buttons
    button_row = ActionRow(components=[])
    button_row.add_component(
        LinkButton(
            url=clan_link,
            label="📱 Apply In-Game"
        )
    )
    
    if discord_link:
        button_row.add_component(
            LinkButton(
                url=discord_link,
                label="💬 Join Discord"
            )
        )
    
    container.add_component(button_row)
    container.add_component(Separator(divider=True))
    
    # Add footer
    if posted_by_id:
        container.add_component(
            Text(content=f"\n-# Posted by <@{posted_by_id}> • <t:{int(datetime.now(timezone.utc).timestamp())}:f>")
        )
    else:
        container.add_component(
            Text(content=f"\n-# Posted • <t:{int(datetime.now(timezone.utc).timestamp())}:f>")
        )
    
    components.append(container)
    
    return components


# No longer exporting functions since commands are removed
# Everything is now managed through MongoDB polling