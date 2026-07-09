import unittest
from types import SimpleNamespace

from src.discord_client import _channel_matches_targets, parse_discord_comment_target


class DiscordTargetParsingTests(unittest.TestCase):
    def test_thread_channel_matches_parent_for_subforum_reply(self):
        thread = SimpleNamespace(id=222, parent_id=111, parent=None)

        self.assertTrue(_channel_matches_targets(thread, [111]))
        self.assertTrue(_channel_matches_targets(thread, [222]))
        self.assertFalse(_channel_matches_targets(thread, [333]))

    def test_parse_forum_post_link_as_channel_and_thread_target(self):
        channel_id, target_id = parse_discord_comment_target(
            "https://discord.com/channels/1/111/222"
        )

        self.assertEqual(channel_id, 111)
        self.assertEqual(target_id, 222)

    def test_parse_plain_forum_thread_pair(self):
        channel_id, target_id = parse_discord_comment_target("111/222")

        self.assertEqual(channel_id, 111)
        self.assertEqual(target_id, 222)


if __name__ == "__main__":
    unittest.main()
