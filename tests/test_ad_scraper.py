#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ad_scraper import (
    ScrapedAd,
    extract_ad_record,
    get_unique_output_dir,
    parse_discord_channel_url,
    sanitize_folder_name,
    write_metadata_file,
)


class StubAttachment:
    def __init__(self, url, filename="image.jpg", content_type="image/jpeg"):
        self.url = url
        self.filename = filename
        self.content_type = content_type


class StubMedia:
    def __init__(self, url=None):
        self.url = url


class StubEmbed:
    def __init__(self, url=None, image_url=None, thumbnail_url=None):
        self.url = url
        self.image = StubMedia(image_url)
        self.thumbnail = StubMedia(thumbnail_url)


class StubMessage:
    def __init__(self, content="", attachments=None, embeds=None):
        self.content = content
        self.attachments = attachments or []
        self.embeds = embeds or []


class AdScraperTests(unittest.TestCase):
    def test_parse_discord_channel_url(self):
        target = parse_discord_channel_url(
            "https://discord.com/channels/1184756111182676004/1492351635899420816"
        )
        self.assertEqual(target.guild_id, 1184756111182676004)
        self.assertEqual(target.channel_id, 1492351635899420816)

    def test_parse_discord_channel_url_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            parse_discord_channel_url("https://example.com/channels/1/2")

    def test_sanitize_folder_name(self):
        self.assertEqual(sanitize_folder_name(' C/P Hat: 2024? '), "C_P Hat_ 2024")

    def test_extract_ad_record(self):
        message = StubMessage(
            content="新品上架 https://hoobuy.com/product/2/7647670176",
            attachments=[
                StubAttachment("https://cdn.discordapp.com/a.jpg"),
                StubAttachment("https://cdn.discordapp.com/a.jpg"),
            ],
            embeds=[
                StubEmbed(
                    url="https://hoobuy.com/product/2/7647670176",
                    image_url="https://images.example.com/1.jpg",
                    thumbnail_url="https://images.example.com/2.jpg",
                )
            ],
        )

        ad = extract_ad_record("C.P Hat", message)

        self.assertEqual(ad.title, "C.P Hat")
        self.assertEqual(ad.link, "https://hoobuy.com/product/2/7647670176")
        self.assertEqual(
            ad.image_urls,
            [
                "https://cdn.discordapp.com/a.jpg",
                "https://images.example.com/1.jpg",
                "https://images.example.com/2.jpg",
            ],
        )

    def test_get_unique_output_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "C.P Hat"))

            output_dir = get_unique_output_dir(temp_dir, "C.P Hat")

            self.assertEqual(os.path.basename(output_dir), "C.P Hat_2")

    def test_write_metadata_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ad = ScrapedAd(
                title="C.P Hat",
                link="https://hoobuy.com/product/2/7647670176",
                image_urls=["https://images.example.com/1.jpg"],
                source_channel_url="https://discord.com/channels/1/2",
            )

            metadata_path = write_metadata_file(temp_dir, ad)

            with open(metadata_path, "r", encoding="utf-8") as handle:
                content = handle.read()

            self.assertIn("标题: C.P Hat", content)
            self.assertIn("商品链接: https://hoobuy.com/product/2/7647670176", content)
            self.assertIn("图片数量: 1", content)


if __name__ == "__main__":
    unittest.main()
