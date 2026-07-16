import unittest
from types import SimpleNamespace

from src.discord_client import Account, DiscordManager


class _FakeThread:
    def __init__(self):
        self.id = 321
        self.parent_id = 123
        self.sent = []

    async def send(self, content=None, files=None):
        self.sent.append((content, files))


class _FakeTargetMessage:
    def __init__(self, thread):
        self.thread = thread
        self.reply_calls = []

    async def reply(self, content=None, files=None):
        self.reply_calls.append((content, files))


class _FakeChannel:
    def __init__(self, target_message):
        self.id = 123
        self.target_message = target_message

    async def fetch_message(self, message_id):
        return self.target_message


class _FakeClient:
    def __init__(self, account, channel):
        self.account = account
        self.is_running = True
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel


class _FailingThread(_FakeThread):
    async def send(self, content=None, files=None):
        raise RuntimeError("send failed")


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


class ReplyThreadRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_forum_starter_reply_is_sent_to_thread(self):
        manager = DiscordManager()
        account = Account("token-a", is_valid=True)
        thread = _FakeThread()
        target_message = _FakeTargetMessage(thread)
        channel = _FakeChannel(target_message)
        manager.accounts = [account]
        manager.clients = [_FakeClient(account, channel)]
        message = SimpleNamespace(id=456, channel=SimpleNamespace(id=123))

        success = await manager.send_rotated_reply(message, "hello", force=True)

        self.assertTrue(success)
        self.assertEqual(thread.sent, [("hello", None)])
        self.assertEqual(target_message.reply_calls, [])

    async def test_message_already_in_thread_is_sent_to_same_thread(self):
        manager = DiscordManager()
        account = Account("token-a", is_valid=True)
        thread = _FakeThread()
        manager.accounts = [account]
        manager.clients = [_FakeClient(account, thread)]
        message = SimpleNamespace(id=456, channel=SimpleNamespace(id=321, parent_id=123))

        success = await manager.send_rotated_reply(message, "hello", force=True)

        self.assertTrue(success)
        self.assertEqual(thread.sent, [("hello", None)])

    async def test_failed_account_falls_through_to_next_account(self):
        manager = DiscordManager()
        first = Account("token-a", is_valid=True)
        second = Account("token-b", is_valid=True)
        successful_thread = _FakeThread()
        manager.accounts = [first, second]
        manager.clients = [
            _FakeClient(first, _FailingThread()),
            _FakeClient(second, successful_thread),
        ]
        message = SimpleNamespace(id=456, channel=SimpleNamespace(id=321, parent_id=123))

        success = await manager.send_rotated_reply(message, "hello", force=True)

        self.assertTrue(success)
        self.assertEqual(successful_thread.sent, [("hello", None)])
        self.assertEqual(manager.current_rotation_index, 0)


if __name__ == "__main__":
    unittest.main()
