import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import os
import hikari
import lightbulb
from dotenv import load_dotenv
from utils.mongo import MongoClient
import coc
from utils.startup import load_cogs
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
clash_client = coc.Client(
    base_url='https://proxy.clashk.ing/v1',
    key_count=10,
    load_game_data=coc.LoadGameData(default=False),
    raw_attribute=True,
)

cloudinary_client = CloudinaryClient()

bot_data.data["mongo"] = mongo_client
bot_data.data["cloudinary_client"] = cloudinary_client
bot_data.data["bot"] = bot
bot_data.data["coc_client"] = clash_client

registry = client.di.registry_for(lightbulb.di.Contexts.DEFAULT)
registry.register_value(MongoClient, mongo_client)
registry.register_value(coc.Client, clash_client)
registry.register_value(CloudinaryClient, cloudinary_client)
registry.register_value(hikari.GatewayBot, bot)

@bot.listen(hikari.StartingEvent)
async def on_starting(_: hikari.StartingEvent) -> None:
    """Bot starting event"""
    all_extensions = [
        "extensions.commands.post_clan",
        "extensions.commands.post_edit",
        "extensions.scheduler.auto_recruit",  # Keep scheduler, remove commands
    ] + load_cogs(disallowed={"example", "post_clan", "post_edit"})

    await client.load_extensions(*all_extensions)
    await client.start()
    await clash_client.login_with_tokens("")


@bot.listen(hikari.StoppingEvent)
async def on_stopping(_: hikari.StoppingEvent) -> None:
    """Bot stopping event"""
    # Properly close the coc.py client to avoid unclosed session warnings
    await clash_client.close()

bot.run()