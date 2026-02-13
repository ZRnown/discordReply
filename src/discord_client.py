import asyncio
import discord
import re
import random
import time
import copy
import logging
import aiohttp
import platform
import hashlib
import uuid
import os
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

# discord.py-self 不需要Intents


class MatchType(Enum):
    PARTIAL = "partial"
    EXACT = "exact"
    REGEX = "regex"


@dataclass
class Account:
    token: str
    is_active: bool = True
    is_valid: bool = False  # 账号验证状态
    last_verified: Optional[float] = None  # 最后验证时间
    user_info: Optional[Dict] = None  # 用户信息
    last_sent_time: Optional[float] = None  # 最后发送消息时间
    rate_limit_until: Optional[float] = None  # 频率限制到期时间

    @property
    def alias(self) -> str:
        """获取账号别名（使用用户名）"""
        if self.user_info and isinstance(self.user_info, dict):
            return f"{self.user_info.get('name', 'Unknown')}#{self.user_info.get('discriminator', '0000')}"
        return f"账号-{self.token[:8]}..."


@dataclass
class PostingTask:
    """发帖任务"""
    id: str  # 任务唯一标识
    content: str  # 发帖内容
    channel_id: int  # 目标频道ID
    title: Optional[str] = None  # 帖子标题（可选）
    image_path: Optional[str] = None  # 可选的图片路径（支持多个，用分号或逗号分隔）
    delay_seconds: int = 0  # 延迟发帖时间（秒）
    is_active: bool = True  # 是否激活
    created_at: Optional[float] = None  # 创建时间
    tags: Optional[List[str]] = None  # 论坛标签（可选，名称或ID）
    next_run_at: Optional[float] = None  # 下次执行时间戳
    sent_count: int = 0  # 已发送次数（用于单次发送控制）
    last_sent_at: Optional[float] = None  # 最近发送时间

    def __post_init__(self):
        # 只有当created_at为None时才设置当前时间
        # 这样可以保留从配置加载的原始创建时间
        if self.created_at is None:
            self.created_at = time.time()
        if self.tags is None:
            self.tags = []
        if self.next_run_at is None and self.delay_seconds > 0:
            self.next_run_at = self.created_at + self.delay_seconds
        if self.sent_count is None:
            self.sent_count = 0


@dataclass
class CommentTask:
    """评论任务"""
    id: str  # 任务唯一标识
    content: str  # 评论内容
    message_link: str  # 目标消息链接
    image_path: Optional[str] = None  # 可选的图片路径
    delay_seconds: int = 0  # 延迟评论时间（秒）
    is_active: bool = True  # 是否激活
    created_at: Optional[float] = None  # 创建时间
    next_run_at: Optional[float] = None  # 下次执行时间戳
    sent_count: int = 0  # 已发送次数（用于单次发送控制）
    last_sent_at: Optional[float] = None  # 最近发送时间

    def __post_init__(self):
        # 只有当created_at为None时才设置当前时间
        # 这样可以保留从配置加载的原始创建时间
        if self.created_at is None:
            self.created_at = time.time()
        if self.next_run_at is None and self.delay_seconds > 0:
            self.next_run_at = self.created_at + self.delay_seconds
        if self.sent_count is None:
            self.sent_count = 0


@dataclass
class Rule:
    id: str  # 规则唯一标识
    keywords: List[str]
    reply: str
    match_type: MatchType
    target_channels: List[int]
    delay_min: float = 0.1
    delay_max: float = 1.0
    is_active: bool = True
    ignore_replies: bool = True  # 是否忽略回复他人的消息
    ignore_mentions: bool = True  # 是否忽略包含@他人的消息
    case_sensitive: bool = False  # 是否区分大小写，False表示不区分大小写
    image_path: Optional[str] = None  # 可选的图片路径，用于回复图片
    account_ids: List[str] = None  # 可使用的账号ID列表，为空则随机使用所有账号

    def __post_init__(self):
        if self.account_ids is None:
            self.account_ids = []


class AutoReplyClient(discord.Client):
    def __init__(self, account: Account, rules: List[Rule], log_callback=None, discord_manager=None, *args, **kwargs):
        # 修正: discord.py-self 不需要也不支持 intents 参数
        # 直接调用父类构造函数即可
        super().__init__(*args, **kwargs)

        self.account = account
        self.rules = rules
        self.is_running = False
        self.log_callback = log_callback
        self.discord_manager = discord_manager

    async def _send_reply_with_image(self, message, text: str, image_path: Optional[str] = None):
        """发送包含文本和图片的回复"""
        import discord
        import os

        # 支持多个图片，用分号或逗号分隔
        image_paths = []
        if image_path:
            # 按分号或逗号分割，支持多个图片路径
            separators = [';', ',']
            for sep in separators:
                if sep in image_path:
                    image_paths = [path.strip() for path in image_path.split(sep) if path.strip()]
                    break
            else:
                # 单个图片路径
                image_paths = [image_path]

            # 过滤出存在的文件
            image_paths = [path for path in image_paths if os.path.exists(path)]

        if image_paths:
            # 发送图片文件
            try:
                files = [discord.File(path) for path in image_paths]
                if text.strip():
                    await message.reply(text, files=files)
                else:
                    await message.reply(files=files)
                return True
            except Exception as e:
                error_msg = f"发送图片失败: {e}"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)
                return False
        else:
            # 只发送文本
            await message.reply(text)
            return True

    async def on_ready(self):
        try:
            # 确保self.user不为None
            if self.user is None:
                error_msg = f"[{self.account.alias}] 用户信息获取失败：client.user为None"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)
                self.is_running = False
                return

            # 设置运行状态
            old_status = self.is_running
            self.is_running = True

            username = getattr(self.user, 'name', 'Unknown')
            discriminator = getattr(self.user, 'discriminator', '0000')
            display_name = f"{username}#{discriminator}"
            message = f"[{self.account.alias}] 登录成功: {display_name}"
            print(message)
            if self.log_callback:
                self.log_callback(message)
                self.log_callback(f"[{self.account.alias}] 运行状态变更: {old_status} -> {self.is_running}")

            # 更新账号信息
            self.account.user_info = {
                'id': str(self.user.id),
                'name': username,
                'discriminator': discriminator,
                'bot': getattr(self.user, 'bot', False)
            }

        except Exception as e:
            error_msg = f"[{self.account.alias}] on_ready事件错误: {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.is_running = False

    async def on_message(self, message):
        # 不要回复自己
        if message.author.id == self.user.id:
            return

        # 检查自动回复功能是否启用
        if not self.discord_manager.reply_enabled:
            return

        runtime_rules = self.rules
        if self.discord_manager:
            runtime_rules = self.discord_manager.get_active_reply_rules()

        # 没有可用规则时无需继续
        if not runtime_rules:
            return

        # 兼容旧模式：仅在未使用多页面上下文时才用全局启动倒计时拦截
        if (not self.discord_manager.workspace_reply_contexts and
                self.discord_manager.reply_start_at is not None and
                time.time() < self.discord_manager.reply_start_at):
            return

        if self.log_callback:
            self.log_callback(f"📨 收到消息: '{message.content}' 来自 {message.author.name}#{message.author.discriminator}")

        # 检查是否是被屏蔽的用户
        try:
            # Discord.py-self 可能有 blocked 属性
            if hasattr(message.author, 'blocked') and message.author.blocked:
                return
        except:
            pass  # 如果无法检查，跳过

        # 过滤出当前账号可以使用的规则
        applicable_rules = []
        for rule in runtime_rules:
            if not rule.is_active:
                continue
            # 如果规则指定了账号ID列表，则检查当前账号是否在列表中
            # 如果规则没有指定账号ID（为空），则所有账号都可以使用
            if rule.account_ids and str(self.account.token) not in rule.account_ids:
                continue
            applicable_rules.append(rule)

        for rule in applicable_rules:
            if rule.target_channels and message.channel.id not in rule.target_channels:
                continue

            if rule.ignore_replies and message.reference is not None:
                continue

            if rule.ignore_mentions and message.mentions:
                continue

            if self._check_match(message.content, rule):
                match_msg = f"[{self.account.alias}] 🎯 匹配到关键词 | 消息: '{message.content}' | 来自: {message.author.name} | 频道: #{message.channel.name}"
                reply_msg = f"[{self.account.alias}] 🤖 准备回复: '{rule.reply}'"

                print(match_msg)
                print(reply_msg)
                if self.log_callback:
                    self.log_callback(match_msg)
                    self.log_callback(reply_msg)

                try:
                    delay = random.uniform(rule.delay_min, rule.delay_max)
                    delay_msg = f"[{self.account.alias}] ⏱️  等待 {delay:.1f} 秒..."
                    print(delay_msg)
                    if self.log_callback:
                        self.log_callback(delay_msg)

                    try:
                        async with message.channel.typing():
                            await asyncio.sleep(delay)
                    except Exception:
                        await asyncio.sleep(delay)

                    # 检查是否启用轮换模式
                    if (self.discord_manager and self.discord_manager.rotation_enabled):
                        # 使用轮换模式
                        allowed_tokens = set(rule.account_ids) if rule.account_ids else None
                        success = await self.discord_manager.send_rotated_reply(
                            message,
                            rule.reply,
                            rule.keywords[0] if rule.keywords else "",
                            image_path=rule.image_path,
                            allowed_tokens=allowed_tokens
                        )
                        if success:
                            success_msg = f"[{self.account.alias}] ✅ 轮换回复成功"
                            print(success_msg)
                            if self.log_callback:
                                self.log_callback(success_msg)
                        else:
                            error_msg = f"[{self.account.alias}] ❌ 轮换回复失败"
                            print(error_msg)
                            if self.log_callback:
                                self.log_callback(error_msg)
                    else:
                        # 使用普通回复
                        success = await self._send_reply_with_image(message, rule.reply, rule.image_path)
                        if success:
                            success_msg = f"[{self.account.alias}] ✅ 回复成功"
                            print(success_msg)
                            if self.log_callback:
                                self.log_callback(success_msg)
                            if self.discord_manager:
                                self.discord_manager.reply_sent_total += 1
                        else:
                            error_msg = f"[{self.account.alias}] ❌ 回复失败"
                            print(error_msg)
                            if self.log_callback:
                                self.log_callback(error_msg)

                    break # 只处理第一个匹配规则

                except Exception as e:
                    error_msg = f"[{self.account.alias}] ❌ 回复失败: {e}"
                    print(error_msg)
                    if self.log_callback:
                        self.log_callback(error_msg)

                break

    def _check_match(self, content: str, rule: Rule) -> bool:
        """检查消息内容是否匹配规则"""
        if not content:
            return False

        if rule.match_type == MatchType.PARTIAL:
            if rule.case_sensitive:
                # 区分大小写
                return any(keyword in content for keyword in rule.keywords)
            else:
                # 不区分大小写
                content_lower = content.lower()
            return any(keyword.lower() in content_lower for keyword in rule.keywords)
        elif rule.match_type == MatchType.EXACT:
            if rule.case_sensitive:
                # 区分大小写
                return content in rule.keywords
            else:
                # 不区分大小写
                content_lower = content.lower()
            return content_lower in [k.lower() for k in rule.keywords]
        elif rule.match_type == MatchType.REGEX:
            flags = 0 if rule.case_sensitive else re.IGNORECASE
            return any(re.search(keyword, content, flags) for keyword in rule.keywords)

        return False

    async def start_client(self):
        try:
            self.is_running = False

            # 启动客户端
            await self.start(self.account.token)

            # 等待on_ready事件，最多等待10秒
            try:
                await asyncio.wait_for(self.wait_for('ready', timeout=10.0), timeout=10.0)
                # 如果能到达这里，说明on_ready已经成功执行，is_running已经被设置为True
            except asyncio.TimeoutError:
                error_msg = f"[{self.account.alias}] 连接超时：等待ready事件超时"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)
                self.is_running = False
                await self.close()

        except discord.LoginFailure as e:
            error_msg = f"[{self.account.alias}] 登录失败: 账号无效 - {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.is_running = False

        except Exception as e:
            error_msg = f"[{self.account.alias}] 启动失败: {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.is_running = False

    async def stop_client(self):
        """停止客户端"""
        self.is_running = False
        await self.close()


class TokenValidator:
    """Discord Token验证器"""

    # 注意: TokenValidator 中使用了 discord.Client() 进行验证
    # 也需要移除 intents 参数

    @staticmethod
    async def validate_token(token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        token = token.strip()
        if not token:
            return False, None, "账号为空"

        # 1. 先尝试 HTTP 验证 (更稳)
        try:
            http_res = await TokenValidator._validate_token_http(token)
            if http_res[0] is not None:
                return http_res
        except Exception as e:
            # HTTP验证完全失败，继续WebSocket验证
            pass

        # 2. 备选: WebSocket 验证
        try:
            ws_res = await TokenValidator._validate_token_websocket(token)
            return ws_res
        except Exception as e:
            return False, None, "所有验证方法都失败，请检查账号和网络连接"

    @staticmethod
    def _detect_token_type(token: str) -> str:
        token = token.strip()
        if len(token) > 70: return "bot"
        if token.startswith("mfa.") or len(token) < 70: return "user"
        return "unknown"

    @staticmethod
    async def _validate_token_http(token: str) -> Tuple[Optional[bool], Optional[Dict], Optional[str]]:
        import aiohttp
        token = token.strip()
        if not token: return False, None, "账号为空"

        headers = {'Authorization': token, 'User-Agent': 'DiscordBot/1.0'}
        timeout = aiohttp.ClientTimeout(total=10)  # 设置10秒超时
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://discord.com/api/v10/users/@me', headers=headers) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            if not data:
                                return False, None, "响应数据为空"
                            user_info = {
                                'id': data.get('id'),
                                'name': data.get('username'),
                                'discriminator': data.get('discriminator', '0000'),
                                'avatar_url': f"https://cdn.discordapp.com/avatars/{data.get('id', 'unknown')}/{data.get('avatar', 'unknown')}.png" if data.get('avatar') else None,
                                'bot': data.get('bot', False),
                                'token_type': 'bot' if data.get('bot') else 'user'
                            }
                            return True, user_info, None
                        except Exception as json_error:
                            return False, None, f"解析响应失败: {str(json_error)}"
                    elif resp.status == 401:
                        return False, None, "账号无效"
                    elif resp.status == 403:
                        return False, None, "账号权限不足"
                    elif resp.status == 429:
                        return False, None, "请求过于频繁，请稍后再试"
                    else:
                        return False, None, f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return None, None, "连接超时，请检查网络"
        except aiohttp.ClientError as client_error:
            return None, None, f"网络连接错误: {str(client_error)}"
        except Exception as e:
            # 避免返回复杂的错误对象，只返回字符串
            error_msg = str(e)
            # 如果错误信息太长或包含特殊字符，简化它
            if len(error_msg) > 100 or "'" in error_msg or '"' in error_msg:
                return None, None, "验证请求失败"
            return None, None, error_msg

    @staticmethod
    async def _validate_token_websocket(token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        使用WebSocket验证Token（备选方案）
        """
        client = None
        try:
            # 创建临时客户端进行验证
            client = discord.Client()

            user_info = None
            error = None

            @client.event
            async def on_ready():
                nonlocal user_info
                try:
                    u = client.user
                    user_info = {
                        'id': str(u.id),
                        'name': u.name,
                        'discriminator': getattr(u, 'discriminator', '0000'),
                        'avatar_url': str(u.avatar.url) if u.avatar else None,
                        'bot': getattr(u, 'bot', False)
                    }
                except Exception as e:
                    pass
                await client.close()

            # 启动客户端并设置超时
            try:
                await asyncio.wait_for(client.start(token), timeout=15.0)  # 15秒超时
            except asyncio.TimeoutError:
                return False, None, "WebSocket连接超时"

            # 等待ready事件，最多等待10秒
            try:
                await asyncio.wait_for(client.wait_for('ready', timeout=10.0), timeout=10.0)
            except asyncio.TimeoutError:
                return False, None, "等待ready事件超时"

            if user_info:
                return True, user_info, None
            return False, None, "无法获取用户信息"

        except asyncio.TimeoutError:
            return False, None, "WebSocket连接超时"
        except discord.LoginFailure:
            return False, None, "账号登录失败"
        except Exception as e:
            error_msg = str(e)
            # 简化错误信息，避免返回复杂的内部错误
            if len(error_msg) > 50 or "sequence" in error_msg or "NoneType" in error_msg:
                return False, None, "WebSocket验证失败"
            return False, None, f"验证失败: {error_msg}"
        finally:
            if client and not client.is_closed():
                await client.close()


class DiscordManager:
    def __init__(self, log_callback=None):
        self.clients: List[AutoReplyClient] = []
        self.accounts: List[Account] = []
        self.rules: List[Rule] = []
        self.is_running = False
        self.validator = TokenValidator()
        self.log_callback = log_callback
        self.license_manager = LicenseManager()  # 许可证管理器

        # 许可证配置（可以后续配置认证信息）
        self.license_client_username = "client"
        self.license_client_password = ""  # 用户需要配置

        # 轮换设置
        self.rotation_enabled: bool = False  # 是否启用账号轮换
        self.rotation_interval: int = 600  # 轮换间隔（秒），默认10分钟
        self.current_rotation_index: int = 0  # 当前使用的账号索引

        # 消息去重跟踪 - 存储已回复的消息ID，避免重复回复
        self.replied_messages: Set[int] = set()
        self.max_replied_messages: int = 1000  # 最多跟踪1000条消息
        self.reply_processing_messages: Set[int] = set()  # 正在处理的消息ID，避免并发重复回复

        # 功能启用状态
        self.reply_enabled: bool = False  # 是否启用自动回复
        self.posting_enabled: bool = False  # 是否启用自动发帖
        self.comment_enabled: bool = False  # 是否启用自动评论
        self.reply_rule_pool: List[Rule] = []  # 多页面运行时自动回复规则池
        self.workspace_reply_contexts: Dict[str, Dict] = {}  # 多页面自动回复上下文

        # 发帖和评论管理
        self.posting_tasks: List[PostingTask] = []  # 发帖任务列表
        self.comment_tasks: List[CommentTask] = []  # 评论任务列表
        self.posting_interval: int = 30  # 发帖间隔（秒），默认30秒
        self.comment_interval: int = 30  # 评论间隔（秒），默认30秒
        self.posting_cycle_interval: int = 30  # 发帖循环轮次间隔（秒）
        self.comment_cycle_interval: int = 30  # 评论循环轮次间隔（秒）
        self.posting_repeat_enabled: bool = False  # 发帖任务是否循环执行
        self.comment_repeat_enabled: bool = False  # 评论任务是否循环执行
        self.comment_link_interval: int = 5  # 评论多链接间隔（秒）
        self.default_posting_channel_id: Optional[int] = None  # 默认发帖频道
        self.default_posting_tags: List[str] = []  # 默认发帖标签
        self.posting_start_delay: int = 0  # 发帖启动倒计时（秒）
        self.comment_start_delay: int = 0  # 评论启动倒计时（秒）
        self.reply_start_delay: int = 0  # 自动回复启动倒计时（秒）
        self.posting_start_at: Optional[float] = None  # 发帖启动时间戳
        self.comment_start_at: Optional[float] = None  # 评论启动时间戳
        self.reply_start_at: Optional[float] = None  # 回复启动时间戳
        self.posting_account_tokens: List[str] = []  # 发帖账号选择（空=所有）
        self.comment_account_tokens: List[str] = []  # 评论账号选择（空=所有）
        self.posting_sent_total: int = 0  # 发帖发送总数
        self.comment_sent_total: int = 0  # 评论发送总数（按链接）
        self.reply_sent_total: int = 0  # 回复发送总数
        self.posting_task_cursor: int = 0  # 发帖任务轮询索引
        self.comment_task_cursor: int = 0  # 评论任务轮询索引
        self.runtime_posting_tasks: List[PostingTask] = []  # 运行中的发帖任务快照
        self.runtime_comment_tasks: List[CommentTask] = []  # 运行中的评论任务快照
        self.workspace_posting_contexts: Dict[str, Dict] = {}  # 多页面发帖运行上下文
        self.workspace_comment_contexts: Dict[str, Dict] = {}  # 多页面评论运行上下文
        self.current_posting_index: int = 0  # 当前发帖账号索引
        self.current_comment_index: int = 0  # 当前评论账号索引
        self.posting_scheduler_running: bool = False
        self.comment_scheduler_running: bool = False

        # 发帖和评论轮换设置
        self.posting_rotation_enabled: bool = False  # 是否启用发帖账号轮换
        self.comment_rotation_enabled: bool = False  # 是否启用评论账号轮换
        self.posting_rotation_count: int = 10  # 发帖多少条后轮换账号
        self.comment_rotation_count: int = 10  # 评论多少条后轮换账号
        self.posting_count_since_rotation: int = 0  # 当前账号发帖计数
        self.comment_count_since_rotation: int = 0  # 当前账号评论计数

    def configure_license_auth(self, username: str, password: str, api_path: str = "/api/v1"):
        """配置许可证认证信息"""
        self.license_client_username = username
        self.license_client_password = password
        self.license_manager.client_username = username
        self.license_manager.client_password = password
        self.license_manager.api_path = api_path

    async def add_account_async(self, token: str) -> Tuple[bool, Optional[str]]:
        if any(acc.token == token for acc in self.accounts):
            return False, "账号已存在"

        is_valid, user_info, msg = await self.validator.validate_token(token)

        # 即使验证失败也允许添加 (可能是网络问题)，但在UI显示无效
        account = Account(
            token=token,
            is_active=True,
            is_valid=is_valid or False,
            last_verified=time.time(),
            user_info=user_info
        )

        self.accounts.append(account)

        return True, "账号添加成功" + (f" ({user_info.get('name', 'Unknown')})" if user_info and isinstance(user_info, dict) else "")


    def remove_account(self, token: str):
        """移除账号"""
        self.accounts = [acc for acc in self.accounts if acc.token != token]

    def add_rule(self, keywords: List[str], reply: str, match_type: MatchType,
                 target_channels: List[int], delay_min: float = 0.1, delay_max: float = 1.0,
                 ignore_replies: bool = True, ignore_mentions: bool = True,
                 case_sensitive: bool = False, image_path: Optional[str] = None,
                 account_ids: Optional[List[str]] = None):
        """添加规则"""
        # 生成唯一的规则ID
        import time
        rule_id = f"rule_{int(time.time() * 1000)}_{len(self.rules)}"

        rule = Rule(
            id=rule_id,
            keywords=keywords,
            reply=reply,
            match_type=match_type,
            target_channels=target_channels,
            delay_min=delay_min,
            delay_max=delay_max,
            ignore_replies=ignore_replies,
            ignore_mentions=ignore_mentions,
            case_sensitive=case_sensitive,
            image_path=image_path,
            account_ids=account_ids
        )
        self.rules.append(rule)

    def remove_rule(self, index: int):
        """移除规则"""
        if 0 <= index < len(self.rules):
            self.rules.pop(index)

    def update_rule(self, index: int, **kwargs):
        """更新规则"""
        if 0 <= index < len(self.rules):
            rule = self.rules[index]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)

    def get_active_reply_rules(self) -> List[Rule]:
        """获取当前运行时生效的自动回复规则"""
        if self.workspace_reply_contexts:
            now = time.time()
            rules: List[Rule] = []
            for context in self.workspace_reply_contexts.values():
                if not context.get("enabled", False):
                    continue
                start_at = context.get("start_at")
                if start_at is not None and now < start_at:
                    continue
                rules.extend(context.get("rules", []))

            # 保留一份缓存，兼容其他读取点
            self.reply_rule_pool = rules
            return rules

        if self.reply_rule_pool:
            return self.reply_rule_pool
        return self.rules

    async def start_all_clients(self):
        if self.is_running: return

        self.is_running = True

        await self.stop_all_clients()
        self.clients.clear()

        for acc in self.accounts:
            if acc.is_active and acc.is_valid:
                # 所有客户端都使用所有规则，规则级别控制账号选择
                client = AutoReplyClient(acc, self.get_active_reply_rules() or self.rules, self.log_callback, self)
                self.clients.append(client)
                # 创建启动任务，让它们在后台运行
                asyncio.create_task(client.start_client())

        # 启动发帖和评论调度器
        if self.posting_enabled:
            asyncio.create_task(self.start_posting_scheduler())
            if self.log_callback:
                self.log_callback("📝 发帖调度器已启动")

        if self.comment_enabled:
            asyncio.create_task(self.start_comment_scheduler())
            if self.log_callback:
                self.log_callback("💬 评论调度器已启动")

        # 不在这里检查状态，让调用者负责等待和状态检查

    async def stop_all_clients(self):
        self.is_running = False

        for c in self.clients:
            await c.stop_client()

        self.clients.clear()

    async def revalidate_all_accounts(self) -> List[Dict]:
        """重新验证所有账号"""
        results = []

        for account in self.accounts:
            is_valid, user_info, error_msg = await self.validator.validate_token(account.token)

            # 更新账号状态
            account.is_valid = is_valid
            account.last_verified = time.time()
            account.user_info = user_info

            results.append({
                'alias': account.alias,
                'is_valid': is_valid,
                'user_info': user_info,
                'error_msg': error_msg
            })

        return results

    def get_next_available_account(self, allowed_tokens: Optional[Set[str]] = None) -> Optional[Account]:
        """获取下一个可用的账号（用于轮换）"""
        if not self.rotation_enabled or not self.accounts:
            return None

        # 查找所有有效的活跃账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
        if allowed_tokens:
            available_accounts = [acc for acc in available_accounts if acc.token in allowed_tokens]

        if not available_accounts:
            return None

        # 检查当前账号是否可以发送
        current_time = time.time()
        current_account = available_accounts[self.current_rotation_index % len(available_accounts)]

        # 如果当前账号没有频率限制或限制已过期，可以使用
        if (current_account.rate_limit_until is None or
            current_time >= current_account.rate_limit_until):
            return current_account

        # 否则，寻找下一个可用的账号
        for i in range(1, len(available_accounts)):
            next_index = (self.current_rotation_index + i) % len(available_accounts)
            account = available_accounts[next_index]
            if (account.rate_limit_until is None or
                current_time >= account.rate_limit_until):
                self.current_rotation_index = next_index
                return account

        # 如果所有账号都被限制，返回None
        return None

    async def send_rotated_reply(self, message, reply_text: str, rule_name: str = "",
                                 image_path: Optional[str] = None,
                                 allowed_tokens: Optional[Set[str]] = None) -> bool:
        """使用轮换账号发送回复"""
        if not self.rotation_enabled:
            return False

        # 检查这条消息是否已经被回复过
        if message.id in self.replied_messages:
            if self.log_callback:
                self.log_callback(f"⚠️ 消息 {message.id} 已被回复，跳过轮换回复")
            return False

        # 避免并发处理同一条消息导致重复回复
        if message.id in self.reply_processing_messages:
            if self.log_callback:
                self.log_callback(f"⚠️ 消息 {message.id} 正在处理，跳过重复轮换请求")
            return False

        self.reply_processing_messages.add(message.id)
        try:
            attempted_tokens: Set[str] = set()

            while True:
                available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
                if allowed_tokens:
                    available_accounts = [acc for acc in available_accounts if acc.token in allowed_tokens]

                available_accounts = [acc for acc in available_accounts if acc.token not in attempted_tokens]
                if not available_accounts:
                    if self.log_callback:
                        self.log_callback("❌ 可用轮换账号不足，无法完成回复")
                    return False

                account = self.get_next_available_account(allowed_tokens)
                if (not account) or (account.token in attempted_tokens):
                    account = available_accounts[0]

                attempted_tokens.add(account.token)
                current_time = time.time()
                account.last_sent_time = current_time

                client = next((c for c in self.clients if c.account.token == account.token), None)
                if not client:
                    if self.log_callback:
                        self.log_callback(f"❌ 找不到账号 {account.alias} 的客户端，尝试下一个账号")
                    continue
                if not client.is_running:
                    if self.log_callback:
                        self.log_callback(f"⏳ 客户端 {account.alias} 尚未登录完成，尝试下一个账号")
                    continue

                try:
                    channel = client.get_channel(message.channel.id)
                    if not channel:
                        channel = await client.fetch_channel(message.channel.id)
                    target_message = await channel.fetch_message(message.id)

                    image_paths = []
                    if image_path:
                        separators = [';', ',']
                        for sep in separators:
                            if sep in image_path:
                                image_paths = [path.strip() for path in image_path.split(sep) if path.strip()]
                                break
                        else:
                            image_paths = [image_path]
                        image_paths = [path for path in image_paths if os.path.exists(path)]

                    if image_paths:
                        files = [discord.File(path) for path in image_paths]
                        if reply_text.strip():
                            await target_message.reply(reply_text, files=files)
                        else:
                            await target_message.reply(files=files)
                    else:
                        await target_message.reply(reply_text)

                    self.replied_messages.add(message.id)
                    if len(self.replied_messages) > self.max_replied_messages:
                        # 保留新消息，移除最旧的一半记录
                        sorted_messages = sorted(self.replied_messages)
                        remove_count = len(sorted_messages) // 2
                        for msg_id in sorted_messages[:remove_count]:
                            self.replied_messages.remove(msg_id)

                    # 成功后移动到下一个账号
                    all_rotatable_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
                    if allowed_tokens:
                        all_rotatable_accounts = [acc for acc in all_rotatable_accounts if acc.token in allowed_tokens]
                    if all_rotatable_accounts:
                        try:
                            current_idx = all_rotatable_accounts.index(account)
                        except ValueError:
                            current_idx = self.current_rotation_index
                        self.current_rotation_index = (current_idx + 1) % len(all_rotatable_accounts)

                    if self.log_callback:
                        self.log_callback(f"✅ [{account.alias}] 轮换回复成功: '{reply_text[:50]}...'")
                    self.reply_sent_total += 1
                    return True

                except discord.HTTPException as e:
                    if e.code == 20016:  # 慢速模式
                        account.rate_limit_until = current_time + 600  # 10分钟限制
                        if self.log_callback:
                            self.log_callback(f"⚠️ [{account.alias}] 触发慢速模式，10分钟内无法发送")
                    elif e.code == 50035:  # 无效表单内容
                        if self.log_callback:
                            self.log_callback(f"❌ [{account.alias}] 发送失败: 无效内容")
                    else:
                        if self.log_callback:
                            self.log_callback(f"❌ [{account.alias}] 发送失败: HTTP {e.code}")
                    continue

                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 发送异常: {str(e)}")
                    continue

        finally:
            self.reply_processing_messages.discard(message.id)

    async def revalidate_account(self, token: str) -> Tuple[bool, Optional[str]]:
        """重新验证指定账号"""
        account = next((acc for acc in self.accounts if acc.token == token), None)
        if not account:
            return False, "账号不存在"

        is_valid, user_info, error_msg = await self.validator.validate_token(account.token)

        # 更新账号状态
        account.is_valid = is_valid
        account.last_verified = time.time()
        account.user_info = user_info

        if is_valid and user_info and isinstance(user_info, dict):
            username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
            return True, f"验证成功，用户名: {username}"
        else:
            return False, f"验证失败: {error_msg}"

    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "is_running": self.is_running,
            "accounts": [
                {
                    "token": acc.token,
                    "alias": acc.alias,  # 现在是只读属性
                    "is_active": acc.is_active,
                    "is_running": any(c.account.token == acc.token and c.is_running for c in self.clients)
                }
                for acc in self.accounts
            ],
            "rules_count": len(self.rules),
            "active_rules": len([r for r in self.rules if r.is_active]),
            "posting_sent_total": self.posting_sent_total,
            "comment_sent_total": self.comment_sent_total,
            "reply_sent_total": self.reply_sent_total
        }

    # ============ 发帖和评论功能 ============

    def add_posting_task(self, content: str, channel_id: Optional[int],
                         image_path: Optional[str] = None, delay_seconds: int = 0,
                         title: Optional[str] = None, tags: Optional[List[str]] = None):
        """添加发帖任务"""
        import time
        task_id = f"post_{int(time.time() * 1000)}_{len(self.posting_tasks)}"

        if not channel_id and self.default_posting_channel_id:
            channel_id = self.default_posting_channel_id

        initial_delay = delay_seconds if delay_seconds > 0 else 0

        task = PostingTask(
            id=task_id,
            title=title,
            content=content,
            image_path=image_path,
            channel_id=channel_id,
            delay_seconds=initial_delay,
            tags=tags,
            next_run_at=None
        )
        self.posting_tasks.append(task)

        if self.log_callback:
            self.log_callback(f"📝 发帖任务已添加: {task_id}")
            if title:
                self.log_callback(f"  标题: '{title}'")
            self.log_callback(f"  内容: '{content[:50]}{'...' if len(content) > 50 else ''}'")
            self.log_callback(f"  频道ID: {channel_id}")
            self.log_callback(f"  延迟: {initial_delay}秒")
            self.log_callback(f"  图片: {image_path if image_path else '无'}")
            if tags:
                self.log_callback(f"  标签: {', '.join(tags)}")

        return task_id

    def add_comment_task(self, content: str, message_link: str, image_path: Optional[str] = None, delay_seconds: int = 0):
        """添加评论任务"""
        import time
        task_id = f"comment_{int(time.time() * 1000)}_{len(self.comment_tasks)}"

        task = CommentTask(
            id=task_id,
            content=content,
            image_path=image_path,
            message_link=message_link,
            delay_seconds=delay_seconds
        )
        self.comment_tasks.append(task)
        return task_id

    async def execute_posting_task(self, task: PostingTask, runtime: Optional[Dict] = None) -> bool:
        """执行发帖任务"""
        if self.log_callback:
            self.log_callback(f"🔍 执行发帖任务: ID={task.id}, 频道={task.channel_id}, 内容='{task.content[:50]}...'")

        runtime_enabled = self.posting_enabled if runtime is None else runtime.get("enabled", True)
        if not runtime_enabled:
            if self.log_callback:
                self.log_callback("❌ 发帖功能未启用")
            return False

        # 验证频道ID格式
        try:
            if task.channel_id is None:
                raise ValueError("频道ID为空")
            channel_id_int = int(task.channel_id)
            if self.log_callback:
                self.log_callback(f"✅ 频道ID格式正确: {channel_id_int}")
        except ValueError:
            if self.log_callback:
                self.log_callback(f"❌ 频道ID格式错误: {task.channel_id}")
            return False

        # 获取下一个可用的账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
        account_tokens = self.posting_account_tokens
        if runtime is not None:
            account_tokens = runtime.get("account_tokens", account_tokens)

        if account_tokens:
            available_accounts = [acc for acc in available_accounts if acc.token in account_tokens]
        if not available_accounts:
            if self.log_callback:
                self.log_callback("❌ 没有可用的账号用于发帖")
            return False

        if self.log_callback:
            self.log_callback(f"✅ 找到 {len(available_accounts)} 个可用账号")

        rotation_enabled = self.posting_rotation_enabled
        rotation_count = max(1, int(self.posting_rotation_count))
        posting_index = self.current_posting_index
        posting_count_since_rotation = self.posting_count_since_rotation
        if runtime is not None:
            rotation_enabled = bool(runtime.get("rotation_enabled", rotation_enabled))
            rotation_count = max(1, int(runtime.get("rotation_count", rotation_count)))
            posting_index = int(runtime.get("current_index", posting_index))
            posting_count_since_rotation = int(runtime.get("count_since_rotation", posting_count_since_rotation))

        # 选择账号
        if rotation_enabled and posting_count_since_rotation >= rotation_count:
            # 轮换到下一个账号
            posting_index = (posting_index + 1) % len(available_accounts)
            posting_count_since_rotation = 0
            if self.log_callback:
                self.log_callback(f"🔄 发帖账号轮换到下一个")

        account = available_accounts[posting_index % len(available_accounts)]

        # 未启用轮换时按顺序使用账号（或固定账号）
        if not rotation_enabled:
            posting_index = (posting_index + 1) % len(available_accounts)

        if runtime is not None:
            runtime["current_index"] = posting_index
            runtime["count_since_rotation"] = posting_count_since_rotation
        else:
            self.current_posting_index = posting_index
            self.posting_count_since_rotation = posting_count_since_rotation

        # 查找对应的客户端
        if self.log_callback:
            self.log_callback(f"🔍 查找客户端 - 账号: {account.alias}, 客户端数量: {len(self.clients)}")

        client = next((c for c in self.clients if c.account.token == account.token), None)
        if not client:
            if self.log_callback:
                self.log_callback(f"❌ 找不到账号 {account.alias} 的客户端")
                # 列出现有的客户端
                for i, c in enumerate(self.clients):
                    self.log_callback(f"  客户端 {i}: {c.account.alias} (运行中: {c.is_running})")
            return False

        if self.log_callback:
            self.log_callback(f"✅ 找到客户端: {account.alias} (运行中: {client.is_running})")

        # 检查客户端是否已经登录成功
        if not client.is_running:
            if self.log_callback:
                self.log_callback(f"⏳ 客户端 {account.alias} 尚未登录完成，跳过本次发帖任务")
            return False

        try:
            # 获取频道
            if self.log_callback:
                self.log_callback(f"🔍 查找频道: {task.channel_id}")
            channel = client.get_channel(task.channel_id)
            if not channel:
                try:
                    channel = await client.fetch_channel(task.channel_id)
                except Exception as fetch_error:
                    channel = None
                    if self.log_callback:
                        self.log_callback(f"❌ 找不到频道 {task.channel_id}: {fetch_error}")
                        # 列出所有可用频道
                        guilds = client.guilds
                        for guild in guilds:
                            self.log_callback(f"  服务器: {guild.name} ({guild.id})")
                            for ch in guild.channels:
                                if hasattr(ch, 'id'):
                                    self.log_callback(f"    频道: {ch.name} ({ch.id})")
                    return False

            if self.log_callback:
                self.log_callback(f"✅ 找到频道: {channel.name} ({channel.id}) 类型: {type(channel).__name__}")

            # 发送消息前处理图片路径
            # 支持多个图片，用分号或逗号分隔
            image_paths = []
            if task.image_path:
                # 按分号或逗号分割，支持多个图片路径
                separators = [';', ',']
                for sep in separators:
                    if sep in task.image_path:
                        image_paths = [path.strip() for path in task.image_path.split(sep) if path.strip()]
                        break
                else:
                    # 单个图片路径
                    image_paths = [task.image_path]

                # 过滤出存在的文件
                image_paths = [path for path in image_paths if os.path.exists(path)]

            # 检查频道类型
            import discord
            if isinstance(channel, discord.ForumChannel):
                if self.log_callback:
                    self.log_callback(f"⚠️ 检测到论坛频道，需要创建帖子才能发消息")
                # 对于论坛频道，我们需要创建一个新的帖子
                try:
                    tags_to_use = task.tags if task.tags else self.default_posting_tags
                    if isinstance(tags_to_use, str):
                        separators = [';', ',', '\n']
                        for sep in separators:
                            if sep in tags_to_use:
                                tags_to_use = [t.strip() for t in tags_to_use.split(sep) if t.strip()]
                                break
                        else:
                            tags_to_use = [tags_to_use.strip()] if tags_to_use.strip() else []
                    # 准备参数
                    thread_kwargs = {
                        'name': task.title or f"自动发帖 {task.id}",
                        'content': task.content
                    }

                    # 只在有图片时添加files参数
                    if image_paths:
                        thread_kwargs['files'] = [discord.File(path) for path in image_paths]

                    # 论坛标签
                    available_tags = getattr(channel, "available_tags", None) or getattr(channel, "tags", None) or []
                    if tags_to_use and available_tags:
                        applied_tags = []
                        for tag_value in tags_to_use:
                            tag_text = str(tag_value).strip()
                            if not tag_text:
                                continue
                            matched_tag = None
                            if tag_text.isdigit():
                                matched_tag = next((t for t in available_tags if str(getattr(t, "id", "")) == tag_text), None)
                            else:
                                matched_tag = next((t for t in available_tags if getattr(t, "name", "").lower() == tag_text.lower()), None)
                            if matched_tag:
                                applied_tags.append(matched_tag)
                            elif self.log_callback:
                                self.log_callback(f"⚠️ 找不到标签: {tag_text}")

                        if applied_tags:
                            thread_kwargs['applied_tags'] = applied_tags
                        elif self.log_callback and tags_to_use:
                            self.log_callback("⚠️ 未匹配到任何标签，可能导致发帖失败")

                    # 创建论坛帖子
                    thread = await channel.create_thread(**thread_kwargs)
                    if self.log_callback:
                        # ThreadWithMessage 可能没有 name 属性，使用 id 或其他标识符
                        thread_name = getattr(thread, 'name', None) or getattr(thread.thread, 'name', f'帖子-{task.id}')
                        self.log_callback(f"✅ [{account.alias}] 论坛发帖成功: 创建帖子 '{thread_name}'")
                    # 增加发帖计数
                    task.sent_count += 1
                    task.last_sent_at = time.time()
                    self.posting_sent_total += 1
                    if runtime is not None:
                        runtime["count_since_rotation"] = int(runtime.get("count_since_rotation", 0)) + 1
                    else:
                        self.posting_count_since_rotation += 1
                    return True
                except discord.HTTPException as e:
                    if e.code == 20016:
                        interval_base = self.posting_interval
                        if runtime is not None:
                            interval_base = max(0, int(runtime.get("posting_interval", interval_base)))
                        retry_after = getattr(e, "retry_after", None) or interval_base or 60
                        task.next_run_at = time.time() + max(1, retry_after)
                        if self.log_callback:
                            self.log_callback(f"⚠️ [{account.alias}] 慢速模式限制，{int(retry_after)}秒后重试")
                    elif self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 论坛发帖失败: HTTP {e.code}")
                    return False
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 论坛发帖失败: {str(e)}")
                    return False

            # 构建发送内容
            send_content = task.content
            if task.title:
                send_content = f"**{task.title}**\n\n{send_content}"

            if image_paths:
                # 发送图片
                files = [discord.File(path) for path in image_paths]
                if send_content.strip():
                    await channel.send(send_content, files=files)
                else:
                    await channel.send(files=files)
            else:
                # 只发送文字
                await channel.send(send_content)

            # 增加发帖计数
            task.sent_count += 1
            task.last_sent_at = time.time()
            self.posting_sent_total += 1
            if runtime is not None:
                runtime["count_since_rotation"] = int(runtime.get("count_since_rotation", 0)) + 1
            else:
                self.posting_count_since_rotation += 1

            if self.log_callback:
                rotation_enabled_log = self.posting_rotation_enabled if runtime is None else bool(runtime.get("rotation_enabled", self.posting_rotation_enabled))
                rotation_count_log = self.posting_rotation_count if runtime is None else max(1, int(runtime.get("rotation_count", self.posting_rotation_count)))
                rotation_num_log = self.posting_count_since_rotation if runtime is None else int(runtime.get("count_since_rotation", 0))
                rotation_info = f" (轮换计数: {rotation_num_log}/{rotation_count_log})" if rotation_enabled_log else ""
                self.log_callback(f"✅ [{account.alias}] 发帖成功: '{task.content[:50]}...'{rotation_info}")

            return True

        except discord.HTTPException as e:
            if e.code == 20016:
                interval_base = self.posting_interval
                if runtime is not None:
                    interval_base = max(0, int(runtime.get("posting_interval", interval_base)))
                retry_after = getattr(e, "retry_after", None) or interval_base or 60
                task.next_run_at = time.time() + max(1, retry_after)
                if self.log_callback:
                    self.log_callback(f"⚠️ [{account.alias}] 慢速模式限制，{int(retry_after)}秒后重试")
            elif self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 发帖失败: HTTP {e.code}")
            return False
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 发帖失败: {str(e)}")
            return False

    async def execute_comment_task(self, task: CommentTask, runtime: Optional[Dict] = None) -> bool:
        """执行评论任务"""
        runtime_enabled = self.comment_enabled if runtime is None else runtime.get("enabled", True)
        if not runtime_enabled:
            return False

        # 获取下一个可用的账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
        account_tokens = self.comment_account_tokens
        if runtime is not None:
            account_tokens = runtime.get("account_tokens", account_tokens)

        if account_tokens:
            available_accounts = [acc for acc in available_accounts if acc.token in account_tokens]
        if not available_accounts:
            if self.log_callback:
                self.log_callback("❌ 没有可用的账号用于评论")
            return False

        rotation_enabled = self.comment_rotation_enabled
        rotation_count = max(1, int(self.comment_rotation_count))
        comment_index = self.current_comment_index
        comment_count_since_rotation = self.comment_count_since_rotation
        if runtime is not None:
            rotation_enabled = bool(runtime.get("rotation_enabled", rotation_enabled))
            rotation_count = max(1, int(runtime.get("rotation_count", rotation_count)))
            comment_index = int(runtime.get("current_index", comment_index))
            comment_count_since_rotation = int(runtime.get("count_since_rotation", comment_count_since_rotation))

        # 选择账号
        if rotation_enabled and comment_count_since_rotation >= rotation_count:
            # 轮换到下一个账号
            comment_index = (comment_index + 1) % len(available_accounts)
            comment_count_since_rotation = 0
            if self.log_callback:
                self.log_callback(f"🔄 评论账号轮换到下一个")

        account = available_accounts[comment_index % len(available_accounts)]

        # 如果不是轮换模式，仍然正常轮换
        if not rotation_enabled:
            comment_index = (comment_index + 1) % len(available_accounts)

        if runtime is not None:
            runtime["current_index"] = comment_index
            runtime["count_since_rotation"] = comment_count_since_rotation
        else:
            self.current_comment_index = comment_index
            self.comment_count_since_rotation = comment_count_since_rotation

        # 查找对应的客户端
        client = next((c for c in self.clients if c.account.token == account.token), None)
        if not client:
            if self.log_callback:
                self.log_callback(f"❌ 找不到账号 {account.alias} 的客户端")
            return False

        # 检查客户端是否已经登录成功
        if not client.is_running:
            if self.log_callback:
                self.log_callback(f"⏳ 客户端 {account.alias} 尚未登录完成，跳过本次评论任务")
            return False

        try:
            links_input = task.message_link.strip()

            separators = ['\n', ';', ',']
            links = []
            for sep in separators:
                if sep in links_input:
                    links = [link.strip() for link in links_input.split(sep) if link.strip()]
                    break
            else:
                links = [links_input] if links_input else []

            success_count = 0
            link_interval = max(0, self.comment_link_interval)
            if runtime is not None:
                link_interval = max(0, int(runtime.get("comment_link_interval", link_interval)))

            for index, link in enumerate(links):
                if not runtime_enabled:
                    if self.log_callback:
                        self.log_callback("⏹️ 自动评论已关闭，停止当前评论任务")
                    break

                # 兼容 <https://...>、末尾斜杠、<#频道ID> 等复制格式
                link = link.strip().strip('<>').rstrip('/')
                if link.startswith("<#") and link.endswith(">"):
                    link = link[2:-1]

                if link.isdigit():
                    try:
                        channel_id = int(link)
                        target_id = None
                    except ValueError:
                        if self.log_callback:
                            self.log_callback(f"❌ 无效的频道ID: {link}")
                        continue
                else:
                    parts = link.split('/')
                    if len(parts) >= 7:
                        try:
                            channel_id = int(parts[-2])
                            target_id = int(parts[-1])
                        except (ValueError, IndexError) as e:
                            if self.log_callback:
                                self.log_callback(f"❌ 无法解析链接: {link} - {str(e)}")
                            continue
                    elif len(parts) >= 6:
                        try:
                            channel_id = int(parts[-1])
                            target_id = None
                        except (ValueError, IndexError) as e:
                            if self.log_callback:
                                self.log_callback(f"❌ 无法解析链接: {link} - {str(e)}")
                            continue
                    else:
                        if self.log_callback:
                            self.log_callback(f"❌ 无效的链接格式: {link}")
                        continue

                channel = client.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await client.fetch_channel(channel_id)
                    except Exception as fetch_error:
                        channel = None
                        if self.log_callback:
                            self.log_callback(f"❌ 找不到频道 {channel_id}: {fetch_error}")
                        continue

                target_channel = channel
                message = None

                if target_id is None:
                    pass
                else:
                    try:
                        potential_message = await channel.fetch_message(target_id)
                        if hasattr(potential_message, 'thread') and potential_message.thread:
                            target_channel = potential_message.thread
                        else:
                            message = potential_message
                    except discord.NotFound:
                        if self.log_callback:
                            self.log_callback(f"❌ 找不到消息: {target_id}")
                        continue

                if task.delay_seconds > 0:
                    await asyncio.sleep(task.delay_seconds)

                image_paths = []
                if task.image_path:
                    separators = [';', ',']
                    for sep in separators:
                        if sep in task.image_path:
                            image_paths = [path.strip() for path in task.image_path.split(sep) if path.strip()]
                            break
                    else:
                        image_paths = [task.image_path]
                    image_paths = [path for path in image_paths if os.path.exists(path)]

                if self.log_callback:
                    self.log_callback(f"💬 [{account.alias}] 准备评论: {link}")

                try:
                    if image_paths:
                        files = [discord.File(path) for path in image_paths]
                        if task.content.strip():
                            if message:
                                await message.reply(task.content, files=files)
                            else:
                                await target_channel.send(task.content, files=files)
                        else:
                            if message:
                                await message.reply(files=files)
                            else:
                                await target_channel.send(files=files)
                    else:
                        if task.content.strip():
                            if message:
                                await message.reply(task.content)
                            else:
                                await target_channel.send(task.content)
                        else:
                            if message:
                                await message.reply()
                            else:
                                await target_channel.send()
                except discord.HTTPException as e:
                    if e.code == 20016:
                        interval_base = self.comment_interval
                        if runtime is not None:
                            interval_base = max(0, int(runtime.get("comment_interval", interval_base)))
                        retry_after = getattr(e, "retry_after", None) or interval_base or 60
                        task.next_run_at = time.time() + max(1, retry_after)
                        if self.log_callback:
                            self.log_callback(f"⚠️ [{account.alias}] 慢速模式限制，{int(retry_after)}秒后重试")
                    elif self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 评论失败: HTTP {e.code}")
                    return False

                success_count += 1
                if self.log_callback:
                    self.log_callback(f"✅ [{account.alias}] 评论成功: {link}")

                if link_interval > 0 and index < len(links) - 1:
                    if self.log_callback:
                        self.log_callback(f"⏳ 等待 {link_interval} 秒后继续下一条评论")
                    await asyncio.sleep(link_interval)

            if self.log_callback:
                self.log_callback(f"✅ [{account.alias}] 成功发送 {success_count}/{len(links)} 条评论")

            if success_count > 0:
                task.sent_count += 1
                task.last_sent_at = time.time()
                self.comment_sent_total += success_count

            if runtime is not None:
                runtime["count_since_rotation"] = int(runtime.get("count_since_rotation", 0)) + 1
            else:
                self.comment_count_since_rotation += 1
            return True

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 评论失败: {str(e)}")
            return False

    async def start_posting_scheduler(self):
        """启动发帖调度器（支持多页面独立运行）"""
        if self.posting_scheduler_running:
            return
        self.posting_scheduler_running = True

        default_contexts = None

        try:
            if self.log_callback:
                self.log_callback(f"📝 发帖调度器开始运行 - 任务数量: {len(self.posting_tasks)}")

            running_clients = [c for c in self.clients if c.is_running]
            wait_count = 0
            max_waits = 15
            while self.posting_enabled and not running_clients and wait_count < max_waits:
                if self.log_callback:
                    self.log_callback("⏳ 发帖调度器等待客户端登录...")
                await asyncio.sleep(2)
                wait_count += 1
                running_clients = [c for c in self.clients if c.is_running]

            if not self.workspace_posting_contexts:
                runtime_tasks = [copy.deepcopy(task) for task in self.posting_tasks]
                for task in runtime_tasks:
                    if task.is_active:
                        task.next_run_at = None
                        task.sent_count = 0

                start_at = self.posting_start_at
                if start_at is None:
                    start_delay = max(0, self.posting_start_delay)
                    start_at = time.time() + start_delay if start_delay > 0 else None

                default_contexts = {
                    "default": {
                        "enabled": self.posting_enabled,
                        "name": "默认页面",
                        "tasks": runtime_tasks,
                        "cursor": 0,
                        "posting_interval": max(0, int(self.posting_interval)),
                        "cycle_interval": max(0, int(self.posting_cycle_interval)),
                        "repeat_enabled": bool(self.posting_repeat_enabled),
                        "start_at": start_at,
                        "account_tokens": list(self.posting_account_tokens),
                        "rotation_enabled": bool(self.posting_rotation_enabled),
                        "rotation_count": max(1, int(self.posting_rotation_count)),
                        "current_index": int(self.current_posting_index),
                        "count_since_rotation": int(self.posting_count_since_rotation),
                        "_initialized": False,
                    }
                }

            while self.posting_enabled:
                try:
                    contexts = self.workspace_posting_contexts if self.workspace_posting_contexts else (default_contexts or {})

                    if not contexts:
                        self.runtime_posting_tasks = []
                        await asyncio.sleep(1)
                        continue

                    now = time.time()
                    candidates = []
                    all_runtime_tasks = []

                    for context_key, context in contexts.items():
                        if not context.get("enabled", False):
                            continue

                        tasks = context.get("tasks", [])
                        all_runtime_tasks.extend(tasks)

                        active_tasks = [task for task in tasks if task.is_active]
                        if not context.get("repeat_enabled", False):
                            active_tasks = [task for task in active_tasks if getattr(task, "sent_count", 0) == 0]

                        if not active_tasks:
                            continue

                        cursor = int(context.get("cursor", 0))
                        if cursor >= len(active_tasks):
                            cursor = 0
                            context["cursor"] = 0

                        if not context.get("_initialized", False):
                            start_at = context.get("start_at")
                            if start_at is not None and start_at < now:
                                start_at = None
                                context["start_at"] = None
                            if start_at is not None:
                                active_tasks[cursor].next_run_at = start_at
                            context["_initialized"] = True

                        scheduled_tasks = [task for task in active_tasks if task.next_run_at is not None]
                        target_task = min(scheduled_tasks, key=lambda t: t.next_run_at) if scheduled_tasks else active_tasks[cursor]
                        due_at = target_task.next_run_at if target_task.next_run_at is not None else now
                        candidates.append((due_at, context_key, context, target_task))

                    self.runtime_posting_tasks = all_runtime_tasks

                    if not candidates:
                        await asyncio.sleep(1)
                        continue

                    due_at, context_key, context, task = min(candidates, key=lambda x: x[0])
                    now = time.time()

                    if due_at > now:
                        sleep_seconds = max(1.0, min(5.0, due_at - now))
                        await asyncio.sleep(sleep_seconds)
                        continue

                    context_name = context.get("name", context_key)
                    if self.log_callback:
                        self.log_callback(f"📝 [{context_name}] 开始执行发帖任务: {task.id}")

                    success = await self.execute_posting_task(task, runtime=context)

                    interval = max(0, int(context.get("posting_interval", self.posting_interval)))
                    cycle_interval = max(0, int(context.get("cycle_interval", interval)))

                    active_tasks = [t for t in context.get("tasks", []) if t.is_active]
                    if not context.get("repeat_enabled", False):
                        active_tasks = [t for t in active_tasks if getattr(t, "sent_count", 0) == 0]

                    if success:
                        if context.get("repeat_enabled", False):
                            if active_tasks:
                                if task in active_tasks:
                                    current_index = active_tasks.index(task)
                                else:
                                    current_index = int(context.get("cursor", 0))
                                next_index = (current_index + 1) % len(active_tasks)
                                context["cursor"] = next_index
                                task.next_run_at = None
                                next_task = active_tasks[next_index]
                                delay_seconds = cycle_interval if next_index == 0 else interval
                                next_task.next_run_at = time.time() + delay_seconds
                        else:
                            task.next_run_at = None
                            if active_tasks:
                                if task in active_tasks:
                                    current_index = active_tasks.index(task)
                                else:
                                    current_index = int(context.get("cursor", 0))
                                if current_index >= len(active_tasks):
                                    current_index = 0
                                context["cursor"] = current_index
                                next_task = active_tasks[current_index]
                                next_task.next_run_at = time.time() + interval
                    else:
                        if task.next_run_at is None:
                            task.next_run_at = time.time() + interval

                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"❌ 发帖调度器错误: {str(e)}")

                await asyncio.sleep(1)

        finally:
            if default_contexts and "default" in default_contexts:
                default_context = default_contexts["default"]
                self.current_posting_index = int(default_context.get("current_index", self.current_posting_index))
                self.posting_count_since_rotation = int(default_context.get("count_since_rotation", self.posting_count_since_rotation))

            self.runtime_posting_tasks = []
            self.posting_scheduler_running = False

    async def start_comment_scheduler(self):
        """启动评论调度器（支持多页面独立运行）"""
        if self.comment_scheduler_running:
            return
        self.comment_scheduler_running = True

        default_contexts = None

        try:
            running_clients = [c for c in self.clients if c.is_running]
            wait_count = 0
            max_waits = 15
            while self.comment_enabled and not running_clients and wait_count < max_waits:
                if self.log_callback:
                    self.log_callback("⏳ 评论调度器等待客户端登录...")
                await asyncio.sleep(2)
                wait_count += 1
                running_clients = [c for c in self.clients if c.is_running]

            if not self.workspace_comment_contexts:
                runtime_tasks = [copy.deepcopy(task) for task in self.comment_tasks]
                for task in runtime_tasks:
                    if task.is_active:
                        task.next_run_at = None
                        task.sent_count = 0

                start_at = self.comment_start_at
                if start_at is None:
                    start_delay = max(0, self.comment_start_delay)
                    start_at = time.time() + start_delay if start_delay > 0 else None

                default_contexts = {
                    "default": {
                        "enabled": self.comment_enabled,
                        "name": "默认页面",
                        "tasks": runtime_tasks,
                        "cursor": 0,
                        "comment_interval": max(0, int(self.comment_interval)),
                        "cycle_interval": max(0, int(self.comment_cycle_interval)),
                        "repeat_enabled": bool(self.comment_repeat_enabled),
                        "start_at": start_at,
                        "comment_link_interval": max(0, int(self.comment_link_interval)),
                        "account_tokens": list(self.comment_account_tokens),
                        "rotation_enabled": bool(self.comment_rotation_enabled),
                        "rotation_count": max(1, int(self.comment_rotation_count)),
                        "current_index": int(self.current_comment_index),
                        "count_since_rotation": int(self.comment_count_since_rotation),
                        "_initialized": False,
                    }
                }

            while self.comment_enabled:
                try:
                    contexts = self.workspace_comment_contexts if self.workspace_comment_contexts else (default_contexts or {})

                    if not contexts:
                        self.runtime_comment_tasks = []
                        await asyncio.sleep(1)
                        continue

                    now = time.time()
                    candidates = []
                    all_runtime_tasks = []

                    for context_key, context in contexts.items():
                        if not context.get("enabled", False):
                            continue

                        tasks = context.get("tasks", [])
                        all_runtime_tasks.extend(tasks)

                        active_tasks = [task for task in tasks if task.is_active]
                        if not context.get("repeat_enabled", False):
                            active_tasks = [task for task in active_tasks if getattr(task, "sent_count", 0) == 0]

                        if not active_tasks:
                            continue

                        cursor = int(context.get("cursor", 0))
                        if cursor >= len(active_tasks):
                            cursor = 0
                            context["cursor"] = 0

                        if not context.get("_initialized", False):
                            start_at = context.get("start_at")
                            if start_at is not None and start_at < now:
                                start_at = None
                                context["start_at"] = None
                            if start_at is not None:
                                active_tasks[cursor].next_run_at = start_at
                            context["_initialized"] = True

                        scheduled_tasks = [task for task in active_tasks if task.next_run_at is not None]
                        target_task = min(scheduled_tasks, key=lambda t: t.next_run_at) if scheduled_tasks else active_tasks[cursor]
                        due_at = target_task.next_run_at if target_task.next_run_at is not None else now
                        candidates.append((due_at, context_key, context, target_task))

                    self.runtime_comment_tasks = all_runtime_tasks

                    if not candidates:
                        await asyncio.sleep(1)
                        continue

                    due_at, context_key, context, task = min(candidates, key=lambda x: x[0])
                    now = time.time()

                    if due_at > now:
                        sleep_seconds = max(1.0, min(5.0, due_at - now))
                        await asyncio.sleep(sleep_seconds)
                        continue

                    context_name = context.get("name", context_key)
                    if self.log_callback:
                        self.log_callback(f"💬 [{context_name}] 开始执行评论任务: {task.id}")

                    success = await self.execute_comment_task(task, runtime=context)

                    interval = max(0, int(context.get("comment_interval", self.comment_interval)))
                    cycle_interval = max(0, int(context.get("cycle_interval", interval)))

                    active_tasks = [t for t in context.get("tasks", []) if t.is_active]
                    if not context.get("repeat_enabled", False):
                        active_tasks = [t for t in active_tasks if getattr(t, "sent_count", 0) == 0]

                    if success:
                        if context.get("repeat_enabled", False):
                            if active_tasks:
                                if task in active_tasks:
                                    current_index = active_tasks.index(task)
                                else:
                                    current_index = int(context.get("cursor", 0))
                                next_index = (current_index + 1) % len(active_tasks)
                                context["cursor"] = next_index
                                task.next_run_at = None
                                next_task = active_tasks[next_index]
                                delay_seconds = cycle_interval if next_index == 0 else interval
                                next_task.next_run_at = time.time() + delay_seconds
                        else:
                            task.next_run_at = None
                            if active_tasks:
                                if task in active_tasks:
                                    current_index = active_tasks.index(task)
                                else:
                                    current_index = int(context.get("cursor", 0))
                                if current_index >= len(active_tasks):
                                    current_index = 0
                                context["cursor"] = current_index
                                next_task = active_tasks[current_index]
                                next_task.next_run_at = time.time() + interval
                    else:
                        if task.next_run_at is None:
                            task.next_run_at = time.time() + interval

                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"❌ 评论调度器错误: {str(e)}")

                await asyncio.sleep(1)

        finally:
            if default_contexts and "default" in default_contexts:
                default_context = default_contexts["default"]
                self.current_comment_index = int(default_context.get("current_index", self.current_comment_index))
                self.comment_count_since_rotation = int(default_context.get("count_since_rotation", self.comment_count_since_rotation))

            self.runtime_comment_tasks = []
            self.comment_scheduler_running = False



class LicenseManager:
    """许可证激活管理器"""

    def __init__(self, license_server_url: str = "http://107.172.1.7:8888",
                 client_username: str = "client", client_password: str = "",
                 admin_username: str = None, admin_password: str = None,
                 api_path: str = "/api/v1"):
        self.license_server_url = license_server_url.rstrip('/')
        self.api_path = api_path  # 保留兼容字段，当前激活接口不依赖该路径
        self.client_username = client_username
        self.client_password = client_password
        self.admin_username = admin_username  # 兼容字段，当前激活接口无需管理员认证
        self.admin_password = admin_password  # 兼容字段，当前激活接口无需管理员认证
        self.license_key: Optional[str] = None
        self.machine_fingerprint: str = self._generate_machine_fingerprint()
        self.is_activated: bool = False
        self.license_info: Optional[Dict] = None

    def _generate_machine_fingerprint(self) -> str:
        """生成机器指纹"""
        try:
            mac = ':'.join(
                ['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0, 48, 8)]
            )[:17]
            system_info = f"{platform.machine()}-{platform.system()}-{mac}"
            return hashlib.sha256(system_info.encode()).hexdigest()[:32].upper()
        except Exception:
            return uuid.uuid4().hex.upper()[:32]

    async def validate_license(self, license_key: str) -> Tuple[bool, str]:
        """验证许可证（当前使用激活接口）"""
        return await self._activate_license(license_key)

    async def activate_license(self, license_key: str) -> Tuple[bool, str]:
        """激活许可证并绑定到当前机器"""
        return await self._activate_license(license_key)

    async def _activate_license(self, license_key: str) -> Tuple[bool, str]:
        """激活许可证，绑定到当前机器"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                activate_url = f"{self.license_server_url}/api/activate"
                payload = {
                    "key": license_key,
                    "hwid": self.machine_fingerprint
                }

                async with session.post(activate_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "success":
                            self.is_activated = True
                            self.license_key = license_key
                            self.license_info = data
                            return True, data.get("msg", "激活成功")
                        return False, data.get("detail", "激活失败")
                    if response.status == 403:
                        return False, "该密钥已被其他设备激活，无法重复使用"
                    if response.status == 404:
                        return False, "密钥不存在或已失效"
                    return False, f"服务器错误: HTTP {response.status}"

        except asyncio.TimeoutError:
            return False, "连接服务器超时，请检查网络"
        except Exception as e:
            return False, f"网络错误: {str(e)}"

    def deactivate_license(self):
        """注销许可证"""
        self.license_key = None
        self.is_activated = False
        self.license_info = None

    def is_license_valid(self) -> bool:
        """检查许可证是否有效"""
        return self.is_activated and self.license_key is not None

    def get_license_info(self) -> Optional[Dict]:
        """获取许可证信息"""
        return self.license_info
