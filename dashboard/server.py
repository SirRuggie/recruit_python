"""Jo Nation scheduled posts dashboard.

A small aiohttp web app that lists, edits, adds and deletes the scheduled
recruitment posts in MongoDB `settings.auto_recruit`. The bot re-reads that
collection every minute (extensions/scheduler/auto_recruit.py), so the dashboard
never talks to the bot directly.

Login is "Sign in with Discord". Only Discord IDs in DASHBOARD_ALLOWED_IDS get in.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
from aiohttp import web
from bson import ObjectId

from dashboard.media import MediaError, MediaStore

log = logging.getLogger("dashboard")

STATIC_DIR = Path(__file__).parent / "static"
DISCORD_API = "https://discord.com/api/v10"
CLASH_API = "https://api.clashofclans.com/v1"
SESSION_COOKIE = "jn_session"
STATE_COOKIE = "jn_oauth_state"
SESSION_SECONDS = 30 * 24 * 3600
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TAG_RE = re.compile(r"^#[0289PYLQGRJCUV]{3,12}$")
ID_RE = re.compile(r"^\d{15,22}$")
DEFAULT_TZ = "America/New_York"
CONTENT_FIELDS = ("description", "image_url", "discord_link")


# ---------- settings ----------

def load_config() -> dict:
    allowed = {x.strip() for x in os.getenv("DASHBOARD_ALLOWED_IDS", "").split(",") if x.strip()}
    return {
        "public_url": os.getenv("DASHBOARD_PUBLIC_URL", "http://127.0.0.1:8790").rstrip("/"),
        "client_id": os.getenv("DISCORD_CLIENT_ID", ""),
        "client_secret": os.getenv("DISCORD_CLIENT_SECRET", ""),
        "secret": os.getenv("DASHBOARD_SECRET", ""),
        "allowed_ids": allowed,
        "bot_token": os.getenv("DISCORD_TOKEN", ""),
        "coc_token": os.getenv("COC_API_TOKEN", ""),
        "default_channel": os.getenv("RECRUITMENT_CHANNEL_ID") or "1144471630614114454",
        # Local testing only: skips Discord and logs in as the first allowed ID.
        "dev_login": os.getenv("DASHBOARD_DEV_LOGIN") == "1",
    }


# ---------- signed session cookie ----------

def _sign(secret: str, payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def _unsign(secret: str, value: str) -> dict | None:
    body, _, mac = value.partition(".")
    good = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not body or not hmac.compare_digest(mac, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
    except ValueError:
        return None
    return data if data.get("exp", 0) > time.time() else None


def current_user(request) -> dict | None:
    cfg = request.app["cfg"]
    data = _unsign(cfg["secret"], request.cookies.get(SESSION_COOKIE, ""))
    # Re-check the allowlist on every request so removing an ID takes effect at once.
    if data and data.get("id") in cfg["allowed_ids"]:
        return data
    return None


def require_user(request) -> dict:
    user = current_user(request)
    if not user:
        raise web.HTTPUnauthorized(text=json.dumps({"error": "Sign in again."}), content_type="application/json")
    if request.method not in ("GET", "HEAD") and not hmac.compare_digest(
        request.headers.get("X-CSRF-Token", ""), user["csrf"]
    ):
        raise web.HTTPForbidden(text=json.dumps({"error": "Reload the page and try again."}), content_type="application/json")
    return user


def set_session(request, response, user: dict) -> None:
    cfg = request.app["cfg"]
    payload = dict(user, csrf=secrets.token_urlsafe(24), exp=int(time.time()) + SESSION_SECONDS)
    response.set_cookie(
        SESSION_COOKIE, _sign(cfg["secret"], payload), max_age=SESSION_SECONDS,
        httponly=True, secure=cfg["public_url"].startswith("https"), samesite="Lax", path="/",
    )


# ---------- login routes ----------

async def login(request):
    cfg = request.app["cfg"]
    if cfg["dev_login"]:
        uid = sorted(cfg["allowed_ids"])[0]
        response = web.HTTPFound("/")
        set_session(request, response, {"id": uid, "name": "Dev user", "avatar": None})
        raise response
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["public_url"] + "/auth/callback",
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "none",
    }
    response = web.HTTPFound("https://discord.com/oauth2/authorize?" + urlencode(params, quote_via=quote))
    response.set_cookie(STATE_COOKIE, state, max_age=300, httponly=True,
                        secure=cfg["public_url"].startswith("https"), samesite="Lax", path="/auth")
    raise response


async def callback(request):
    cfg = request.app["cfg"]
    state = request.query.get("state", "")
    if not state or not hmac.compare_digest(state, request.cookies.get(STATE_COOKIE, "")):
        raise web.HTTPFound("/?login=expired")
    code = request.query.get("code")
    if not code:
        raise web.HTTPFound("/?login=cancelled")
    http = request.app["http"]
    data = {
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": cfg["public_url"] + "/auth/callback",
    }
    async with http.post(f"{DISCORD_API}/oauth2/token", data=data) as resp:
        if resp.status != 200:
            log.warning("Discord token exchange failed: %s", resp.status)
            raise web.HTTPFound("/?login=failed")
        token = (await resp.json())["access_token"]
    async with http.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {token}"}) as resp:
        if resp.status != 200:
            raise web.HTTPFound("/?login=failed")
        me = await resp.json()
    uid = str(me["id"])
    if uid not in cfg["allowed_ids"]:
        log.warning("Login refused for Discord ID %s", uid)
        raise web.HTTPFound(f"/?login=denied&id={uid}")
    response = web.HTTPFound("/")
    set_session(request, response, {
        "id": uid,
        "name": me.get("global_name") or me.get("username"),
        "avatar": _avatar_url(uid, me.get("avatar")),
    })
    response.del_cookie(STATE_COOKIE, path="/auth")
    raise response


async def logout(request):
    require_user(request)
    response = web.json_response({"ok": True})
    response.del_cookie(SESSION_COOKIE, path="/")
    return response


async def me(request):
    user = current_user(request)
    if not user:
        return web.json_response({"user": None})
    return web.json_response({"user": {k: user[k] for k in ("id", "name", "avatar")}, "csrf": user["csrf"]})


# ---------- Discord and Clash lookups (cached) ----------

def _avatar_url(uid: str, avatar_hash: str | None) -> str | None:
    if not avatar_hash:
        return None
    return f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png?size=64"


async def _cached(request, key: str, seconds: int, fetch):
    cache = request.app["cache"]
    hit = cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        value = await fetch()
    except (aiohttp.ClientError, TimeoutError) as exc:
        log.warning("Lookup %s failed: %s", key, exc)
        value = None
    # Remember failures for a short time only.
    cache[key] = (time.time() + (seconds if value is not None else 60), value)
    return value


async def discord_user(request, uid: str) -> dict | None:
    async def fetch():
        headers = {"Authorization": f"Bot {request.app['cfg']['bot_token']}"}
        async with request.app["http"].get(f"{DISCORD_API}/users/{uid}", headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return {"name": data.get("global_name") or data.get("username"),
                    "username": data.get("username"), "avatar": _avatar_url(uid, data.get("avatar"))}
    return await _cached(request, f"user:{uid}", 3600, fetch)


async def discord_channel(request, cid: str) -> dict | None:
    async def fetch():
        headers = {"Authorization": f"Bot {request.app['cfg']['bot_token']}"}
        async with request.app["http"].get(f"{DISCORD_API}/channels/{cid}", headers=headers) as resp:
            if resp.status != 200:
                return None
            return {"name": (await resp.json()).get("name")}
    return await _cached(request, f"channel:{cid}", 3600, fetch)


async def clash_clan(request, tag: str) -> dict | None:
    """Returns clan info, {"missing": True} if the tag does not exist, or None if the API is down."""
    async def fetch():
        headers = {"Authorization": f"Bearer {request.app['cfg']['coc_token']}"}
        url = f"{CLASH_API}/clans/{quote(tag, safe='')}"
        async with request.app["http"].get(url, headers=headers) as resp:
            if resp.status == 404:
                return {"missing": True}
            if resp.status != 200:
                log.warning("Clash API %s for %s", resp.status, tag)
                return None
            data = await resp.json()
            return {"name": data.get("name"), "badge": (data.get("badgeUrls") or {}).get("medium"),
                    "members": data.get("members"), "level": data.get("clanLevel")}
    return await _cached(request, f"clan:{tag}", 600, fetch)


# ---------- helpers ----------

def _doc_filter(doc_id: str) -> dict:
    # The bot accepts both ObjectId and string IDs, so the dashboard does too.
    return {"_id": ObjectId(doc_id)} if ObjectId.is_valid(doc_id) else {"_id": doc_id}


def _times(doc: dict) -> list[str]:
    times = doc.get("post_times") or [doc.get("post_time") or "14:00"]
    return sorted({t for t in times if isinstance(t, str) and TIME_RE.match(t)})


def next_sends(times: list[str], tz_name: str, now: datetime | None = None) -> list[str]:
    """UTC ISO time of the next send for each HH:MM, in the post's own timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(DEFAULT_TZ)
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(tz)
    result = []
    for t in times:
        hour, minute = map(int, t.split(":"))
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate = (local_now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        result.append(candidate.astimezone(timezone.utc).isoformat())
    return result


def _iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


async def serialize_post(request, doc: dict, template: dict | None) -> dict:
    discord_id = str(doc.get("discord_id") or "")
    clan_tag = doc.get("clan_tag") or (template or {}).get("clan_tag")
    channel_id = str(doc.get("channel_id") or request.app["cfg"]["default_channel"])
    times = _times(doc)
    tz_name = doc.get("timezone") or DEFAULT_TZ
    saved = {f: (template or {}).get(f) or "" for f in CONTENT_FIELDS}
    own = {f: doc[f] for f in CONTENT_FIELDS if doc.get(f) is not None}
    return {
        "id": str(doc["_id"]),
        "rev": int(doc.get("dash_rev") or 0),
        "discord_id": discord_id,
        "user": await discord_user(request, discord_id) if discord_id else None,
        "clan_tag": clan_tag,
        "clan": await clash_clan(request, clan_tag) if clan_tag else None,
        "channel_id": channel_id,
        "channel": await discord_channel(request, channel_id),
        "times": times,
        "timezone": tz_name,
        "next_sends": next_sends(times, tz_name),
        "enabled": bool(doc.get("enabled")),
        "error": doc.get("error"),
        "last_posted": _iso(doc.get("last_posted")),
        "has_template": template is not None,
        # What the post will say: this post's own text if set, else the user's saved template.
        "content": {**saved, **own},
        "saved_content": saved,
        "custom_content": sorted(own),
    }


def _clean(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


async def validate(request, body: dict) -> dict:
    """Check the editor form. Returns the fields to store or raises 400 with a message."""
    errors = {}
    discord_id = _clean(body.get("discord_id"), 30)
    if not ID_RE.match(discord_id):
        errors["discord_id"] = "Pick who the post is from."
    clan_tag = _clean(body.get("clan_tag"), 20).upper().replace("O", "0")
    if clan_tag and not clan_tag.startswith("#"):
        clan_tag = "#" + clan_tag
    if not TAG_RE.match(clan_tag):
        errors["clan_tag"] = "Enter a clan tag like #2PYLUR2PV."
    else:
        clan = await clash_clan(request, clan_tag)
        if clan and clan.get("missing"):
            errors["clan_tag"] = "No clan has that tag."
    channel_id = _clean(body.get("channel_id"), 30) or request.app["cfg"]["default_channel"]
    if not ID_RE.match(channel_id):
        errors["channel_id"] = "Channel ID must be a number."
    times = body.get("times") or []
    if not isinstance(times, list) or not times or len(times) > 6 or not all(
        isinstance(t, str) and TIME_RE.match(t) for t in times
    ):
        errors["times"] = "Add at least one send time (up to 6)."
    tz_name = _clean(body.get("timezone"), 64) or DEFAULT_TZ
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        errors["timezone"] = "Unknown timezone."
    content = body.get("content") or {}
    fields = {
        "description": _clean(content.get("description"), 1500),
        "image_url": _clean(content.get("image_url"), 500),
        "discord_link": _clean(content.get("discord_link"), 200),
    }
    if not fields["description"]:
        errors["description"] = "The post needs a description."
    for key in ("image_url", "discord_link"):
        if fields[key] and not fields[key].startswith("https://"):
            errors[key] = "Must start with https://"
    if errors:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Check the highlighted fields.", "fields": errors}),
                                 content_type="application/json")
    times = sorted(set(times))
    return {
        "discord_id": discord_id, "clan_tag": clan_tag, "channel_id": channel_id,
        "post_times": times, "post_time": times[0], "timezone": tz_name,
        "enabled": bool(body.get("enabled", True)), "content": fields,
    }


async def _store_content(request, doc_filter: dict, fields: dict) -> None:
    """Keep text that matches the saved template unset, so later /post-edit changes still flow through."""
    mongo = request.app["mongo"]
    template = await mongo.recruit_data.find_one({"_id": fields["discord_id"]})
    saved = {f: (template or {}).get(f) or "" for f in CONTENT_FIELDS}
    to_set, to_unset = {}, {}
    for f in CONTENT_FIELDS:
        if template is not None and fields["content"][f] == saved[f]:
            to_unset[f] = ""
        else:
            to_set[f] = fields["content"][f]
    update = {"$set": to_set} if to_set else {}
    if to_unset:
        update["$unset"] = to_unset
    if update:
        await mongo.auto_recruit.update_one(doc_filter, update)
    if template is None:
        # The bot disables a post whose user has no saved template, so create one.
        await mongo.recruit_data.insert_one({
            "_id": fields["discord_id"], "clan_tag": fields["clan_tag"], **fields["content"],
            "posted_by": int(fields["discord_id"]), "created_by_dashboard": True,
        })


# ---------- post routes ----------

async def list_posts(request):
    require_user(request)
    mongo = request.app["mongo"]
    docs = await mongo.auto_recruit.find({}).to_list(None)
    ids = {str(d.get("discord_id")) for d in docs if d.get("discord_id")}
    templates = {t["_id"]: t for t in await mongo.recruit_data.find({"_id": {"$in": list(ids)}}).to_list(None)}
    posts = [await serialize_post(request, d, templates.get(str(d.get("discord_id")))) for d in docs]
    return web.json_response({"posts": posts, "default_channel": request.app["cfg"]["default_channel"]})


async def list_templates(request):
    """Saved /post-clan templates, for the "Posts as" picker when adding a post."""
    require_user(request)
    rows = await request.app["mongo"].recruit_data.find(
        {"_id": {"$regex": r"^\d+$"}}, {"clan_tag": 1, **{f: 1 for f in CONTENT_FIELDS}}
    ).to_list(500)
    out = []
    cache = request.app["cache"]
    for row in rows:
        # Names only from the cache: looking up hundreds of users would hit Discord's rate limit.
        hit = cache.get(f"user:{row['_id']}")
        user = hit[1] if hit and hit[0] > time.time() else None
        out.append({"discord_id": row["_id"], "user": user, "clan_tag": row.get("clan_tag"),
                    "content": {f: row.get(f) or "" for f in CONTENT_FIELDS}})
    out.sort(key=lambda r: ((r["user"] or {}).get("name") or r["discord_id"]).lower())
    return web.json_response({"templates": out})


async def clan_lookup(request):
    require_user(request)
    tag = request.match_info["tag"].upper().replace("O", "0")
    tag = tag if tag.startswith("#") else "#" + tag
    if not TAG_RE.match(tag):
        return web.json_response({"clan": None, "tag": tag})
    return web.json_response({"clan": await clash_clan(request, tag), "tag": tag})


async def create_post(request):
    require_user(request)
    fields = await validate(request, await _json(request))
    doc = {k: fields[k] for k in ("discord_id", "clan_tag", "channel_id", "post_times", "post_time", "timezone", "enabled")}
    doc.update(last_posted=None, last_message_id=None, error=None, dash_rev=1,
               created_by_dashboard=datetime.now(timezone.utc))
    result = await request.app["mongo"].auto_recruit.insert_one(doc)
    await _store_content(request, {"_id": result.inserted_id}, fields)
    return await _one(request, result.inserted_id, status=201)


async def update_post(request):
    require_user(request)
    body = await _json(request)
    fields = await validate(request, body)
    doc_filter = _doc_filter(request.match_info["id"])
    rev = int(body.get("rev") or 0)
    # Only save if nobody else saved since this editor opened it.
    rev_match = {"dash_rev": rev} if rev else {"dash_rev": {"$exists": False}}
    to_set = {k: fields[k] for k in ("discord_id", "clan_tag", "channel_id", "post_times", "post_time", "timezone", "enabled")}
    if to_set["enabled"]:
        to_set["error"] = None  # Turning a post back on clears the old error.
    result = await request.app["mongo"].auto_recruit.update_one(
        {**doc_filter, **rev_match}, {"$set": to_set, "$inc": {"dash_rev": 1}}
    )
    if result.matched_count == 0:
        exists = await request.app["mongo"].auto_recruit.find_one(doc_filter, {"_id": 1})
        if not exists:
            raise web.HTTPNotFound(text=json.dumps({"error": "This post was deleted."}), content_type="application/json")
        raise web.HTTPConflict(text=json.dumps({"error": "This post changed somewhere else. Reload to see it."}),
                               content_type="application/json")
    await _store_content(request, doc_filter, fields)
    return await _one(request, doc_filter["_id"])


async def toggle_post(request):
    """Pause or resume from the card without opening the editor."""
    require_user(request)
    body = await _json(request)
    enabled = bool(body.get("enabled"))
    to_set = {"enabled": enabled}
    if enabled:
        to_set["error"] = None
    doc_filter = _doc_filter(request.match_info["id"])
    result = await request.app["mongo"].auto_recruit.update_one(doc_filter, {"$set": to_set, "$inc": {"dash_rev": 1}})
    if result.matched_count == 0:
        raise web.HTTPNotFound(text=json.dumps({"error": "This post was deleted."}), content_type="application/json")
    return await _one(request, doc_filter["_id"])


async def delete_post(request):
    require_user(request)
    result = await request.app["mongo"].auto_recruit.delete_one(_doc_filter(request.match_info["id"]))
    return web.json_response({"deleted": result.deleted_count})


async def _one(request, doc_id, status=200):
    mongo = request.app["mongo"]
    doc = await mongo.auto_recruit.find_one({"_id": doc_id})
    template = await mongo.recruit_data.find_one({"_id": str(doc.get("discord_id"))})
    return web.json_response({"post": await serialize_post(request, doc, template)}, status=status)


async def _json(request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text=json.dumps({"error": "Bad request."}), content_type="application/json")
    return body


# ---------- image routes ----------

async def list_images(request):
    require_user(request)
    try:
        images = await request.app["media"].list_images()
    except MediaError as exc:
        return web.json_response({"error": str(exc), "images": []}, status=503)
    return web.json_response({"images": images})


async def upload_image(request):
    require_user(request)
    try:
        form = await request.post()
    except ValueError:
        raise web.HTTPRequestEntityTooLarge(max_size=11 * 1024 * 1024, actual_size=request.content_length or 0,
                                            text=json.dumps({"error": "Images must be under 10 MB."}),
                                            content_type="application/json")
    upload = form.get("file")
    if not hasattr(upload, "file"):
        raise web.HTTPBadRequest(text=json.dumps({"error": "Pick an image file."}), content_type="application/json")
    data = upload.file.read(11 * 1024 * 1024)
    try:
        url = await request.app["media"].upload(data, str(form.get("name") or ""))
    except MediaError as exc:
        raise web.HTTPBadRequest(text=json.dumps({"error": str(exc)}), content_type="application/json")
    return web.json_response({"url": url}, status=201)


# ---------- app ----------

@web.middleware
async def security_headers(request, handler):
    response = await handler(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data: blob:; style-src 'self'; style-src-attr 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'",
    )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.path.startswith("/static/") and not request.path.endswith(".woff2"):
        # Make browsers and Cloudflare check for a new version, so updates show up at once.
        response.headers["Cache-Control"] = "no-cache"
    return response


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def create_app(mongo, cfg: dict | None = None, media: MediaStore | None = None) -> web.Application:
    cfg = cfg or load_config()
    if not cfg["secret"] or len(cfg["secret"]) < 32:
        raise SystemExit("DASHBOARD_SECRET must be set to a random string of 32+ characters.")
    if not cfg["allowed_ids"]:
        raise SystemExit("DASHBOARD_ALLOWED_IDS must list at least one Discord user ID.")
    if not cfg["dev_login"] and not (cfg["client_id"] and cfg["client_secret"]):
        raise SystemExit("DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET are required for Discord login.")

    app = web.Application(middlewares=[security_headers], client_max_size=11 * 1024 * 1024)
    app["cfg"] = cfg
    app["mongo"] = mongo
    app["cache"] = {}
    app["media"] = media or MediaStore()

    async def http_session(app):
        app["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        yield
        await app["http"].close()

    app.cleanup_ctx.append(http_session)
    app.router.add_get("/", index)
    app.router.add_get("/auth/login", login)
    app.router.add_get("/auth/callback", callback)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/posts", list_posts)
    app.router.add_post("/api/posts", create_post)
    app.router.add_put("/api/posts/{id}", update_post)
    app.router.add_post("/api/posts/{id}/enabled", toggle_post)
    app.router.add_delete("/api/posts/{id}", delete_post)
    app.router.add_get("/api/templates", list_templates)
    app.router.add_get("/api/clans/{tag}", clan_lookup)
    app.router.add_get("/api/images", list_images)
    app.router.add_post("/api/images", upload_image)
    app.router.add_static("/static/", STATIC_DIR)
    return app
