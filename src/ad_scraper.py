import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse

import aiohttp
import discord


DISCORD_HOSTS = {
    "discord.com",
    "www.discord.com",
    "ptb.discord.com",
    "canary.discord.com",
}
DISCORD_CHANNEL_PATH_RE = re.compile(r"^/channels/(?P<guild_id>\d+)/(?P<channel_id>\d+)/?$")
HTTP_URL_RE = re.compile(r"https?://[^\s<>()]+")
INVALID_FOLDER_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}


@dataclass
class ChannelTarget:
    guild_id: int
    channel_id: int


@dataclass
class ScrapedAd:
    title: str
    link: str
    image_urls: List[str]
    source_channel_url: str = ""
    source_message_url: str = ""
    output_dir: str = ""
    image_paths: List[str] = field(default_factory=list)


@dataclass
class CrawlSummary:
    channel_name: str
    output_root: str
    ads: List[ScrapedAd]
    skipped_count: int = 0


def parse_discord_channel_url(url: str) -> ChannelTarget:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in DISCORD_HOSTS:
        raise ValueError("请输入有效的 Discord 频道链接")

    match = DISCORD_CHANNEL_PATH_RE.match(parsed.path)
    if not match:
        raise ValueError("Discord 链接格式不正确，应为 /channels/<guild>/<channel>")

    return ChannelTarget(
        guild_id=int(match.group("guild_id")),
        channel_id=int(match.group("channel_id")),
    )


def sanitize_folder_name(title: str) -> str:
    cleaned = INVALID_FOLDER_CHARS_RE.sub("_", title.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return cleaned or "untitled"


def extract_first_external_url(text: str, embeds: Optional[List] = None) -> str:
    if text:
        match = HTTP_URL_RE.search(text)
        if match:
            return match.group(0)

    for embed in embeds or []:
        embed_url = getattr(embed, "url", None)
        if embed_url and str(embed_url).startswith(("http://", "https://")):
            return str(embed_url)

    return ""


def _attachment_looks_like_image(attachment) -> bool:
    content_type = getattr(attachment, "content_type", None) or ""
    if content_type.startswith("image/"):
        return True

    filename = getattr(attachment, "filename", "") or ""
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def extract_image_urls(message) -> List[str]:
    image_urls: List[str] = []

    for attachment in getattr(message, "attachments", []) or []:
        attachment_url = getattr(attachment, "url", None)
        if attachment_url and _attachment_looks_like_image(attachment):
            image_urls.append(str(attachment_url))

    for embed in getattr(message, "embeds", []) or []:
        for attr_name in ("image", "thumbnail"):
            media = getattr(embed, attr_name, None)
            media_url = getattr(media, "url", None) if media else None
            if media_url:
                image_urls.append(str(media_url))

    deduped_urls: List[str] = []
    seen = set()
    for url in image_urls:
        if url not in seen:
            seen.add(url)
            deduped_urls.append(url)

    return deduped_urls


def extract_ad_record(
    title: str,
    message,
    source_channel_url: str = "",
    source_message_url: str = "",
) -> ScrapedAd:
    normalized_title = (title or "").strip()
    if not normalized_title:
        normalized_title = "untitled"

    return ScrapedAd(
        title=normalized_title,
        link=extract_first_external_url(
            getattr(message, "content", ""),
            getattr(message, "embeds", []) or [],
        ),
        image_urls=extract_image_urls(message),
        source_channel_url=source_channel_url,
        source_message_url=source_message_url,
    )


def get_unique_output_dir(root_dir: str, title: str) -> str:
    base_name = sanitize_folder_name(title)
    target_path = Path(root_dir) / base_name
    if not target_path.exists():
        return str(target_path)

    index = 2
    while True:
        candidate = Path(root_dir) / f"{base_name}_{index}"
        if not candidate.exists():
            return str(candidate)
        index += 1


def write_metadata_file(output_dir: str, ad: ScrapedAd) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "广告信息.txt"
    lines = [
        f"标题: {ad.title}",
        f"商品链接: {ad.link or '无'}",
        f"来源频道: {ad.source_channel_url or '无'}",
        f"来源消息: {ad.source_message_url or '无'}",
        f"图片数量: {len(ad.image_urls)}",
    ]
    metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(metadata_path)


def _suffix_from_url(image_url: str) -> str:
    path = urlparse(image_url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in IMAGE_EXTENSIONS else ".jpg"


async def _download_image(
    session: aiohttp.ClientSession,
    image_url: str,
    output_dir: str,
    index: int,
) -> str:
    suffix = _suffix_from_url(image_url)
    output_path = Path(output_dir) / f"image_{index:02d}{suffix}"

    async with session.get(image_url) as response:
        response.raise_for_status()
        output_path.write_bytes(await response.read())

    return str(output_path)


class DiscordAdCrawler:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log_callback = log_callback

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(message)

    async def crawl_channel(
        self,
        token: str,
        channel_url: str,
        output_root: str,
        include_archived: bool = True,
    ) -> CrawlSummary:
        target = parse_discord_channel_url(channel_url)
        output_root_path = Path(output_root)
        output_root_path.mkdir(parents=True, exist_ok=True)

        client = discord.Client()
        ready_event = asyncio.Event()

        @client.event
        async def on_ready():
            ready_event.set()
            username = getattr(client.user, "name", "Unknown")
            discriminator = getattr(client.user, "discriminator", "0000")
            self._log(f"已登录 Discord: {username}#{discriminator}")

        start_task = asyncio.create_task(client.start(token))

        try:
            await asyncio.wait_for(ready_event.wait(), timeout=20.0)
            channel = await client.fetch_channel(target.channel_id)
            ads = await self._crawl_from_channel(
                channel=channel,
                source_channel_url=channel_url,
                output_root=str(output_root_path),
                include_archived=include_archived,
            )
            return CrawlSummary(
                channel_name=getattr(channel, "name", str(target.channel_id)),
                output_root=str(output_root_path),
                ads=ads,
                skipped_count=0,
            )
        finally:
            if not client.is_closed():
                await client.close()

            try:
                await start_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def _crawl_from_channel(
        self,
        channel,
        source_channel_url: str,
        output_root: str,
        include_archived: bool,
    ) -> List[ScrapedAd]:
        if isinstance(channel, discord.Thread):
            return [await self._crawl_thread(channel, source_channel_url, output_root)]

        if isinstance(channel, discord.ForumChannel):
            threads = list(getattr(channel, "threads", []) or [])

            if include_archived:
                async for archived_thread in channel.archived_threads(limit=None):
                    threads.append(archived_thread)

            deduped_threads = []
            seen_ids = set()
            for thread in threads:
                if thread.id not in seen_ids:
                    seen_ids.add(thread.id)
                    deduped_threads.append(thread)

            self._log(f"共找到 {len(deduped_threads)} 个帖子，开始抓取")

            ads: List[ScrapedAd] = []
            for index, thread in enumerate(deduped_threads, start=1):
                self._log(f"[{index}/{len(deduped_threads)}] 抓取帖子: {thread.name}")
                ads.append(await self._crawl_thread(thread, source_channel_url, output_root))
            return ads

        raise ValueError("当前只支持论坛频道链接或单个帖子链接")

    async def _crawl_thread(self, thread: discord.Thread, source_channel_url: str, output_root: str) -> ScrapedAd:
        starter_message = await self._get_starter_message(thread)
        source_message_url = getattr(starter_message, "jump_url", "") if starter_message else ""

        if starter_message is None:
            ad = ScrapedAd(
                title=thread.name,
                link="",
                image_urls=[],
                source_channel_url=source_channel_url,
                source_message_url=source_message_url,
            )
        else:
            ad = extract_ad_record(
                title=thread.name,
                message=starter_message,
                source_channel_url=source_channel_url,
                source_message_url=source_message_url,
            )

        output_dir = get_unique_output_dir(output_root, ad.title)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        write_metadata_file(output_dir, ad)

        if ad.image_urls:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for index, image_url in enumerate(ad.image_urls, start=1):
                    try:
                        image_path = await _download_image(session, image_url, output_dir, index)
                        ad.image_paths.append(image_path)
                    except Exception as exc:
                        self._log(f"下载图片失败: {image_url} | {exc}")

        ad.output_dir = output_dir
        return ad

    async def _get_starter_message(self, thread: discord.Thread):
        async for message in thread.history(limit=1, oldest_first=True):
            return message
        return None
