"""
Script to delete auto-recruit commands from Discord
Run this when changing guild IDs or removing commands
"""

import os
import asyncio
import hikari
from dotenv import load_dotenv

load_dotenv()

async def delete_auto_recruit_commands():
    """Delete auto-recruit commands from global and guild scope"""
    # Create a simple bot instance just for REST operations
    bot = hikari.GatewayBot(token=os.getenv("DISCORD_TOKEN"))
    
    async with bot.rest as client:
        # Get the application
        app = await client.fetch_application()
        
        # Commands to delete
        commands_to_delete = [
            "auto-recruit-enable",
            "auto-recruit-disable", 
            "auto-recruit-status"
        ]
        
        # Delete global commands
        print("Checking for global commands...")
        commands = await client.fetch_application_commands(app.id)
        
        deleted_count = 0
        for command in commands:
            if command.name in commands_to_delete:
                print(f"Deleting global command: {command.name}")
                await client.delete_application_command(app.id, command.id)
                deleted_count += 1
        
        if deleted_count > 0:
            print(f"Deleted {deleted_count} global commands")
        else:
            print("No global auto-recruit commands found")
        
        # Check for OLD_GUILD_ID environment variable
        old_guild_id = os.getenv("OLD_GUILD_ID")
        if old_guild_id:
            print(f"\nChecking guild {old_guild_id} for commands...")
            try:
                guild_commands = await client.fetch_application_commands(app.id, guild=int(old_guild_id))
                guild_deleted = 0
                
                for command in guild_commands:
                    if command.name in commands_to_delete:
                        print(f"Deleting guild command: {command.name}")
                        await client.delete_application_command(app.id, command.id, guild=int(old_guild_id))
                        guild_deleted += 1
                
                if guild_deleted > 0:
                    print(f"Deleted {guild_deleted} commands from guild {old_guild_id}")
                else:
                    print(f"No auto-recruit commands found in guild {old_guild_id}")
                    
            except Exception as e:
                print(f"Error accessing guild {old_guild_id}: {e}")
        
        # Show next steps
        guild_id = os.getenv("AUTO_RECRUIT_GUILD_ID")
        if guild_id:
            print(f"\n✅ Auto-recruit commands will be registered to guild {guild_id} when you restart the bot")
        else:
            print("\n⚠️  No AUTO_RECRUIT_GUILD_ID set - commands will be global")
            
        print("\nNext steps:")
        print("1. If changing guilds, set OLD_GUILD_ID in .env to the previous guild ID")
        print("2. Update AUTO_RECRUIT_GUILD_ID to the new guild ID")
        print("3. Restart your bot")

if __name__ == "__main__":
    asyncio.run(delete_auto_recruit_commands())