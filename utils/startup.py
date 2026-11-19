import asyncio
import os

import coc


def load_cogs(disallowed: set, disallowed_folders: set = None):
    if disallowed_folders is None:
        disallowed_folders = set()

    file_list = []

    for root, _, files in os.walk("extensions/commands"):
        # Check if any part of the current path is a disallowed folder
        path_parts = root.replace("\\", "/").split("/")
        if any(folder in disallowed_folders for folder in path_parts):
            continue  # Skip this entire directory

        for filename in files:
            if not filename.endswith(".py") or filename.startswith("__"):
                continue

            full_path = os.path.join(root, filename)
            module_path = full_path.replace("\\", ".").replace("/", ".").replace(".py", "")

            # Check if the filename (without .py) is in disallowed
            if module_path.split(".")[-1] in disallowed:
                continue

            file_list.append(module_path)

    return file_list


def create_clash_client(*, loop: asyncio.AbstractEventLoop | None = None) -> coc.Client:
    """Create the coc.py client for the official Clash of Clans API (same setup as the WU bot)."""
    active_loop = loop or asyncio.get_running_loop()
    return coc.Client(
        loop=active_loop,
        base_url="https://api.clashofclans.com/v1",
        load_game_data=coc.LoadGameData(default=False),
        raw_attribute=True,
    )


async def create_authenticated_clash_client(
    api_token: str, *, loop: asyncio.AbstractEventLoop | None = None
) -> coc.Client:
    """Create the official API client and log in with COC_API_TOKEN before the bot finishes starting."""
    token = (api_token or "").strip()
    if not token:
        raise RuntimeError("COC_API_TOKEN is required for the official Clash API. Add it to .env.")

    client = create_clash_client(loop=loop)
    await client.login_with_tokens(token)
    return client
