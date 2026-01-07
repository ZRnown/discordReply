import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import asdict
from .discord_client import Account, Rule, MatchType, PostingTask, CommentTask


class ConfigManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = self._get_config_dir(config_dir)
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.ensure_config_dir()

    def _get_config_dir(self, config_dir: str) -> str:
        if getattr(sys, 'frozen', False):
            # 运行在打包后的 EXE 中，配置目录与 EXE 同级
            exe_path = Path(sys.executable).parent
            return str(exe_path / config_dir)
        else:
            # 运行在开发环境中
            return config_dir

    def ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def save_config(self, accounts: List[Account], rules: List[Rule], license_config: Dict = None, rotation_config: Dict = None, posting_tasks: List[PostingTask] = None, comment_tasks: List[CommentTask] = None):
        """保存配置到文件"""
        config_data = {
            "accounts": [
                {
                    "token": acc.token,
                    "is_active": acc.is_active,
                    "is_valid": acc.is_valid,
                    "last_verified": acc.last_verified,
                    "user_info": acc.user_info
                }
                for acc in accounts
            ],
            "rules": [
                {
                    "id": rule.id,
                    "keywords": rule.keywords,
                    "reply": rule.reply,
                    "match_type": rule.match_type.value,
                    "target_channels": rule.target_channels,
                    "delay_min": rule.delay_min,
                    "delay_max": rule.delay_max,
                    "is_active": rule.is_active,
                    "ignore_replies": getattr(rule, 'ignore_replies', False),
                    "ignore_mentions": getattr(rule, 'ignore_mentions', False),
                    "case_sensitive": getattr(rule, 'case_sensitive', False),
                    "image_path": getattr(rule, 'image_path', None),
                    "account_ids": getattr(rule, 'account_ids', [])
                }
                for rule in rules
            ]
        }

        # 添加轮换配置
        if rotation_config:
            config_data["rotation"] = rotation_config

        # 添加许可证配置
        if license_config:
            config_data["license"] = license_config

        # 添加发帖任务
        if posting_tasks:
            config_data["posting_tasks"] = [
                {
                    "id": task.id,
                    "content": task.content,
                    "channel_id": task.channel_id,
                    "title": task.title,
                    "image_path": task.image_path,
                    "delay_seconds": task.delay_seconds,
                    "is_active": task.is_active,
                    "created_at": task.created_at
                }
                for task in posting_tasks
            ]

        # 添加评论任务
        if comment_tasks:
            config_data["comment_tasks"] = [
                {
                    "id": task.id,
                    "content": task.content,
                    "message_link": task.message_link,
                    "image_path": task.image_path,
                    "delay_seconds": task.delay_seconds,
                    "is_active": task.is_active,
                    "created_at": task.created_at
                }
                for task in comment_tasks
            ]

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def load_config(self) -> tuple[List[Account], List[Rule], Dict, Dict, List[PostingTask], List[CommentTask]]:
        """从文件加载配置"""
        if not os.path.exists(self.config_file):
            return [], [], {}, {}, [], []

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            accounts = []
            for acc_data in config_data.get("accounts", []):
                account = Account(
                    token=acc_data["token"],
                    is_active=acc_data.get("is_active", True),
                    is_valid=acc_data.get("is_valid", False),
                    last_verified=acc_data.get("last_verified"),
                    user_info=acc_data.get("user_info"),
                )
                accounts.append(account)

            rules = []
            for rule_data in config_data.get("rules", []):
                rule = Rule(
                    id=rule_data.get("id", f"rule_{len(rules)}"),  # 如果没有id，生成一个
                    keywords=rule_data["keywords"],
                    reply=rule_data["reply"],
                    match_type=MatchType(rule_data["match_type"]),
                    target_channels=rule_data["target_channels"],
                    delay_min=rule_data.get("delay_min", 2.0),
                    delay_max=rule_data.get("delay_max", 5.0),
                    is_active=rule_data.get("is_active", True),
                    ignore_replies=rule_data.get("ignore_replies", False),
                    ignore_mentions=rule_data.get("ignore_mentions", False),
                    case_sensitive=rule_data.get("case_sensitive", False),
                    image_path=rule_data.get("image_path"),
                    account_ids=rule_data.get("account_ids", [])
                )
                rules.append(rule)

            # 加载许可证配置
            license_config = config_data.get("license", {})

            # 加载轮换配置
            rotation_config = config_data.get("rotation", {})

            # 加载发帖任务
            posting_tasks = []
            for task_data in config_data.get("posting_tasks", []):
                task = PostingTask(
                    id=task_data["id"],
                    content=task_data["content"],
                    channel_id=task_data["channel_id"],
                    title=task_data.get("title"),
                    image_path=task_data.get("image_path"),
                    delay_seconds=task_data.get("delay_seconds", 0),
                    is_active=task_data.get("is_active", True),
                    created_at=task_data.get("created_at")
                )
                posting_tasks.append(task)

            # 加载评论任务
            comment_tasks = []
            for task_data in config_data.get("comment_tasks", []):
                task = CommentTask(
                    id=task_data["id"],
                    content=task_data["content"],
                    message_link=task_data["message_link"],
                    image_path=task_data.get("image_path"),
                    delay_seconds=task_data.get("delay_seconds", 0),
                    is_active=task_data.get("is_active", True),
                    created_at=task_data.get("created_at")
                )
                comment_tasks.append(task)

            return accounts, rules, license_config, rotation_config, posting_tasks, comment_tasks

        except Exception as e:
            print(f"加载配置失败: {e}")
            return [], [], {}, {}, [], []

    def export_config(self, filepath: str, accounts: List[Account], rules: List[Rule]) -> bool:
        """导出配置到指定文件"""
        try:
            config_data = {
                "accounts": [
                    {
                        "token": acc.token,
                        "alias": acc.alias,
                        "is_active": acc.is_active
                    }
                    for acc in accounts
                ],
                "rules": [
                    {
                        "keywords": rule.keywords,
                        "reply": rule.reply,
                        "match_type": rule.match_type.value,
                        "target_channels": rule.target_channels,
                        "delay_min": rule.delay_min,
                        "delay_max": rule.delay_max,
                        "is_active": rule.is_active,
                        "ignore_replies": getattr(rule, 'ignore_replies', False),
                        "ignore_mentions": getattr(rule, 'ignore_mentions', False),
                        "case_sensitive": getattr(rule, 'case_sensitive', False)
                    }
                    for rule in rules
                ]
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出配置失败: {e}")
            return False

    def import_config(self, filepath: str) -> tuple[List[Account], List[Rule]]:
        """从指定文件导入配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            accounts = []
            for acc_data in config_data.get("accounts", []):
                account = Account(
                    token=acc_data["token"],
                    is_active=acc_data.get("is_active", True),
                    is_valid=acc_data.get("is_valid", False),
                    last_verified=acc_data.get("last_verified"),
                    user_info=acc_data.get("user_info"),
                )
                accounts.append(account)

            rules = []
            for rule_data in config_data.get("rules", []):
                rule = Rule(
                    id=rule_data.get("id", f"rule_{len(rules)}"),  # 如果没有id，生成一个
                    keywords=rule_data["keywords"],
                    reply=rule_data["reply"],
                    match_type=MatchType(rule_data["match_type"]),
                    target_channels=rule_data["target_channels"],
                    delay_min=rule_data.get("delay_min", 2.0),
                    delay_max=rule_data.get("delay_max", 5.0),
                    is_active=rule_data.get("is_active", True),
                    ignore_replies=rule_data.get("ignore_replies", False),
                    ignore_mentions=rule_data.get("ignore_mentions", False),
                    case_sensitive=rule_data.get("case_sensitive", False)
                )
                rules.append(rule)

            return accounts, rules

        except Exception as e:
            print(f"导入配置失败: {e}")
            return [], []
