"""Start the dashboard: python -m dashboard (reads the bot's .env)."""

import logging
import os

from aiohttp import web
from dotenv import load_dotenv

from dashboard.server import create_app, load_config
from utils.mongo import MongoClient


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    if cfg["dev_login"] and host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("DASHBOARD_DEV_LOGIN only works on 127.0.0.1.")
    mongo = MongoClient(uri=os.getenv("MONGODB_URI"))
    web.run_app(create_app(mongo, cfg), host=host, port=int(os.getenv("DASHBOARD_PORT", "8790")), access_log=None)


if __name__ == "__main__":
    main()
