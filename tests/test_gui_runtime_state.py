import os
import sys
import unittest
from types import SimpleNamespace


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.discord_client import Account, CommentTask
from src.gui import MainWindow


class _ValueSpin:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class GuiRuntimeStateTests(unittest.TestCase):
    def test_int_checked_state_enables_comment_rotation(self):
        window = MainWindow.__new__(MainWindow)
        window.discord_manager = SimpleNamespace(
            comment_rotation_enabled=False,
            comment_rotation_count=0,
        )
        window.comment_rotation_count_spin = _ValueSpin(3)
        window.save_config = lambda: None
        window.refresh_runtime_contexts_from_workspaces = lambda: None
        window.add_log = lambda *args, **kwargs: None

        MainWindow.on_comment_rotation_enabled_changed(window, 2)

        self.assertTrue(window.discord_manager.comment_rotation_enabled)
        self.assertEqual(window.discord_manager.comment_rotation_count, 3)

    def test_refresh_runtime_contexts_syncs_current_workspace_tasks_first(self):
        window = MainWindow.__new__(MainWindow)
        account = Account(token="token", is_active=True, is_valid=True)
        window.discord_manager = SimpleNamespace(
            accounts=[account],
            rules=[],
            posting_tasks=[],
            comment_tasks=[
                CommentTask(
                    id="comment_1",
                    content="new comment",
                    message_link="https://discord.com/channels/1/2/3",
                )
            ],
            rotation_enabled=False,
            rotation_interval=600,
            posting_rotation_enabled=False,
            posting_rotation_count=10,
            comment_rotation_enabled=True,
            comment_rotation_count=1,
            posting_interval=30,
            posting_cycle_interval=30,
            comment_interval=30,
            comment_cycle_interval=30,
            posting_repeat_enabled=False,
            comment_repeat_enabled=False,
            comment_link_interval=5,
            default_posting_channel_id=None,
            default_posting_tags=[],
            posting_start_delay=0,
            comment_start_delay=0,
            reply_start_delay=0,
            posting_account_tokens=[],
            comment_account_tokens=[],
            workspace_posting_contexts={},
            workspace_comment_contexts={},
            workspace_reply_contexts={},
            runtime_posting_tasks=[],
            runtime_comment_tasks=[],
            reply_rule_pool=[],
            reply_enabled=False,
            posting_enabled=False,
            comment_enabled=False,
            is_running=False,
            clients=[],
            get_active_reply_rules=lambda: [],
        )
        window.workspaces = [{
            "id": "ws_1",
            "name": "工具1",
            "rules": [],
            "posting_tasks": [],
            "comment_tasks": [],
            "rotation": {},
            "features": {
                "reply_enabled": False,
                "posting_enabled": False,
                "comment_enabled": True,
                "reply_start_at": None,
                "posting_start_at": None,
                "comment_start_at": None,
            },
        }]
        window.active_workspace_index = 0

        MainWindow.refresh_runtime_contexts_from_workspaces(window)

        context = window.discord_manager.workspace_comment_contexts["ws_1"]
        self.assertEqual(len(context["tasks"]), 1)
        self.assertEqual(context["tasks"][0].content, "new comment")


if __name__ == "__main__":
    unittest.main()
