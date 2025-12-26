import asyncio
import discord
import re
import random
import time
import logging
from typing import List, Dict, Optional, Tuple
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
    rule_ids: List[str] = None  # 关联的规则ID列表

    def __post_init__(self):
        if self.rule_ids is None:
            self.rule_ids = []

    @property
    def alias(self) -> str:
        """获取账号别名（使用用户名）"""
        if self.user_info:
            return f"{self.user_info.get('name', 'Unknown')}#{self.user_info.get('discriminator', '0000')}"
        return f"Token-{self.token[:8]}..."


@dataclass
class Rule:
    id: str  # 规则唯一标识
    keywords: List[str]
    reply: str
    match_type: MatchType
    target_channels: List[int]
    delay_min: float = 2.0
    delay_max: float = 5.0
    is_active: bool = True


class AutoReplyClient(discord.Client):
    def __init__(self, account: Account, rules: List[Rule], log_callback=None, *args, **kwargs):
        # discord.py-self 不需要Intents，直接使用默认设置
        super().__init__(*args, **kwargs)
        self.account = account
        self.rules = rules
        self.is_running = False
        self.log_callback = log_callback  # 日志回调函数

    async def on_ready(self):
        self.is_running = True
        message = f"[{self.account.alias}] 登录成功: {self.user}"
        print(message)
        if self.log_callback:
            self.log_callback(message)

    async def on_message(self, message):
        # 不要回复自己，避免死循环
        if message.author == self.user:
            return

        # 遍历规则
        for rule in self.rules:
            if not rule.is_active:
                continue

            # 检查频道限制
            if rule.target_channels and message.channel.id not in rule.target_channels:
                continue

            # 检查关键词匹配
            should_reply = self._check_match(message.content, rule)

            if should_reply:
                # 只在匹配时记录日志
                match_msg = f"[{self.account.alias}] 🎯 匹配到关键词 | 消息: '{message.content}' | 来自: {message.author.name} | 频道: #{message.channel.name}"
                reply_msg = f"[{self.account.alias}] 🤖 准备回复原消息: '{rule.reply}'"

                print(match_msg)
                print(reply_msg)
                if self.log_callback:
                    self.log_callback(match_msg)
                    self.log_callback(reply_msg)

                try:
                    # 随机延迟（防封控）
                    delay = random.uniform(rule.delay_min, rule.delay_max)
                    delay_msg = f"[{self.account.alias}] ⏱️  等待 {delay:.1f} 秒后回复..."
                    print(delay_msg)
                    if self.log_callback:
                        self.log_callback(delay_msg)

                    # 尝试显示正在输入状态（可能需要权限）
                    try:
                        async with message.channel.typing():
                            await asyncio.sleep(delay)
                    except Exception as typing_error:
                        # 如果没有权限显示正在输入，直接等待
                        typing_warning = f"[{self.account.alias}] ⚠️ 无法显示正在输入状态（权限不足），直接等待..."
                        print(typing_warning)
                        if self.log_callback:
                            self.log_callback(typing_warning)
                        await asyncio.sleep(delay)

                    await message.reply(rule.reply)
                    success_msg = f"[{self.account.alias}] ✅ 回复成功发送（已回复原消息）"
                    print(success_msg)
                    if self.log_callback:
                        self.log_callback(success_msg)

                    # 命中一条规则后是否继续匹配其他规则？通常break
                    break

                except discord.Forbidden as e:
                    # 处理权限错误
                    error_code = getattr(e, 'code', 'unknown')
                    if error_code == 50001:
                        error_msg = f"[{self.account.alias}] ❌ 回复失败：缺少频道权限（无法在此频道发送消息）"
                    else:
                        error_msg = f"[{self.account.alias}] ❌ 回复失败：权限被拒绝 (错误码: {error_code})"
                    print(error_msg)
                    if self.log_callback:
                        self.log_callback(error_msg)

                except discord.HTTPException as e:
                    # 处理其他HTTP错误
                    status = getattr(e, 'status', 'unknown')
                    error_msg = f"[{self.account.alias}] ❌ 回复失败：HTTP错误 {status}"
                    print(error_msg)
                    if self.log_callback:
                        self.log_callback(error_msg)

                except Exception as e:
                    error_msg = f"[{self.account.alias}] ❌ 回复失败: {e}"
                    print(error_msg)
                    import traceback
                    detailed_error = f"[{self.account.alias}] 详细错误: {traceback.format_exc()}"
                    print(detailed_error)
                    if self.log_callback:
                        self.log_callback(error_msg)
                        self.log_callback(detailed_error)
                break  # 确保只处理第一个匹配的规则

    def _check_match(self, content: str, rule: Rule) -> bool:
        """检查消息内容是否匹配规则"""
        content_lower = content.lower()

        if rule.match_type == MatchType.PARTIAL:
            return any(keyword.lower() in content_lower for keyword in rule.keywords)
        elif rule.match_type == MatchType.EXACT:
            return content_lower in [k.lower() for k in rule.keywords]
        elif rule.match_type == MatchType.REGEX:
            return any(re.search(keyword, content, re.IGNORECASE) for keyword in rule.keywords)

        return False

    async def start_client(self):
        """启动客户端"""
        try:
            # 重置运行状态
            self.is_running = False
            await self.start(self.account.token, reconnect=True)
            # 等待on_ready事件被触发，最多等待15秒
            await asyncio.sleep(1)  # 给一点时间让连接建立
            if not self.is_running:
                # 如果还没连接成功，等待更长时间
                try:
                    await asyncio.wait_for(self.wait_for('ready', timeout=10.0), timeout=10.0)
                except asyncio.TimeoutError:
                    log_msg = f"[{self.account.alias}] 连接超时"
                    print(log_msg)
                    if self.log_callback:
                        self.log_callback(log_msg)
                    self.is_running = False
        except discord.LoginFailure as e:
            log_msg = f"[{self.account.alias}] 登录失败: Token无效"
            print(log_msg)
            if self.log_callback:
                self.log_callback(log_msg)
            self.is_running = False
        except Exception as e:
            error_str = str(e)
            if "SSL" in error_str or "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in error_str:
                log_msg = f"[{self.account.alias}] SSL连接错误，通常是网络问题，请稍后重试"
                print(log_msg)
                if self.log_callback:
                    self.log_callback(log_msg)
            else:
                log_msg = f"[{self.account.alias}] 启动失败: {error_str}"
                print(log_msg)
                if self.log_callback:
                    self.log_callback(log_msg)
                import traceback
                detailed_error = f"[{self.account.alias}] 详细错误: {traceback.format_exc()}"
                print(detailed_error)
                if self.log_callback:
                    self.log_callback(detailed_error)
            self.is_running = False

    async def stop_client(self):
        """停止客户端"""
        self.is_running = False
        await self.close()


class TokenValidator:
    """Discord Token验证器"""

    @staticmethod
    async def validate_token(token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        验证Discord Token
        返回: (是否有效, 用户信息, 错误信息)
        """
        # 首先尝试使用HTTP API验证（更稳定）
        http_result = await TokenValidator._validate_token_http(token)
        if http_result[0] is not None:  # HTTP验证成功或明确失败
            return http_result

        # 如果HTTP验证失败，尝试WebSocket验证作为备选
        print("HTTP验证失败，尝试WebSocket验证...")
        return await TokenValidator._validate_token_websocket(token)

    @staticmethod
    async def _validate_token_http(token: str) -> Tuple[Optional[bool], Optional[Dict], Optional[str]]:
        """
        使用HTTP API验证Token
        """
        import aiohttp

        # 首先进行基本的Token格式检查
        token = token.strip()
        if not token:
            return False, None, "Token不能为空"

        # 检查基本格式
        if len(token) < 20:
            return False, None, "Token长度不正确（太短）"

        # Discord Token通常包含多个点号分隔的部分
        if token.count('.') < 2:
            return False, None, "Token格式不正确（缺少必要的分隔符）"

        # 检查是否包含常见的前缀模式
        parts = token.split('.')
        if len(parts) < 3:
            return False, None, "Token格式不正确（部分不完整）"

        # 检查第一部分是否是有效的base64编码（通常是数字开头）
        import base64
        try:
            # 尝试解码第一部分，看是否是有效的base64
            first_part = parts[0]
            # Discord Token的第一部分通常是base64编码的
            decoded = base64.b64decode(first_part + '==')  # 添加填充
        except Exception:
            return False, None, "Token格式不正确（编码无效）"

        headers = {
            'Authorization': token.strip(),
            'User-Agent': 'DiscordBot/1.0'
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)  # 10秒超时
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 获取当前用户信息
                async with session.get('https://discord.com/api/v10/users/@me', headers=headers) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        user_info = {
                            'id': user_data.get('id', 'unknown'),
                            'name': user_data.get('username', 'unknown'),
                            'discriminator': user_data.get('discriminator', '0000'),
                            'avatar_url': None,
                            'bot': user_data.get('bot', False)
                        }

                        # 获取头像URL
                        if user_data.get('avatar'):
                            user_info['avatar_url'] = f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"

                        return True, user_info, None

                    elif response.status == 401:
                        return False, None, "Token无效或已过期"
                    elif response.status == 429:
                        return False, None, "请求过于频繁，请稍后再试"
                    else:
                        error_text = await response.text()
                        return False, None, f"API错误 ({response.status}): {error_text[:100]}"

        except asyncio.TimeoutError:
            return False, None, "验证超时，请检查网络连接"
        except aiohttp.ClientError as e:
            return None, None, f"网络连接失败: {str(e)}"  # 返回None表示需要尝试WebSocket
        except Exception as e:
            return None, None, f"HTTP验证异常: {str(e)}"  # 返回None表示需要尝试WebSocket

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
            validation_error = None

            @client.event
            async def on_ready():
                nonlocal user_info, validation_error
                try:
                    # 检查client.user是否存在
                    if not client.user:
                        validation_error = "无法获取用户信息：client.user为None"
                        await client.close()
                        return

                    # Token有效，获取用户信息
                    avatar_url = None
                    try:
                        if hasattr(client.user, 'avatar') and client.user.avatar:
                            avatar_url = str(client.user.avatar.url)
                    except Exception as e:
                        print(f"头像URL获取失败: {e}")
                        avatar_url = None

                    user_info = {
                        'id': str(client.user.id) if client.user.id else "unknown",
                        'name': client.user.name if client.user.name else "unknown",
                        'discriminator': getattr(client.user, 'discriminator', '0000'),
                        'avatar_url': avatar_url,
                        'bot': getattr(client.user, 'bot', False)
                    }

                except AttributeError as e:
                    validation_error = f"用户信息属性错误: {str(e)}"
                except Exception as e:
                    validation_error = f"获取用户信息失败: {str(e)}"
                finally:
                    # 断开连接
                    try:
                        await client.close()
                    except Exception as close_error:
                        print(f"客户端关闭失败: {close_error}")

            # 尝试登录
            await client.start(token)

            # 等待on_ready事件完成或超时
            try:
                await asyncio.wait_for(client.wait_for('ready', timeout=10.0), timeout=10.0)

                if validation_error:
                    return False, None, validation_error

                if user_info:
                    return True, user_info, None
                else:
                    return False, None, "获取用户信息失败：user_info为空"

            except asyncio.TimeoutError:
                return False, None, "验证超时：等待ready事件超时"
            except Exception as e:
                return False, None, f"验证过程中出错: {str(e)}"

        except discord.LoginFailure as e:
            error_msg = str(e)
            if "Improper token" in error_msg:
                return False, None, "Token格式错误或无效，请检查Token是否正确复制"
            elif "401" in error_msg or "Unauthorized" in error_msg:
                return False, None, "Token已过期或无效，请重新获取Token"
            else:
                return False, None, f"登录失败: {error_msg}"
        except discord.HTTPException as e:
            status = getattr(e, 'status', 'unknown')
            if status == 401:
                return False, None, "Token无效或已过期（401 Unauthorized）"
            elif status == 403:
                return False, None, "Token权限不足（403 Forbidden）"
            elif status == 429:
                return False, None, "请求过于频繁，请稍后再试（429 Rate Limited）"
            else:
                return False, None, f"Discord API错误 ({status}): {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return False, None, "连接超时，请检查网络连接"
            elif "connection" in error_msg.lower():
                return False, None, "网络连接失败，请检查网络设置"
            else:
                return False, None, f"验证失败: {error_msg}"
        finally:
            # 确保客户端被正确关闭
            if client:
                try:
                    await client.close()
                except Exception as close_error:
                    print(f"最终客户端关闭失败: {close_error}")


class DiscordManager:
    def __init__(self, log_callback=None):
        self.clients: List[AutoReplyClient] = []
        self.accounts: List[Account] = []
        self.rules: List[Rule] = []
        self.is_running = False
        self.validator = TokenValidator()
        self.log_callback = log_callback

    async def add_account_async(self, token: str) -> Tuple[bool, Optional[str]]:
        """异步添加账号（包含Token验证）"""
        # 检查Token是否已存在
        if any(acc.token == token for acc in self.accounts):
            return False, "该Token已存在"

        # 验证Token
        is_valid, user_info, error_msg = await self.validator.validate_token(token)

        # 创建账号对象
        account = Account(
            token=token,
            is_active=True,
            is_valid=is_valid,
            last_verified=time.time(),
            user_info=user_info
        )

        self.accounts.append(account)

        if is_valid and user_info:
            username = f"{user_info['name']}#{user_info['discriminator']}"
            return True, f"账号添加成功，用户名: {username}"
        else:
            return True, f"账号添加成功，但Token无效: {error_msg}"

    def add_account(self, token: str, alias: str):
        """添加账号（同步版本，用于向后兼容）"""
        account = Account(token=token, alias=alias)
        self.accounts.append(account)

    def remove_account(self, token: str):
        """移除账号"""
        self.accounts = [acc for acc in self.accounts if acc.token != token]

    def add_rule(self, keywords: List[str], reply: str, match_type: MatchType,
                 target_channels: List[int], delay_min: float = 2.0, delay_max: float = 5.0):
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
            delay_max=delay_max
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
        """启动所有客户端"""
        if self.is_running:
            return

        self.is_running = True

        # 清除之前的客户端
        await self.stop_all_clients()
        self.clients.clear()

        # 启动所有有效的客户端
        tasks = []
        for account in self.accounts:
            if account.is_active and account.is_valid:
                # 获取该账号关联的规则
                account_rules = [rule for rule in self.rules if rule.id in account.rule_ids]
                client = AutoReplyClient(account, account_rules, log_callback=self.log_callback)
                self.clients.append(client)
                # 创建启动任务
                task = asyncio.create_task(client.start_client())
                tasks.append(task)

        # 等待所有客户端启动完成（或失败）
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                log_msg = f"所有客户端启动完成，共 {len(self.clients)} 个客户端"
                print(log_msg)
                if self.log_callback:
                    self.log_callback(log_msg)
            except Exception as e:
                log_msg = f"客户端启动过程中出现错误: {e}"
                print(log_msg)
                if self.log_callback:
                    self.log_callback(log_msg)

        # 记录最终状态
        running_clients = [c for c in self.clients if c.is_running]
        status_msg = f"运行中的客户端: {len(running_clients)} / {len(self.clients)}"
        print(status_msg)
        if self.log_callback:
            self.log_callback(status_msg)

        if running_clients:
            success_msg = "✅ 自动回复功能已启用！"
            print(success_msg)
            if self.log_callback:
                self.log_callback(success_msg)
        else:
            warning_msg = "⚠️ 没有客户端成功启动，请检查Token是否有效"
            print(warning_msg)
            if self.log_callback:
                self.log_callback(warning_msg)

    async def stop_all_clients(self):
        """停止所有客户端"""
        self.is_running = False

        if not self.clients:
            return

        stop_msg = f"正在停止 {len(self.clients)} 个客户端..."
        print(stop_msg)
        if self.log_callback:
            self.log_callback(stop_msg)

        # 停止所有客户端
        stop_tasks = []
        for client in self.clients:
            try:
                stop_tasks.append(client.stop_client())
            except Exception as e:
                error_msg = f"停止客户端 {client.account.alias} 时出错: {e}"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)

        if stop_tasks:
            try:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
                success_msg = "所有客户端已停止"
                print(success_msg)
                if self.log_callback:
                    self.log_callback(success_msg)
            except Exception as e:
                error_msg = f"停止客户端时出现错误: {e}"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)

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

        if is_valid and user_info:
            username = f"{user_info['name']}#{user_info['discriminator']}"
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
