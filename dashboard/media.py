"""Images in the WU R2 bucket: list the ones the post editor can pick, and upload new ones.

Same bucket and rules as the WU bot (its utils/media_store.py): keys are
`<folder>/<name>.<sha256[:10]>.<ext>`, stored with a one-year immutable cache
header, so a changed image always gets a new URL. Jo Nation uploads go under
`jo-nation/recruit/`. The picker lists `clans/` (WU clan logos and banners)
and `jo-nation/`.

Settings (.env, same names as WU): R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL. Without them the picker
says images are not set up and the rest of the dashboard works as before.
"""

import asyncio
import hashlib
import logging
import os
import re
import time
import warnings
from io import BytesIO
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
LIST_PREFIXES = ("clans/", "jo-nation/")
UPLOAD_FOLDER = "jo-nation/recruit"
CACHE_CONTROL = "public, max-age=31536000, immutable"
LIST_SECONDS = 300
FORMATS = {
    "PNG": ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "MPO": ("jpg", "image/jpeg"),
    "GIF": ("gif", "image/gif"),
    "WEBP": ("webp", "image/webp"),
}
log = logging.getLogger("dashboard.media")
IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|webp)$", re.IGNORECASE)
ENV = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE_URL")


class MediaError(Exception):
    """A problem worded for the person using the dashboard."""


def detect_image(data: bytes) -> tuple[str, str]:
    """(extension, content type) of real image bytes, else MediaError."""
    if not data:
        raise MediaError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise MediaError("Images must be under 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                fmt = image.format
                if image.size[0] * image.size[1] > MAX_PIXELS:
                    raise MediaError("That image is too large.")
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise MediaError("That file is not an image. Use PNG, JPG, GIF or WEBP.") from exc
    if fmt not in FORMATS:
        raise MediaError("Use PNG, JPG, GIF or WEBP.")
    return FORMATS[fmt]


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")
    return cleaned[:60] or "image"


class MediaStore:
    def __init__(self, client=None):
        values = {name: os.getenv(name, "").strip() for name in ENV}
        self.configured = all(values.values()) or client is not None
        self.bucket = values["R2_BUCKET"]
        self.base_url = values["R2_PUBLIC_BASE_URL"].rstrip("/")
        self._values = values
        self._client = client  # tests pass a fake
        self._listing = None  # (expires_at, images)

    def _s3(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=f"https://{self._values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                aws_access_key_id=self._values["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=self._values["R2_SECRET_ACCESS_KEY"],
                region_name="auto",
                # R2 does not accept the newer default checksum headers (same as WU).
                config=Config(request_checksum_calculation="when_required",
                              response_checksum_validation="when_required"),
            )
        return self._client

    def public_url(self, key: str) -> str:
        return f"{self.base_url}/{quote(key)}"

    def _list_blocking(self) -> list[dict]:
        images = []
        for prefix in LIST_PREFIXES:
            token = None
            while True:
                page = self._s3().list_objects_v2(
                    Bucket=self.bucket, Prefix=prefix, MaxKeys=1000,
                    **({"ContinuationToken": token} if token else {}),
                )
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not IMAGE_EXT.search(key):
                        continue
                    folder, _, name = key.rpartition("/")
                    modified = obj.get("LastModified")
                    images.append({
                        "key": key,
                        "url": self.public_url(key),
                        "folder": folder,
                        "name": name,
                        "modified": modified.isoformat() if modified else None,
                    })
                if not page.get("IsTruncated"):
                    break
                token = page.get("NextContinuationToken")
        images.sort(key=lambda i: i["modified"] or "", reverse=True)
        return images

    async def list_images(self) -> list[dict]:
        if not self.configured:
            raise MediaError("Image storage isn't set up yet. Add the R2 keys to .env.")
        if self._listing and self._listing[0] > time.time():
            return self._listing[1]
        try:
            images = await asyncio.to_thread(self._list_blocking)
        except Exception as exc:
            log.exception("Listing R2 images failed")
            code = getattr(exc, "response", {}).get("Error", {}).get("Code") if isinstance(getattr(exc, "response", None), dict) else None
            raise MediaError(f"Couldn't load images from R2{f' ({code})' if code else ''}.") from exc
        self._listing = (time.time() + LIST_SECONDS, images)
        return images

    async def upload(self, data: bytes, name: str) -> str:
        if not self.configured:
            raise MediaError("Image storage isn't set up yet. Add the R2 keys to .env.")
        ext, content_type = detect_image(data)
        key = f"{UPLOAD_FOLDER}/{slug(name)}.{hashlib.sha256(data).hexdigest()[:10]}.{ext}"
        try:
            await asyncio.to_thread(
                self._s3().put_object, Bucket=self.bucket, Key=key, Body=data,
                ContentType=content_type, CacheControl=CACHE_CONTROL,
            )
        except Exception as exc:
            raise MediaError("Upload to R2 failed. Try again.") from exc
        self._listing = None  # show the new image in the library right away
        return self.public_url(key)
