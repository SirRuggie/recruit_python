"""
Post Clan Command - Create clan recruitment posts with modal input
"""

import lightbulb
import hikari
import coc
from datetime import datetime, timezone, UTC, timedelta
import re
from utils.emoji import emojis
from utils.mongo import MongoClient
from utils.constants import GREEN_ACCENT, CYAN_ACCENT

from hikari.impl import (
    ModalActionRowBuilder as ModalActionRow,
    ContainerComponentBuilder as Container,
    TextDisplayComponentBuilder as Text,
    SeparatorComponentBuilder as Separator,
    MediaGalleryComponentBuilder as Media,
    MediaGalleryItemBuilder as MediaItem,
    MessageActionRowBuilder as ActionRow,
    LinkButtonBuilder as LinkButton,
    SectionComponentBuilder as Section,
    ThumbnailComponentBuilder as Thumbnail,
    InteractiveButtonBuilder as Button,
)

loader = lightbulb.Loader()

# Store modal handlers globally
modal_handlers = {}


def ensure_utc_aware(dt):
    """Ensure a datetime is timezone-aware in UTC"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Naive datetime - assume it's UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt

# Configuration
RECRUITMENT_CHANNEL_ID = 1144471630614114454


@loader.listener(hikari.InteractionCreateEvent)
async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
    """Handle modal and button interactions"""
    interaction = event.interaction
    
    # Handle modal interactions
    if isinstance(interaction, hikari.ModalInteraction):
        if interaction.custom_id.startswith("recruitment_modal_"):
            await handle_modal_interaction(interaction)
    
    # Handle button interactions
    elif isinstance(interaction, hikari.ComponentInteraction):
        if interaction.custom_id.startswith("use_stored_"):
            user_id = int(interaction.custom_id.split("_")[-1])
            user_data = modal_handlers.get(user_id)
            
            if user_data and "stored_data" in user_data:
                # Show modal with prefilled data
                await show_recruitment_modal_from_interaction(
                    interaction,
                    user_data["save"],
                    user_data["mongo"],
                    user_data["coc_client"],
                    user_data["bot"],
                    user_data["stored_data"]
                )
        
        elif interaction.custom_id.startswith("new_post_"):
            user_id = int(interaction.custom_id.split("_")[-1])
            user_data = modal_handlers.get(user_id)
            
            if user_data:
                # Check cooldown before showing modal
                cooldown_hours = 12
                cooldown_delta = timedelta(hours=cooldown_hours)
                
                if "stored_data" in user_data and user_data["stored_data"]:
                    stored_data = user_data["stored_data"]
                    if 'posted_at' in stored_data:
                        last_posted = ensure_utc_aware(stored_data['posted_at'])
                        time_since_last_post = datetime.now(timezone.utc) - last_posted
                        
                        if time_since_last_post < cooldown_delta:
                            time_remaining = cooldown_delta - time_since_last_post
                            next_post_time = datetime.now(timezone.utc) + time_remaining
                            next_post_timestamp = int(next_post_time.timestamp())
                            
                            cooldown_embed = hikari.Embed(
                                title="⏰ Cooldown Active",
                                description=f"You can not post again until <t:{next_post_timestamp}:F>",
                                color=0xFF0000
                            )
                            cooldown_embed.add_field(
                                name="💡 Tip",
                                value="Use `/post-edit` to modify your existing recruitment post.",
                                inline=False
                            )
                            await interaction.create_initial_response(
                                hikari.ResponseType.MESSAGE_CREATE,
                                embed=cooldown_embed,
                                flags=hikari.MessageFlag.EPHEMERAL
                            )
                            return
                
                # Show empty modal if no cooldown
                await show_recruitment_modal_from_interaction(
                    interaction,
                    user_data["save"],
                    user_data["mongo"],
                    user_data["coc_client"],
                    user_data["bot"]
                )


@loader.command
class PostClan(
    lightbulb.SlashCommand,
    name="post-clan",
    description="Post a clan recruitment message"
):
    save: bool = lightbulb.boolean("save", "Save this recruitment post to database", default=False)
    
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED
    ) -> None:
        save = self.save
        
        # Check if user has stored recruitment data
        stored_data = await mongo.recruit_data.find_one({"_id": str(ctx.user.id)})
        
        if stored_data:
            # Defer only when we have stored data (since we'll show buttons)
            await ctx.defer(ephemeral=True)
            # Ask if they want to use stored data
            embed = hikari.Embed(
                title="📋 Stored Recruitment Data Found",
                description="You have a saved recruitment post. Would you like to use it?",
                color=GREEN_ACCENT
            )
            embed.add_field(
                name="Clan Tag",
                value=stored_data.get("clan_tag", "N/A"),
                inline=True
            )
            # Calculate time since last post for display
            if 'posted_at' in stored_data:
                last_posted = ensure_utc_aware(stored_data['posted_at'])
                time_since = datetime.now(timezone.utc) - last_posted
                hours_since = int(time_since.total_seconds() // 3600)
                minutes_since = int((time_since.total_seconds() % 3600) // 60)
                
                embed.add_field(
                    name="Last Posted",
                    value=f"{hours_since}h {minutes_since}m ago",
                    inline=True
                )
            else:
                embed.add_field(
                    name="Saved On",
                    value=stored_data.get("posted_at", datetime.now(timezone.utc)).strftime('%B %d, %Y'),
                    inline=True
                )
            
            # Create buttons for user choice
            row = ActionRow()
            use_stored_btn = Button(
                style=hikari.ButtonStyle.SUCCESS,
                label="Use Stored Data",
                custom_id=f"use_stored_{ctx.user.id}"
            )
            new_post_btn = Button(
                style=hikari.ButtonStyle.PRIMARY,
                label="Create New Post",
                custom_id=f"new_post_{ctx.user.id}"
            )
            row.add_component(use_stored_btn)
            row.add_component(new_post_btn)
            
            await ctx.respond(
                embed=embed,
                components=[row]
            )
            
            # Store context for button handlers
            modal_handlers[ctx.user.id] = {
                "save": save,
                "mongo": mongo,
                "coc_client": coc_client,
                "bot": bot,
                "stored_data": stored_data
            }
            return
        
        else:
            # No stored data, show modal directly (don't defer)
            # Store save state for modal callback
            modal_handlers[ctx.user.id] = {
                "save": save,
                "mongo": mongo,
                "coc_client": coc_client,
                "bot": bot
            }
            
            # Build modal using ModalActionRow
            clan_tag_input = ModalActionRow().add_text_input(
                "clan_tag",
                "Clan Tag",
                placeholder="#2PYLUR2PV",
                required=True,
                min_length=3,
                max_length=15,
                style=hikari.TextInputStyle.SHORT
            )
            
            recruitment_message_input = ModalActionRow().add_text_input(
                "recruitment_message",
                "Recruitment Message",
                placeholder="Tell us about your clan...",
                required=True,
                min_length=10,
                max_length=1024,
                style=hikari.TextInputStyle.PARAGRAPH
            )
            
            image_url_input = ModalActionRow().add_text_input(
                "image_url",
                "Image URL (Optional)",
                placeholder="https://example.com/image.png",
                required=False,
                style=hikari.TextInputStyle.SHORT
            )
            
            discord_link_input = ModalActionRow().add_text_input(
                "discord_link",
                "Discord Invite Link (Optional)",
                placeholder="https://discord.gg/invite",
                required=False,
                style=hikari.TextInputStyle.SHORT
            )
            
            await ctx.respond_with_modal(
                title="Post Clan Recruitment",
                custom_id=f"recruitment_modal_{ctx.user.id}",
                components=[clan_tag_input, recruitment_message_input, image_url_input, discord_link_input]
            )


async def show_recruitment_modal(
    ctx: lightbulb.Context,
    save: bool,
    mongo: MongoClient,
    coc_client: coc.Client,
    bot: hikari.GatewayBot,
    prefill_data: dict = None
) -> None:
    """Show the recruitment modal with optional prefilled data"""
    # Store save state for modal callback
    modal_handlers[ctx.user.id] = {
        "save": save,
        "mongo": mongo,
        "coc_client": coc_client,
        "bot": bot
    }
    
    # Build modal using ModalActionRow
    clan_tag_input = ModalActionRow().add_text_input(
        "clan_tag",
        "Clan Tag",
        placeholder="#2PYLUR2PV",
        value=prefill_data.get("clan_tag") if prefill_data and prefill_data.get("clan_tag") else None,
        required=True,
        min_length=3,
        max_length=15,
        style=hikari.TextInputStyle.SHORT
    )
    
    recruitment_message_input = ModalActionRow().add_text_input(
        "recruitment_message",
        "Recruitment Message",
        placeholder="Tell us about your clan...",
        value=prefill_data.get("description") if prefill_data and prefill_data.get("description") else None,
        required=True,
        min_length=10,
        max_length=1024,
        style=hikari.TextInputStyle.PARAGRAPH
    )
    
    image_url_input = ModalActionRow().add_text_input(
        "image_url",
        "Image URL (Optional)",
        placeholder="https://example.com/image.png",
        value=prefill_data.get("image_url") if prefill_data and prefill_data.get("image_url") else None,
        required=False,
        style=hikari.TextInputStyle.SHORT
    )
    
    discord_link_input = ModalActionRow().add_text_input(
        "discord_link",
        "Discord Invite Link (Optional)",
        placeholder="https://discord.gg/invite",
        value=prefill_data.get("discord_link") if prefill_data and prefill_data.get("discord_link") else None,
        required=False,
        style=hikari.TextInputStyle.SHORT
    )
    
    await ctx.respond_with_modal(
        title="Post Clan Recruitment",
        custom_id=f"recruitment_modal_{ctx.user.id}",
        components=[clan_tag_input, recruitment_message_input, image_url_input, discord_link_input]
    )


async def show_recruitment_modal_from_interaction(
    interaction: hikari.ComponentInteraction,
    save: bool,
    mongo: MongoClient,
    coc_client: coc.Client,
    bot: hikari.GatewayBot,
    prefill_data: dict = None
) -> None:
    """Show the recruitment modal from a button interaction"""
    # Store save state for modal callback
    modal_handlers[interaction.user.id] = {
        "save": save,
        "mongo": mongo,
        "coc_client": coc_client,
        "bot": bot
    }
    
    # Build modal using ModalActionRow
    clan_tag_input = ModalActionRow().add_text_input(
        "clan_tag",
        "Clan Tag",
        placeholder="#2PYLUR2PV",
        value=prefill_data.get("clan_tag") if prefill_data and prefill_data.get("clan_tag") else None,
        required=True,
        min_length=3,
        max_length=15,
        style=hikari.TextInputStyle.SHORT
    )
    
    recruitment_message_input = ModalActionRow().add_text_input(
        "recruitment_message",
        "Recruitment Message",
        placeholder="Tell us about your clan...",
        value=prefill_data.get("description") if prefill_data and prefill_data.get("description") else None,
        required=True,
        min_length=10,
        max_length=1024,
        style=hikari.TextInputStyle.PARAGRAPH
    )
    
    image_url_input = ModalActionRow().add_text_input(
        "image_url",
        "Image URL (Optional)",
        placeholder="https://example.com/image.png",
        value=prefill_data.get("image_url") if prefill_data and prefill_data.get("image_url") else None,
        required=False,
        style=hikari.TextInputStyle.SHORT
    )
    
    discord_link_input = ModalActionRow().add_text_input(
        "discord_link",
        "Discord Invite Link (Optional)",
        placeholder="https://discord.gg/invite",
        value=prefill_data.get("discord_link") if prefill_data and prefill_data.get("discord_link") else None,
        required=False,
        style=hikari.TextInputStyle.SHORT
    )
    
    # Create modal response from button interaction
    await interaction.create_modal_response(
        title="Post Clan Recruitment",
        custom_id=f"recruitment_modal_{interaction.user.id}",
        components=[clan_tag_input, recruitment_message_input, image_url_input, discord_link_input]
    )


async def handle_modal_interaction(interaction: hikari.ModalInteraction) -> None:
    """Handle the modal submission"""
    await interaction.create_initial_response(
        hikari.ResponseType.DEFERRED_MESSAGE_CREATE,
        flags=hikari.MessageFlag.EPHEMERAL
    )
    
    # Helper to get modal values
    def get_val(custom_id: str) -> str:
        for row in interaction.components:
            for comp in row:
                if comp.custom_id == custom_id:
                    return comp.value
        return ""
    
    # Extract user ID from custom_id
    user_id = int(interaction.custom_id.split("_")[-1])
    
    # Get stored data
    user_data = modal_handlers.get(user_id)
    if not user_data:
        await interaction.edit_initial_response(
            content="❌ Session expired. Please try again."
        )
        return
    
    save = user_data["save"]
    mongo = user_data["mongo"]
    coc_client = user_data["coc_client"]
    bot = user_data["bot"]
    
    # Safety check: Verify cooldown again to prevent bypassing
    cooldown_hours = 12
    cooldown_delta = timedelta(hours=cooldown_hours)
    
    # Re-fetch current data to ensure we have the latest posted_at
    current_data = await mongo.recruit_data.find_one({"_id": str(user_id)})
    if current_data and 'posted_at' in current_data:
        last_posted = ensure_utc_aware(current_data['posted_at'])
        time_since_last_post = datetime.now(timezone.utc) - last_posted
        
        if time_since_last_post < cooldown_delta:
            time_remaining = cooldown_delta - time_since_last_post
            next_post_time = datetime.now(timezone.utc) + time_remaining
            next_post_timestamp = int(next_post_time.timestamp())
            
            await interaction.edit_initial_response(
                content=f"❌ **Cooldown Active**: You can not post again until <t:{next_post_timestamp}:F>\n💡 Use `/post-edit` to modify your existing post."
            )
            return
    
    # Get values from modal
    clan_tag = get_val("clan_tag").strip().upper()
    recruitment_message = get_val("recruitment_message").strip()
    image_url = get_val("image_url").strip()
    discord_link = get_val("discord_link").strip()
    
    # Validate Discord link if provided
    if discord_link:
        # Add https:// if not present
        if not discord_link.startswith(('http://', 'https://', 'discord://')):
            discord_link = f"https://{discord_link}"
        
        # Validate URL format
        if not discord_link.startswith(('https://discord.gg/', 'https://discord.com/invite/')):
            embed = hikari.Embed(
                title="Invalid Discord Link",
                description="Please provide a valid Discord invite link.\nExample: `https://discord.gg/invite` or `discord.gg/invite`",
                color=0xFF0000
            )
            await interaction.edit_initial_response(embed=embed)
            return
    
    # Validate clan tag
    if not clan_tag.startswith("#"):
        clan_tag = f"#{clan_tag}"
        
    clan_tag_clean = clan_tag.replace("#", "")
    if not re.match(r'^[0289PYLQGRJCUV]+$', clan_tag_clean):
        embed = hikari.Embed(
            title="Invalid Clan Tag",
            description="Please provide a valid clan tag.",
            color=0xFF0000
        )
        await interaction.edit_initial_response(embed=embed)
        return
    
    # Fetch clan data
    try:
        clan = await coc_client.get_clan(clan_tag)
    except coc.NotFound:
        embed = hikari.Embed(
            title="Clan Not Found",
            description=f"No clan found with tag `{clan_tag}`",
            color=0xFF0000
        )
        await interaction.edit_initial_response(embed=embed)
        return
    except Exception as e:
        embed = hikari.Embed(
            title="Error",
            description=f"Failed to fetch clan data: {str(e)}",
            color=0xFF0000
        )
        await interaction.edit_initial_response(embed=embed)
        return
    
    # Save to database if requested (moved after message creation to include message_id)
    save_data_prepared = None
    if save:
        save_data_prepared = {
            "_id": str(interaction.user.id),
            "clan_tag": clan_tag,
            "description": recruitment_message,
            "posted_by": interaction.user.id,
            "posted_at": datetime.now(timezone.utc),
            "guild_id": interaction.guild_id
        }
        
        if image_url:
            save_data_prepared["image_url"] = image_url
        if discord_link:
            save_data_prepared["discord_link"] = discord_link
    
    # Calculate capital hall level
    if clan and clan.capital_districts:
        peak = max(d.hall_level for d in clan.capital_districts)
    else:
        peak = 0
    
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
    container.add_component(
        Text(content=f"\n-# Posted by {interaction.user.mention} • <t:{int(datetime.now(UTC).timestamp())}:f>")
    )
    
    components.append(container)
    
    # Send to recruitment channel if configured, otherwise to current channel
    channel_id = RECRUITMENT_CHANNEL_ID if RECRUITMENT_CHANNEL_ID else interaction.channel_id
    
    try:
        # Send the recruitment post
        message = await bot.rest.create_message(
            channel=channel_id,
            components=components
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
        
        # Always save message ID and channel ID for editing later
        try:
            # Get existing data if any
            existing_data = await mongo.recruit_data.find_one({"_id": str(interaction.user.id)})
            
            if save and save_data_prepared:
                # Full save with all data
                save_data_prepared["message_id"] = message.id
                save_data_prepared["channel_id"] = channel_id
                
                await mongo.recruit_data.replace_one(
                    {"_id": str(interaction.user.id)},
                    save_data_prepared,
                    upsert=True
                )
            else:
                # Just update message ID and channel ID
                update_data = {
                    "message_id": message.id,
                    "channel_id": channel_id,
                    "posted_at": datetime.now(timezone.utc)
                }
                
                if existing_data:
                    # Update existing record
                    await mongo.recruit_data.update_one(
                        {"_id": str(interaction.user.id)},
                        {"$set": update_data}
                    )
                else:
                    # Create minimal record with just IDs
                    minimal_data = {
                        "_id": str(interaction.user.id),
                        "message_id": message.id,
                        "channel_id": channel_id,
                        "posted_by": interaction.user.id,
                        "posted_at": datetime.now(timezone.utc),
                        "guild_id": interaction.guild_id,
                        "clan_tag": clan_tag
                    }
                    await mongo.recruit_data.insert_one(minimal_data)
                    
        except Exception as e:
            # Log error but don't fail the command
            print(f"Failed to save recruitment data: {e}")
        
        # Send success response
        success_embed = hikari.Embed(
            title="✅ Recruitment Post Created",
            description=f"Your recruitment post has been created successfully!",
            color=0x2ECC71
        )
        
        if RECRUITMENT_CHANNEL_ID and channel_id != interaction.channel_id:
            success_embed.add_field(
                name="Posted in",
                value=f"<#{channel_id}>",
                inline=False
            )
        
        if save:
            success_embed.add_field(
                name="Saved to Database",
                value="✅ This recruitment post has been saved and can be retrieved later.",
                inline=False
            )
        
        await interaction.edit_initial_response(embed=success_embed)
        
    except Exception as e:
        error_embed = hikari.Embed(
            title="❌ Error",
            description=f"Failed to create recruitment post: {str(e)}",
            color=0xFF0000
        )
        await interaction.edit_initial_response(embed=error_embed)
    
    # Clean up save state
    if user_id in modal_handlers:
        del modal_handlers[user_id]




