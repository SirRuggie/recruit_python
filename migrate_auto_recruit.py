"""
Migration script to update auto_recruit documents with discord_id field
"""

import os
import asyncio
from pymongo import AsyncMongoClient
from dotenv import load_dotenv

load_dotenv()

async def migrate_auto_recruit():
    """Update auto_recruit documents to have discord_id field"""
    
    # Connect to MongoDB
    client = AsyncMongoClient(os.getenv("MONGODB_URI"))
    db = client.get_database("settings")
    
    try:
        # Update the specific document that's missing discord_id
        # This assumes there's only one document and it belongs to user 505227988229554179
        result = await db.get_collection("auto_recruit").update_one(
            {"discord_id": {"$exists": False}},  # Find document without discord_id
            {"$set": {"discord_id": "505227988229554179"}}  # Add discord_id
        )
        
        if result.modified_count > 0:
            print(f"Successfully added discord_id to {result.modified_count} document(s)")
        else:
            print("No documents needed updating (discord_id already exists)")
        
        # Show all documents after update
        print("\nCurrent documents in auto_recruit collection:")
        cursor = db.get_collection("auto_recruit").find({})
        documents = await cursor.to_list(None)
        
        for doc in documents:
            print(f"\nDocument ID: {doc['_id']}")
            print(f"Discord ID: {doc.get('discord_id', 'NOT SET')}")
            print(f"Clan Tag: {doc.get('clan_tag', 'NOT SET')}")
            print(f"Enabled: {doc.get('enabled', False)}")
            print(f"Post Time: {doc.get('post_time', 'NOT SET')}")
        
    finally:
        # No need to close AsyncMongoClient
        pass

if __name__ == "__main__":
    asyncio.run(migrate_auto_recruit())