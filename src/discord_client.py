import asyncio
import discord
import re
import random
import time
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
    is_valid: bool = False  # Token验证状态
    last_verified: Optional[float] = None  # 最后验证时间
    user_info: Optional[Dict] = None  # 用户信息
    last_sent_time: Optional[float] = None  # 最后发送消息时间
    rate_limit_until: Optional[float] = None  # 频率限制到期时间

    @property
    def alias(self) -> str:
        """获取账号别名（使用用户名）"""
        if self.user_info and isinstance(self.user_info, dict):
            return f"{self.user_info.get('name', 'Unknown')}#{self.user_info.get('discriminator', '0000')}"
        return f"Token-{self.token[:8]}..."


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

    def __post_init__(self):
        # 只有当created_at为None时才设置当前时间
        # 这样可以保留从配置加载的原始创建时间
        if self.created_at is None:
            self.created_at = time.time()


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

    def __post_init__(self):
        # 只有当created_at为None时才设置当前时间
        # 这样可以保留从配置加载的原始创建时间
        if self.created_at is None:
            self.created_at = time.time()


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
        for rule in self.rules:
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
                    if (self.discord_manager and
                        self.discord_manager.rotation_enabled and
                        rule.target_channels and
                        message.channel.id in rule.target_channels):
                        # 使用轮换模式
                        success = await self.discord_manager.send_rotated_reply(
                            message, rule.reply, rule.keywords[0] if rule.keywords else ""
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
            error_msg = f"[{self.account.alias}] 登录失败: Token无效 - {e}"
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
            return False, None, "Token为空"

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
            return False, None, "所有验证方法都失败，请检查Token和网络连接"

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
        if not token: return False, None, "Token为空"

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
                        return False, None, "Token无效"
                    elif resp.status == 403:
                        return False, None, "Token权限不足"
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
            return False, None, "Token登录失败"
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

        # 功能启用状态
        self.reply_enabled: bool = False  # 是否启用自动回复
        self.posting_enabled: bool = False  # 是否启用自动发帖
        self.comment_enabled: bool = False  # 是否启用自动评论

        # 发帖和评论管理
        self.posting_tasks: List[PostingTask] = []  # 发帖任务列表
        self.comment_tasks: List[CommentTask] = []  # 评论任务列表
        self.posting_interval: int = 30  # 发帖间隔（秒），默认30秒
        self.comment_interval: int = 30  # 评论间隔（秒），默认30秒
        self.current_posting_index: int = 0  # 当前发帖账号索引
        self.current_comment_index: int = 0  # 当前评论账号索引

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
        # 重新创建LicenseManager实例
        self.license_manager = LicenseManager(
            license_server_url=self.license_manager.license_server_url,
            client_username=username,
            client_password=password,
            api_path=api_path
        )

    async def add_account_async(self, token: str) -> Tuple[bool, Optional[str]]:
        if any(acc.token == token for acc in self.accounts):
            return False, "Token已存在"

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
                 case_sensitive: bool = False, image_path: Optional[str] = None):
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
            image_path=image_path
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

    async def start_all_clients(self):
        if self.is_running: return

        self.is_running = True

        await self.stop_all_clients()
        self.clients.clear()

        for acc in self.accounts:
            if acc.is_active and acc.is_valid:
                # 所有客户端都使用所有规则，规则级别控制账号选择
                client = AutoReplyClient(acc, self.rules, self.log_callback, self)
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
        """重新验证所有账号的Token"""
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

    def get_next_available_account(self) -> Optional[Account]:
        """获取下一个可用的账号（用于轮换）"""
        if not self.rotation_enabled or not self.accounts:
            return None

        # 查找所有有效的活跃账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]

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

    async def send_rotated_reply(self, message, reply_text: str, rule_name: str = "") -> bool:
        """使用轮换账号发送回复"""
        if not self.rotation_enabled:
            return False

        # 检查这条消息是否已经被回复过
        if message.id in self.replied_messages:
            if self.log_callback:
                self.log_callback(f"⚠️ 消息 {message.id} 已被回复，跳过轮换回复")
            return False

        account = self.get_next_available_account()
        if not account:
            if self.log_callback:
                self.log_callback(f"❌ 所有账号都被频率限制，无法发送回复")
            return False

        # 查找对应的客户端
        client = next((c for c in self.clients if c.account.token == account.token), None)
        if not client:
            if self.log_callback:
                self.log_callback(f"❌ 找不到账号 {account.alias} 的客户端")
            return False

        try:
            # 标记这条消息已被回复
            self.replied_messages.add(message.id)

            # 清理过期的消息ID（保持内存使用合理）
            if len(self.replied_messages) > self.max_replied_messages:
                # 移除最旧的一半消息
                sorted_messages = sorted(self.replied_messages)
                remove_count = len(sorted_messages) // 2
                for msg_id in sorted_messages[:remove_count]:
                    self.replied_messages.remove(msg_id)

            # 更新账号的最后发送时间
            current_time = time.time()
            account.last_sent_time = current_time

            # 发送消息
            await message.reply(reply_text)

            # 移动到下一个账号
            available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
            if available_accounts:
                self.current_rotation_index = (self.current_rotation_index + 1) % len(available_accounts)

            if self.log_callback:
                self.log_callback(f"✅ [{account.alias}] 轮换回复成功: '{reply_text[:50]}...'")

            return True

        except discord.HTTPException as e:
            # 检查是否是频率限制错误
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

            # 尝试下一个账号
            return await self.send_rotated_reply(message, reply_text, rule_name)

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 发送异常: {str(e)}")
            return False

    async def revalidate_account(self, token: str) -> Tuple[bool, Optional[str]]:
        """重新验证指定账号的Token"""
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
            "active_rules": len([r for r in self.rules if r.is_active])
        }

    # ============ 发帖和评论功能 ============

    def add_posting_task(self, content: str, channel_id: int, image_path: Optional[str] = None, delay_seconds: int = 0, title: Optional[str] = None):
        """添加发帖任务"""
        import time
        task_id = f"post_{int(time.time() * 1000)}_{len(self.posting_tasks)}"

        task = PostingTask(
            id=task_id,
            title=title,
            content=content,
            image_path=image_path,
            channel_id=channel_id,
            delay_seconds=delay_seconds
        )
        self.posting_tasks.append(task)

        if self.log_callback:
            self.log_callback(f"📝 发帖任务已添加: {task_id}")
            if title:
                self.log_callback(f"  标题: '{title}'")
            self.log_callback(f"  内容: '{content[:50]}{'...' if len(content) > 50 else ''}'")
            self.log_callback(f"  频道ID: {channel_id}")
            self.log_callback(f"  延迟: {delay_seconds}秒")
            self.log_callback(f"  图片: {image_path if image_path else '无'}")

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

    async def execute_posting_task(self, task: PostingTask) -> bool:
        """执行发帖任务"""
        if self.log_callback:
            self.log_callback(f"🔍 执行发帖任务: ID={task.id}, 频道={task.channel_id}, 内容='{task.content[:50]}...'")

        if not self.posting_enabled:
            if self.log_callback:
                self.log_callback("❌ 发帖功能未启用")
            return False

        # 验证频道ID格式
        try:
            channel_id_int = int(task.channel_id)
            if self.log_callback:
                self.log_callback(f"✅ 频道ID格式正确: {channel_id_int}")
        except ValueError:
            if self.log_callback:
                self.log_callback(f"❌ 频道ID格式错误: {task.channel_id}")
            return False

        # 获取下一个可用的账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
        if not available_accounts:
            if self.log_callback:
                self.log_callback("❌ 没有可用的账号用于发帖")
            return False

        if self.log_callback:
            self.log_callback(f"✅ 找到 {len(available_accounts)} 个可用账号")

        # 选择账号
        if self.posting_rotation_enabled and self.posting_count_since_rotation >= self.posting_rotation_count:
            # 轮换到下一个账号
            self.current_posting_index = (self.current_posting_index + 1) % len(available_accounts)
            self.posting_count_since_rotation = 0
            if self.log_callback:
                self.log_callback(f"🔄 发帖账号轮换到下一个")

        account = available_accounts[self.current_posting_index % len(available_accounts)]

        # 如果不是轮换模式，仍然正常轮换
        if not self.posting_rotation_enabled:
            self.current_posting_index = (self.current_posting_index + 1) % len(available_accounts)

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
                if self.log_callback:
                    self.log_callback(f"❌ 找不到频道 {task.channel_id}")
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
                    # 准备参数
                    thread_kwargs = {
                        'name': task.title or f"自动发帖 {task.id}",
                        'content': task.content
                    }

                    # 只在有图片时添加files参数
                    if image_paths:
                        thread_kwargs['files'] = [discord.File(path) for path in image_paths]

                    # 创建论坛帖子
                    thread = await channel.create_thread(**thread_kwargs)
                    if self.log_callback:
                        # ThreadWithMessage 可能没有 name 属性，使用 id 或其他标识符
                        thread_name = getattr(thread, 'name', None) or getattr(thread.thread, 'name', f'帖子-{task.id}')
                        self.log_callback(f"✅ [{account.alias}] 论坛发帖成功: 创建帖子 '{thread_name}'")
                    # 增加发帖计数
                    self.posting_count_since_rotation += 1
                    # 移除已完成的任务
                    self.posting_tasks.remove(task)
                    return True
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 论坛发帖失败: {str(e)}")
                    return False

            # 延迟执行
            if task.delay_seconds > 0:
                await asyncio.sleep(task.delay_seconds)

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
            self.posting_count_since_rotation += 1

            if self.log_callback:
                rotation_info = f" (轮换计数: {self.posting_count_since_rotation}/{self.posting_rotation_count})" if self.posting_rotation_enabled else ""
                self.log_callback(f"✅ [{account.alias}] 发帖成功: '{task.content[:50]}...'{rotation_info}")

            # 移除已完成的任务
            self.posting_tasks.remove(task)
            return True

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 发帖失败: {str(e)}")
            return False

    async def execute_comment_task(self, task: CommentTask) -> bool:
        """执行评论任务"""
        if not self.comment_enabled:
            return False

        # 获取下一个可用的账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
        if not available_accounts:
            if self.log_callback:
                self.log_callback("❌ 没有可用的账号用于评论")
            return False

        # 选择账号
        if self.comment_rotation_enabled and self.comment_count_since_rotation >= self.comment_rotation_count:
            # 轮换到下一个账号
            self.current_comment_index = (self.current_comment_index + 1) % len(available_accounts)
            self.comment_count_since_rotation = 0
            if self.log_callback:
                self.log_callback(f"🔄 评论账号轮换到下一个")

        account = available_accounts[self.current_comment_index % len(available_accounts)]

        # 如果不是轮换模式，仍然正常轮换
        if not self.comment_rotation_enabled:
            self.current_comment_index = (self.current_comment_index + 1) % len(available_accounts)

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
            for link in links:
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
                    if len(parts) >= 6:
                        try:
                            channel_id = int(parts[-1])
                            target_id = None
                            if len(parts) >= 7:
                                target_id = int(parts[-2])
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
                    if self.log_callback:
                        self.log_callback(f"❌ 找不到频道 {channel_id}")
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

                success_count += 1

            if self.log_callback:
                self.log_callback(f"✅ [{account.alias}] 成功发送 {success_count}/{len(links)} 条评论")

            self.comment_count_since_rotation += 1

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 评论失败: {str(e)}")
            return False

    async def start_posting_scheduler(self):
        """启动发帖调度器"""
        if self.log_callback:
            self.log_callback(f"📝 发帖调度器开始运行 - 任务数量: {len(self.posting_tasks)}")

        # 等待至少有一个客户端登录成功
        if self.log_callback:
            self.log_callback(f"📝 开始等待客户端登录 - 当前客户端数量: {len(self.clients)}")

        # 首先检查是否已经有登录的客户端
        running_clients = [c for c in self.clients if c.is_running]
        if running_clients and self.log_callback:
            self.log_callback(f"📝 发现已有 {len(running_clients)} 个已登录客户端，开始处理发帖任务")
        else:
            # 等待客户端登录，最多等待30秒
            wait_count = 0
            max_waits = 15  # 15次检查 = 30秒
            while self.posting_enabled and wait_count < max_waits:
                running_clients = [c for c in self.clients if c.is_running]
                if self.log_callback:
                    import time
                    current_time = time.time()
                    self.log_callback(f"📝 等待检查 #{wait_count} - 运行中客户端: {len(running_clients)}/{len(self.clients)} (时间: {current_time:.1f})")
                    # 显示每个客户端的状态
                    for i, client in enumerate(self.clients):
                        self.log_callback(f"  客户端 {i}: {client.account.alias}, 运行状态: {client.is_running}")

                if running_clients:
                    if self.log_callback:
                        self.log_callback(f"📝 检测到 {len(running_clients)} 个已登录客户端，开始处理发帖任务")
                    break

                if self.log_callback:
                    self.log_callback("⏳ 等待客户端登录完成...")
                await asyncio.sleep(2)  # 每2秒检查一次
                wait_count += 1

            # 如果等待超时但仍有任务，记录警告
            if not running_clients and self.posting_enabled and self.posting_tasks and self.log_callback:
                self.log_callback("⚠️ 等待客户端登录超时，将在客户端登录后重试任务执行")

        while self.posting_enabled:
            try:
                # 检查是否有待执行的发帖任务
                current_time = time.time()

                if self.log_callback:
                    self.log_callback(f"📝 检查任务 - 当前时间: {current_time:.1f}, 任务数量: {len(self.posting_tasks)}, 启用: {self.posting_enabled}, 运行中: {self.is_running}")

                if self.log_callback and self.posting_tasks:
                    for task in self.posting_tasks:
                        remaining_time = (task.created_at + task.delay_seconds) - current_time
                        status = "可执行" if remaining_time <= 0 else f"等待{remaining_time:.1f}秒"
                        self.log_callback(f"  任务 {task.id}: 活跃={task.is_active}, 创建时间={task.created_at:.1f}, 当前时间={current_time:.1f}, 延迟={task.delay_seconds}, 剩余={remaining_time:.1f}秒, {status}")

                pending_tasks = [task for task in self.posting_tasks
                               if task.is_active and
                               current_time >= task.created_at + task.delay_seconds]

                if self.log_callback:
                    self.log_callback(f"📝 找到 {len(pending_tasks)} 个待执行的任务")

                for task in pending_tasks:
                    if self.log_callback:
                        self.log_callback(f"📝 开始执行发帖任务: {task.id}")
                    success = await self.execute_posting_task(task)
                    if success and self.log_callback:
                        self.log_callback(f"📝 发帖任务 {task.id} 执行成功")
                    elif not success and self.log_callback:
                        self.log_callback(f"📝 发帖任务 {task.id} 执行失败")

                    # 发帖间隔
                    if self.posting_interval > 0:
                        if self.log_callback:
                            self.log_callback(f"📝 等待发帖间隔: {self.posting_interval}秒")
                        await asyncio.sleep(self.posting_interval)

            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"❌ 发帖调度器错误: {str(e)}")

            await asyncio.sleep(10)  # 检查间隔

    async def start_comment_scheduler(self):
        """启动评论调度器"""
        # 等待至少有一个客户端登录成功
        # 首先检查是否已经有登录的客户端
        running_clients = [c for c in self.clients if c.is_running]
        if running_clients and self.log_callback:
            self.log_callback(f"💬 发现已有 {len(running_clients)} 个已登录客户端，开始处理评论任务")
        else:
            # 等待客户端登录，最多等待30秒
            wait_count = 0
            max_waits = 15  # 15次检查 = 30秒
            while self.comment_enabled and wait_count < max_waits:
                running_clients = [c for c in self.clients if c.is_running]
                if running_clients:
                    if self.log_callback:
                        self.log_callback(f"💬 检测到 {len(running_clients)} 个已登录客户端，开始处理评论任务")
                    break

                if self.log_callback:
                    self.log_callback("⏳ 等待客户端登录完成...")
                await asyncio.sleep(2)  # 每2秒检查一次
                wait_count += 1

            # 如果等待超时但仍有任务，记录警告
            if not running_clients and self.comment_enabled and self.comment_tasks and self.log_callback:
                self.log_callback("⚠️ 等待客户端登录超时，将在客户端登录后重试任务执行")

        while self.comment_enabled:
            try:
                # 检查是否有待执行的评论任务
                current_time = time.time()
                pending_tasks = [task for task in self.comment_tasks
                               if task.is_active and
                               current_time >= task.created_at + task.delay_seconds]

                for task in pending_tasks:
                    await self.execute_comment_task(task)
                    # 评论间隔
                    if self.comment_interval > 0:
                        await asyncio.sleep(self.comment_interval)

            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"❌ 评论调度器错误: {str(e)}")

            await asyncio.sleep(10)  # 检查间隔



class LicenseManager:
    """License Mate许可证管理系统"""

    def __init__(self, license_server_url: str = "https://license.thy1cc.top",
                 client_username: str = "client", client_password: str = "",
                 api_path: str = "/api/v1"):
        self.license_server_url = license_server_url.rstrip('/')
        self.api_path = api_path  # API路径，如 /api/v1
        self.client_username = client_username
        self.client_password = client_password
        self.license_key: Optional[str] = None
        self.machine_fingerprint: str = self._generate_machine_fingerprint()
        self.is_activated: bool = False
        self.license_info: Optional[Dict] = None

    def _generate_machine_fingerprint(self) -> str:
        """生成机器指纹"""
        # 获取系统信息
        system_info = platform.uname()
        node = system_info.node
        machine = system_info.machine

        # 创建唯一指纹
        fingerprint_data = f"{node}-{machine}-{uuid.getnode()}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    async def validate_license(self, license_key: str) -> Tuple[bool, str]:
        """验证许可证"""
        try:
            # 设置认证
            auth = None
            if self.client_username and self.client_password:
                auth = aiohttp.BasicAuth(self.client_username, self.client_password)

            async with aiohttp.ClientSession(auth=auth) as session:
                # 验证许可证
                validate_url = f"{self.license_server_url}{self.api_path}/validate"
                params = {"_id": license_key}

                async with session.get(validate_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("message") == "License is valid":
                            # 检查是否需要绑定机器
                            license_details = data.get("license-details", {})
                            machine_node = license_details.get("machine-node")

                            if machine_node == "NOT_ACTIVATED":
                                # 需要激活，绑定到当前机器
                                success, msg = await self._activate_license(license_key)
                                if success:
                                    self.license_key = license_key
                                    self.is_activated = True
                                    self.license_info = license_details
                                    return True, f"许可证激活成功: {license_details.get('name', 'Unknown')}"
                                else:
                                    return False, f"许可证激活失败: {msg}"
                            elif machine_node == self.machine_fingerprint:
                                # 已绑定到当前机器
                                self.license_key = license_key
                                self.is_activated = True
                                self.license_info = license_details
                                return True, f"许可证有效: {license_details.get('name', 'Unknown')}"
                            else:
                                # 已绑定到其他机器
                                return False, "此许可证已绑定到其他设备"

                    elif response.status == 202:
                        data = await response.json()
                        if data.get("message") == "License is expired":
                            return False, "许可证已过期"

                    elif response.status == 404:
                        return False, "许可证不存在"

                    else:
                        return False, f"验证失败: HTTP {response.status}"

        except Exception as e:
            return False, f"网络错误: {str(e)}"

        return False, "未知错误"

    async def _activate_license(self, license_key: str) -> Tuple[bool, str]:
        """激活许可证，绑定到当前机器"""
        try:
            # 设置认证
            auth = None
            if self.client_username and self.client_password:
                auth = aiohttp.BasicAuth(self.client_username, self.client_password)

            async with aiohttp.ClientSession(auth=auth) as session:
                # 更新许可证信息，绑定到当前机器
                update_url = f"{self.license_server_url}{self.api_path}/update"
                payload = {
                    "_id": license_key,
                    "machine-node": self.machine_fingerprint,
                    "machine-sn": int(time.time())  # 使用时间戳作为序列号
                }

                async with session.patch(update_url, json=payload) as response:
                    if response.status == 200:
                        return True, "激活成功"
                    else:
                        return False, f"激活失败: HTTP {response.status}"

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

