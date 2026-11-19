import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import asyncio
import os
import hikari
import lightbulb
from dotenv import load_dotenv
from utils.mongo import MongoClient
import coc
from utils.startup import load_cogs, create_authenticated_clash_client
from utils.cloudinary_client import CloudinaryClient
from utils import bot_data

load_dotenv()

# Create a GatewayBot instance with intents
bot = hikari.GatewayBot(
    token=os.getenv("DISCORD_TOKEN"),
    intents=(
        hikari.Intents.GUILD_MESSAGES
        | hikari.Intents.MESSAGE_CONTENT
        | hikari.Intents.GUILDS
        | hikari.Intents.GUILD_MEMBERS
        | hikari.Intents.GUILD_MODERATION
        | hikari.Intents.GUILD_MESSAGE_REACTIONS
    ),
)

client = lightbulb.client_from_app(bot)

mongo_client = MongoClient(uri=os.getenv("MONGODB_URI"))
# The Clash API client is built in on_starting, once the bot's event loop is running
clash_client: coc.Client | None = None

cloudinary_client = CloudinaryClient()

bot_data.data["mongo"] = mongo_client
bot_data.data["cloudinary_client"] = cloudinary_client
bot_data.data["bot"] = bot

registry = client.di.registry_for(lightbulb.di.Contexts.DEFAULT)
registry.register_value(MongoClient, mongo_client)
registry.register_value(CloudinaryClient, cloudinary_client)
registry.register_value(hikari.GatewayBot, bot)

@bot.listen(hikari.StartingEvent)
async def on_starting(_: hikari.StartingEvent) -> None:
    """Bot starting event"""
    global clash_client

    # Official Clash of Clans API, set up the same way as the WU bot.
    # COC_API_TOKEN comes from developer.clashofclans.com and is locked to the host's IP.
    clash_client = await create_authenticated_clash_client(
        os.getenv("COC_API_TOKEN", ""), loop=asyncio.get_running_loop()
    )
    bot_data.data["coc_client"] = clash_client
    registry.register_value(coc.Client, clash_client)

    all_extensions = [
        "extensions.commands.post_clan",
        "extensions.commands.post_edit",
        "extensions.scheduler.auto_recruit",  # Keep scheduler, remove commands
        "extensions.events.message_delete",  # Auto-delete messages in recruitment channel
    ] + load_cogs(disallowed={"example", "post_clan", "post_edit"})

    await client.load_extensions(*all_extensions)
    await client.start()


@bot.listen(hikari.StoppingEvent)
async def on_stopping(_: hikari.StoppingEvent) -> None:
    """Bot stopping event"""
    # Properly close the coc.py client to avoid unclosed session warnings
    if clash_client is not None and clash_client.http is not None:
        await clash_client.close()

bot.run()