"""
Post Edit Command - Edit existing clan recruitment posts
"""

import lightbulb
import hikari
import coc
from datetime import datetime, timezone, UTC
import re
from utils.mongo import MongoClient
from utils.constants import CYAN_ACCENT

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

# Configuration - should match post_clan.py
RECRUITMENT_CHANNEL_ID = None  # Set this to your recruitment channel ID


@loader.listener(hikari.InteractionCreateEvent)
async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
    """Handle modal and button interactions"""
    interaction = event.interaction
    
    if isinstance(interaction, hikari.ModalInteraction):
        if interaction.custom_id.startswith("edit_recruitment_modal_"):
            await handle_edit_modal_interaction(interaction)
    
    elif isinstance(interaction, hikari.ComponentInteraction):
        if interaction.custom_id.startswith("load_edit_data_"):
            await handle_load_edit_data(interaction)


@loader.command
class PostEdit(
    lightbulb.SlashCommand,
    name="post-edit",
    description="Edit your existing clan recruitment post"
):
    @lightbulb.invoke
    @lightbulb.di.with_di
    async def invoke(
        self,
        ctx: lightbulb.Context,
        mongo: MongoClient = lightbulb.di.INJECTED,
        bot: hikari.GatewayBot = lightbulb.di.INJECTED,
        coc_client: coc.Client = lightbulb.di.INJECTED
    ) -> None:
        # Defer the response immediately to avoid timeout
        await ctx.defer(ephemeral=True)
        
        # Check if user has stored recruitment data
        stored_data = await mongo.recruit_data.find_one({"_id": str(ctx.user.id)})
        
        if not stored_data:
            embed = hikari.Embed(
                title="❌ No Saved Recruitment Post",
                description="You don't have any saved recruitment data. Please use `/post-clan` with the save option to create one first.",
                color=0xFF0000
            )
            await ctx.respond(embed=embed)
            return
        
        # Store context and data for modal handler
        channel_id = RECRUITMENT_CHANNEL_ID if RECRUITMENT_CHANNEL_ID else ctx.channel_id
        modal_handlers[ctx.user.id] = {
            "save": True,
            "mongo": mongo,
            "coc_client": coc_client,
            "bot": bot,
            "channel_id": channel_id,
            "is_edit": True,
            "stored_data": stored_data  # Store the data here
        }
        
        # Show a button to load data
        embed = hikari.Embed(
            title="📝 Edit Recruitment Post",
            description="Click the button below to edit your saved recruitment data.",
            color=CYAN_ACCENT
        )
        embed.add_field(
            name="Clan Tag",
            value=stored_data.get("clan_tag", "N/A"),
            inline=True
        )
        embed.add_field(
            name="Last Updated",
            value=stored_data.get("posted_at", datetime.now(timezone.utc)).strftime('%B %d, %Y'),
            inline=True
        )
        
        row = ActionRow()
        load_button = Button(
            style=hikari.ButtonStyle.PRIMARY,
            label="Edit My Recruitment Post",
            custom_id=f"load_edit_data_{ctx.user.id}"
        )
        row.add_component(load_button)
        
        await ctx.respond(
            embed=embed,
            components=[row]
        )


async def handle_load_edit_data(interaction: hikari.ComponentInteraction) -> None:
    """Handle button click to load edit data"""
    user_id = int(interaction.custom_id.split("_")[-1])
    
    # Get stored handler data
    user_data = modal_handlers.get(user_id)
    if not user_data:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ Session expired. Please try the command again.",
            components=[]
        )
        return
    
    # Get the stored data (already loaded in the command)
    stored_data = user_data.get("stored_data")
    if not stored_data:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ No data found. Please try the command again.",
            components=[]
        )
        return
    
    # Show modal with prefilled data (don't acknowledge the interaction first)
    await show_edit_modal_from_interaction(interaction, stored_data)


async def show_edit_modal_from_interaction(interaction: hikari.ComponentInteraction, prefill_data: dict) -> None:
    """Show the edit modal from a button interaction with prefilled data"""
    # Build modal using ModalActionRow
    clan_tag_input = ModalActionRow().add_text_input(
        "clan_tag",
        "Clan Tag",
        placeholder="#2PYLUR2PV",
        value=prefill_data.get("clan_tag", "") or None,
        required=True,
        min_length=3,
        max_length=15,
        style=hikari.TextInputStyle.SHORT
    )
    
    recruitment_message_input = ModalActionRow().add_text_input(
        "recruitment_message",
        "Recruitment Message",
        placeholder="Tell us about your clan...",
        value=prefill_data.get("description", "") or None,
        required=True,
        min_length=10,
        max_length=1024,
        style=hikari.TextInputStyle.PARAGRAPH
    )
    
    image_url_input = ModalActionRow().add_text_input(
        "image_url",
        "Image URL (Optional)",
        placeholder="https://example.com/image.png",
        value=prefill_data.get("image_url", "") or None,
        required=False,
        style=hikari.TextInputStyle.SHORT
    )
    
    discord_link_input = ModalActionRow().add_text_input(
        "discord_link",
        "Discord Invite Link (Optional)",
        placeholder="https://discord.gg/invite",
        value=prefill_data.get("discord_link", "") or None,
        required=False,
        style=hikari.TextInputStyle.SHORT
    )
    
    await interaction.create_modal_response(
        title="Edit Clan Recruitment",
        custom_id=f"edit_recruitment_modal_{interaction.user.id}",
        components=[clan_tag_input, recruitment_message_input, image_url_input, discord_link_input]
    )


async def handle_edit_modal_interaction(interaction: hikari.ModalInteraction) -> None:
    """Handle the edit modal submission"""
    # Extract user ID from custom_id first (before any async operations)
    user_id = int(interaction.custom_id.split("_")[-1])
    
    # Create initial response IMMEDIATELY to avoid timeout
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
    
    # Get stored data
    user_data = modal_handlers.get(user_id)
    if not user_data:
        await interaction.edit_initial_response(
            content="❌ Session expired. Please try again."
        )
        return
    
    mongo = user_data["mongo"]
    coc_client = user_data["coc_client"]
    bot = user_data["bot"]
    channel_id = user_data["channel_id"]
    
    # Get stored data from modal handler (already loaded)
    stored_data = user_data.get("stored_data")
    if not stored_data:
        # Double-check in database
        stored_data = await mongo.recruit_data.find_one({"_id": str(interaction.user.id)})
        if not stored_data:
            embed = hikari.Embed(
                title="❌ No Saved Recruitment Post",
                description="You don't have any saved recruitment data. Please use `/post-clan` to create one first.",
                color=0xFF0000
            )
            await interaction.edit_initial_response(embed=embed)
            return
    
    # Get values from modal
    clan_tag = get_val("clan_tag").strip().upper()
    recruitment_message = get_val("recruitment_message").strip()
    image_url = get_val("image_url").strip()
    discord_link = get_val("discord_link").strip()
    
    # Validate Discord link if provided
    if discord_link:
        if not discord_link.startswith(('http://', 'https://', 'discord://')):
            discord_link = f"https://{discord_link}"
        
        if not discord_link.startswith(('https://discord.gg/', 'https://discord.com/invite/')):
            embed = hikari.Embed(
                title="Invalid Discord Link",
                description="Please provide a valid Discord invite link.\nExample: `https://discord.gg/invite`",
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
    
    # Update stored data (preserve message_id and channel_id)
    try:
        save_data = {
            "_id": str(interaction.user.id),
            "clan_tag": clan_tag,
            "description": recruitment_message,
            "posted_by": interaction.user.id,
            "posted_at": datetime.now(timezone.utc),
            "guild_id": interaction.guild_id,
            "message_id": stored_data.get("message_id"),  # Preserve message ID
            "channel_id": stored_data.get("channel_id")   # Preserve channel ID
        }
        
        if image_url:
            save_data["image_url"] = image_url
        if discord_link:
            save_data["discord_link"] = discord_link
            
        await mongo.recruit_data.replace_one(
            {"_id": str(interaction.user.id)},
            save_data,
            upsert=True
        )
    except Exception as e:
        embed = hikari.Embed(
            title="Save Failed",
            description=f"Failed to save recruitment data: {str(e)}",
            color=0xFF0000
        )
        await interaction.edit_initial_response(embed=embed)
        return
    
    # Update the existing message if we have the message ID
    messages_updated = 0
    if not stored_data.get("message_id") or not stored_data.get("channel_id"):
        # No message ID stored - likely created without save option
        info_embed = hikari.Embed(
            title="ℹ️ No Previous Post Found",
            description=(
                "No previous recruitment post was found to update. This usually happens when:\n"
                "• The original post was created without the save option\n"
                "• The post was created before the update feature was added\n\n"
                "Your recruitment data has been saved. Use `/post-clan` to create a new post with this data."
            ),
            color=0x3498DB
        )
        await interaction.edit_initial_response(embed=info_embed)
        return
    
    if stored_data.get("message_id") and stored_data.get("channel_id"):
        try:
            # Fetch the specific message
            message = await bot.rest.fetch_message(
                channel=stored_data["channel_id"],
                message=stored_data["message_id"]
            )
            
            # Update it with new content
            await update_recruitment_message(
                bot, message, clan, clan_tag_clean,
                recruitment_message, image_url, discord_link,
                interaction.user
            )
            messages_updated = 1
            
        except hikari.NotFoundError:
            # Message was deleted
            success_embed = hikari.Embed(
                title="⚠️ Original Message Not Found",
                description="Your original recruitment post was deleted. Data has been updated for next time you post.",
                color=0xFFA500
            )
            await interaction.edit_initial_response(embed=success_embed)
            return
        except Exception as e:
            print(f"Error updating message: {e}")
            error_embed = hikari.Embed(
                title="⚠️ Failed to Update Message",
                description=f"Could not update the recruitment post: {str(e)}\n\nYour data has been saved for next time.",
                color=0xFFA500
            )
            await interaction.edit_initial_response(embed=error_embed)
            return
    
    # Send success response
    success_embed = hikari.Embed(
        title="✅ Recruitment Post Updated",
        description=f"Your recruitment data has been saved!",
        color=0x2ECC71
    )
    
    if messages_updated > 0:
        success_embed.add_field(
            name="Messages Updated",
            value=f"Updated {messages_updated} existing recruitment post(s)",
            inline=False
        )
    else:
        success_embed.add_field(
            name="No Messages Found",
            value="No existing recruitment posts found to update. Use `/post-clan` to create a new one.",
            inline=False
        )
    
    await interaction.edit_initial_response(embed=success_embed)
    
    # Clean up
    if user_id in modal_handlers:
        del modal_handlers[user_id]


async def update_recruitment_message(
    bot: hikari.GatewayBot,
    message: hikari.Message,
    clan: coc.Clan,
    clan_tag_clean: str,
    recruitment_message: str,
    image_url: str,
    discord_link: str,
    user: hikari.User
) -> None:
    """Update an existing recruitment message with new data"""
    # Calculate capital hall level
    if clan and clan.capital_districts:
        peak = max(d.hall_level for d in clan.capital_districts)
    else:
        peak = 0
    
    # Use the clan's share link if available
    clan_link = clan.share_link if hasattr(clan, 'share_link') and clan.share_link else f"https://link.clashofclans.com/en?action=OpenClanProfile&tag={clan_tag_clean}"
    
    # Build components (same as in post_clan)
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
    
    # Add footer with updated timestamp
    container.add_component(
        Text(content=f"\n-# Posted by {user.mention} • <t:{int(datetime.now(UTC).timestamp())}:f> (edited)")
    )
    
    components.append(container)
    
    # Update the message
    await bot.rest.edit_message(
        channel=message.channel_id,
        message=message.id,
        components=components
    )