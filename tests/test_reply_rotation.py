import unittest

from src.discord_client import Account, DiscordManager


class ReplyRotationTests(unittest.TestCase):
    def test_next_available_account_rotates_when_ui_rotation_disabled(self):
        manager = DiscordManager()
        manager.rotation_enabled = False
        manager.current_rotation_index = 1
        manager.accounts = [
            Account("token-a", is_valid=True),
            Account("token-b", is_valid=True),
        ]

        account = manager.get_next_available_account()

        self.assertIsNotNone(account)
        self.assertEqual(account.token, "token-b")


if __name__ == "__main__":
    unittest.main()
