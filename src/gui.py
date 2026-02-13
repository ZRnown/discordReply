import sys
import asyncio
import time
import os
import json
import csv
import copy
import uuid
from typing import List, Optional, Dict
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTabBar, QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QInputDialog,
    QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog, QSplitter, QProgressBar,
    QDialog, QMenu, QScrollArea, QFrame, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap

from .discord_client import DiscordManager, Account, Rule, MatchType
from .config_manager import ConfigManager


class LicenseVerifyThread(QThread):
    """许可证验证工作线程"""
    finished = Signal(bool, str)  # success, message
    error = Signal(str)  # error_message

    def __init__(self, license_manager, license_key, activate=False):
        super().__init__()
        self.license_manager = license_manager
        self.license_key = license_key
        self.activate = activate

    def run(self):
        """在线程中运行异步验证"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if self.activate:
                # 执行验证并激活
                success, message = loop.run_until_complete(
                    self.license_manager.activate_license(self.license_key)
                )
            else:
                # 仅验证，不激活
                success, message = loop.run_until_complete(
                    self.license_manager.validate_license(self.license_key)
                )

            # 发送结果信号
            self.finished.emit(success, message)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()


class LicenseServerTestThread(QThread):
    """许可证服务器连接测试工作线程"""
    finished = Signal(bool, str)  # success, message

    def __init__(self, license_manager):
        super().__init__()
        self.license_manager = license_manager

    def run(self):
        """在线程中测试服务器连接"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 测试基本的服务器连接（通过验证一个不存在的许可证）
            success, message = loop.run_until_complete(
                self.license_manager.validate_license("test-connection-key")
            )

            # 如果返回"密钥不存在"，说明服务器连接正常
            if "密钥不存在" in message or "已失效" in message:
                self.finished.emit(True, "服务器连接正常")
            else:
                self.finished.emit(False, f"连接测试失败: {message}")

        except Exception as e:
            self.finished.emit(False, f"网络错误: {str(e)}")
        finally:
            loop.close()


class AccountDialog(QDialog):
    """账号添加/编辑对话框"""
    def __init__(self, parent=None, account=None, discord_manager=None):
        super().__init__(parent)
        self.account = account
        self.discord_manager = discord_manager
        self.is_validating = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("添加账号" if not self.account else "编辑账号")
        self.setModal(True)
        self.resize(500, 250)

        layout = QVBoxLayout(self)

        # 账号输入
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("账号:"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("输入账号")
        if self.account:
            self.token_input.setText(self.account.token)
        self.token_input.textChanged.connect(self.on_token_changed)
        token_layout.addWidget(self.token_input)

        # 验证按钮
        self.validate_btn = QPushButton("验证账号")
        self.validate_btn.clicked.connect(self.validate_token)
        token_layout.addWidget(self.validate_btn)

        # 帮助按钮
        help_btn = QPushButton("❓")
        help_btn.setMaximumWidth(30)
        help_btn.setToolTip("如何获取账号")
        help_btn.clicked.connect(self.show_token_help)
        token_layout.addWidget(help_btn)

        layout.addLayout(token_layout)

        # 验证状态显示
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        self.status_label.setWordWrap(True)  # 允许换行
        layout.addWidget(self.status_label)

        # 显示当前用户信息（如果有的话）
        if self.account and self.account.user_info and isinstance(self.account.user_info, dict):
            user_info = self.account.user_info
            username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
            info_label = QLabel(f"当前账号: {username}")
            info_label.setStyleSheet("color: blue; font-weight: bold;")
            layout.addWidget(info_label)

        # 激活状态
        self.active_checkbox = QCheckBox("启用账号")
        self.active_checkbox.setChecked(True if not self.account else self.account.is_active)
        layout.addWidget(self.active_checkbox)

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept_and_validate)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)

        # 如果是编辑模式，显示当前验证状态
        if self.account:
            self.update_validation_status()

    def on_token_changed(self):
        """账号输入改变时重置验证状态"""
        if not self.is_validating:
            self.status_label.setText("")
            self.status_label.setStyleSheet("color: gray; font-style: italic;")

    def update_validation_status(self):
        """更新验证状态显示"""
        if self.account and self.account.last_verified:
            if self.account.is_valid and self.account.user_info and isinstance(self.account.user_info, dict):
                user_info = self.account.user_info
                username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
                self.status_label.setText(f"✅ 账号有效 - 用户名: {username}")
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText("❌ 账号无效或已过期")
                self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setText("⚠️ 账号未验证")
            self.status_label.setStyleSheet("color: orange;")

    async def validate_token_async(self):
        """异步验证账号"""
        token = self.token_input.text().strip()
        if not token:
            self.status_label.setText("❌ 请输入账号")
            self.status_label.setStyleSheet("color: red;")
            return

        self.is_validating = True
        self.validate_btn.setEnabled(False)
        self.validate_btn.setText("验证中...")
        self.status_label.setText("🔄 正在验证账号，请稍候...")
        self.status_label.setStyleSheet("color: blue;")

        # 强制更新UI
        QApplication.processEvents()

        try:
            # 更新状态：正在连接
            self.status_label.setText("🔗 正在连接服务器...")
            self.status_label.setStyleSheet("color: blue;")
            QApplication.processEvents()

            # 导入验证器
            from discord_client import TokenValidator
            validator = TokenValidator()

            # 执行验证
            is_valid, user_info, error_msg = await validator.validate_token(token)

            if is_valid and user_info and isinstance(user_info, dict):
                username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
                bot_status = "🤖 机器人账号" if user_info.get('bot', False) else "👤 用户账号"
                self.status_label.setText(f"✅ 账号有效\n{bot_status}\n👤 用户名: {username}\n🔗 验证成功！")
                self.status_label.setStyleSheet("color: green;")
            else:
                # 提供更友好的错误信息
                if "401" in error_msg or "Unauthorized" in error_msg:
                    friendly_msg = "账号无效或已过期，请重新获取"
                elif "Improper token" in error_msg:
                    friendly_msg = "账号格式错误，请检查是否正确复制"
                elif "429" in error_msg:
                    friendly_msg = "请求过于频繁，请稍后再试"
                elif "403" in error_msg:
                    friendly_msg = "账号权限不足"
                elif "timeout" in error_msg.lower():
                    friendly_msg = "连接超时，请检查网络"
                elif "格式" in error_msg:
                    friendly_msg = error_msg
                else:
                    friendly_msg = "账号验证失败，请检查账号是否正确"

                self.status_label.setText(f"❌ 账号无效\n💡 {friendly_msg}\n🔍 原始错误: {error_msg}")
                self.status_label.setStyleSheet("color: red;")

        except Exception as e:
            self.status_label.setText(f"❌ 验证出错: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.is_validating = False
            self.validate_btn.setEnabled(True)
            self.validate_btn.setText("验证账号")

    def validate_token(self):
        """验证账号（同步包装器）"""
        # 创建新的事件循环来运行异步验证
        # 注意：这会暂时阻塞GUI，但在PySide6不使用qasync的情况下，这是处理短时间异步任务的简单方法
        try:
            # 显示验证开始状态
            self.status_label.setText("🔄 正在验证账号，请稍候...")
            self.status_label.setStyleSheet("color: blue;")
            QApplication.processEvents()  # 强制更新UI

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.validate_token_async())
            loop.close()
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            self.status_label.setText(f"❌ 验证系统错误: {error_msg}")
            self.status_label.setStyleSheet("color: red;")

    def show_token_help(self):
        """显示账号获取帮助"""
        help_text = """
        <h3>如何获取账号</h3>

        <p><b>重要提醒：</b>请谨慎使用账号信息，不要泄露给他人！</p>

        <h4>获取用户账号（推荐用于个人使用）：</h4>
        <ol>
        <li>打开网页版或桌面客户端</li>
        <li>按 <b>F12</b> 打开开发者工具</li>
        <li>切换到 <b>Application</b> 标签页</li>
        <li>在左侧选择 <b>Local Storage</b> → <b>https://相关域名</b></li>
        <li>找到 <b>token</b> 字段</li>
        <li>复制 <b>value</b> 列的值（不包含引号）</li>
        </ol>

        <h4>账号格式示例：</h4>
        <p><code>XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX</code></p>
        <p>或</p>
        <p><code>XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX</code></p>

        <h4>常见错误：</h4>
        <ul>
        <li><b>401 Unauthorized</b>: 账号无效或已过期</li>
        <li><b>Improper token</b>: 账号格式错误</li>
        <li><b>403 Forbidden</b>: 账号权限不足</li>
        </ul>

        <p><b>注意：</b>账号可能会定期过期，建议定期更新。</p>
        """

        QMessageBox.information(self, "账号获取指南",
                               help_text, QMessageBox.StandardButton.Ok)

    def accept_and_validate(self):
        """确定并验证"""
        # 如果还没有验证过，自动验证一次
        if not self.status_label.text() or "未验证" in self.status_label.text():
            self.validate_token()

        # 检查验证结果
        if "❌" in self.status_label.text():
            reply = QMessageBox.question(
                self, "账号无效",
                "账号验证失败，确定要继续保存吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.accept()

    def get_account_data(self):
        """获取账号数据"""
        # 解析验证状态
        is_valid = "✅" in self.status_label.text()
        # 注意：这里我们不能轻易从label文本重建user_info，
        # 实际使用时会重新验证或保留原有info
        user_info = self.account.user_info if self.account else None

        # 如果刚才验证成功了，但是self.account.user_info可能没更新（因为validate只跑了一次逻辑）
        # 在这里我们简化处理：如果需要最新user_info，依赖外部重新验证

        return {
            'token': self.token_input.text().strip(),
            'is_active': self.active_checkbox.isChecked(),
            'is_valid': is_valid,
            'user_info': user_info
        }


class RuleDialog(QDialog):
    """规则添加/编辑对话框"""
    def __init__(self, parent=None, rule=None):
        super().__init__(parent)
        self.rule = rule
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("添加规则" if not self.rule else "编辑规则")
        self.setModal(True)
        self.resize(500, 350)

        layout = QVBoxLayout(self)

        # 关键词输入
        keywords_layout = QHBoxLayout()
        keywords_layout.addWidget(QLabel("关键词:"))
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("用逗号分隔多个关键词")
        if self.rule:
            self.keywords_input.setText(", ".join(self.rule.keywords))
        keywords_layout.addWidget(self.keywords_input)
        layout.addLayout(keywords_layout)

        # 回复内容
        reply_layout = QVBoxLayout()
        reply_layout.addWidget(QLabel("回复内容:"))
        self.reply_input = QTextEdit()
        self.reply_input.setMaximumHeight(80)
        if self.rule:
            self.reply_input.setText(self.rule.reply)
        reply_layout.addWidget(self.reply_input)
        layout.addLayout(reply_layout)

        # 匹配类型和频道ID
        type_channel_layout = QHBoxLayout()

        # 匹配类型
        type_layout = QVBoxLayout()
        type_layout.addWidget(QLabel("匹配类型:"))
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["partial - 部分匹配", "exact - 精确匹配", "regex - 正则表达式"])
        if self.rule:
            if self.rule.match_type.value == "partial":
                self.match_type_combo.setCurrentIndex(0)
            elif self.rule.match_type.value == "exact":
                self.match_type_combo.setCurrentIndex(1)
            else:
                self.match_type_combo.setCurrentIndex(2)
        type_layout.addWidget(self.match_type_combo)
        type_channel_layout.addLayout(type_layout)

        # 目标频道
        channel_layout = QVBoxLayout()
        channel_layout.addWidget(QLabel("频道ID (可选):"))
        self.channels_input = QLineEdit()
        self.channels_input.setPlaceholderText("为空则监听所有频道")
        if self.rule:
            self.channels_input.setText(", ".join(map(str, self.rule.target_channels)))
        channel_layout.addWidget(self.channels_input)
        type_channel_layout.addLayout(channel_layout)

        layout.addLayout(type_channel_layout)

        # 延迟设置
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("回复延迟:"))
        self.delay_min_spin = QDoubleSpinBox()
        self.delay_min_spin.setRange(0.1, 30.0)
        self.delay_min_spin.setValue(0.1 if not self.rule else self.rule.delay_min)
        self.delay_min_spin.setSuffix("秒")
        delay_layout.addWidget(self.delay_min_spin)

        delay_layout.addWidget(QLabel("-"))

        self.delay_max_spin = QDoubleSpinBox()
        self.delay_max_spin.setRange(0.1, 30.0)
        self.delay_max_spin.setValue(1.0 if not self.rule else self.rule.delay_max)
        self.delay_max_spin.setSuffix("秒")
        delay_layout.addWidget(self.delay_max_spin)

        layout.addLayout(delay_layout)

        # 激活状态
        self.active_checkbox = QCheckBox("启用规则")
        self.active_checkbox.setChecked(True if not self.rule else self.rule.is_active)
        layout.addWidget(self.active_checkbox)

        # 忽略回复消息
        self.ignore_replies_checkbox = QCheckBox("忽略回复消息")
        self.ignore_replies_checkbox.setToolTip("启用后，当有人回复别人的消息时，不会再回复这条回复消息")
        self.ignore_replies_checkbox.setChecked(True if not self.rule else getattr(self.rule, 'ignore_replies', False))
        layout.addWidget(self.ignore_replies_checkbox)

        # 忽略@消息
        self.ignore_mentions_checkbox = QCheckBox("忽略@消息")
        self.ignore_mentions_checkbox.setToolTip("启用后，当消息中包含@他人时，不会回复这条消息")
        self.ignore_mentions_checkbox.setChecked(True if not self.rule else getattr(self.rule, 'ignore_mentions', False))

        # 大小写敏感
        self.case_sensitive_checkbox = QCheckBox("不区分大小写")
        self.case_sensitive_checkbox.setToolTip("启用后，关键词匹配将不区分大小写；关闭后，将区分大小写")
        self.case_sensitive_checkbox.setChecked(True if not self.rule else not getattr(self.rule, 'case_sensitive', False))
        layout.addWidget(self.case_sensitive_checkbox)
        layout.addWidget(self.ignore_mentions_checkbox)

        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("图片回复 (可选，支持多选):"))
        self.image_path_input = QLineEdit()
        self.image_path_input.setPlaceholderText("选择图片文件路径（多个用分号或逗号分隔）...")
        if self.rule and self.rule.image_path:
            self.image_path_input.setText(self.rule.image_path)
        image_layout.addWidget(self.image_path_input)

        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self.browse_image)
        image_layout.addWidget(browse_button)

        clear_button = QPushButton("清空")
        clear_button.clicked.connect(lambda: self.image_path_input.clear())
        image_layout.addWidget(clear_button)

        layout.addLayout(image_layout)

        # 账号选择
        accounts_group = QGroupBox("使用账号 (可选)")
        accounts_layout = QVBoxLayout(accounts_group)

        accounts_layout.addWidget(QLabel("选择可使用此规则的账号（留空则随机使用所有账号）:"))
        self.accounts_list = QListWidget()
        self.accounts_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.accounts_list.setMaximumHeight(120)

        # 添加可用账号到列表
        if hasattr(self.parent(), 'discord_manager') and self.parent().discord_manager.accounts:
            for account in self.parent().discord_manager.accounts:
                if account.is_active and account.is_valid:
                    item = QListWidgetItem(f"{account.alias}")
                    item.setData(Qt.ItemDataRole.UserRole, account.token)
                    # 如果是编辑模式，检查账号是否已选中
                    if self.rule and account.token in getattr(self.rule, 'account_ids', []):
                        item.setSelected(True)
                    self.accounts_list.addItem(item)

        accounts_layout.addWidget(self.accounts_list)
        layout.addWidget(accounts_group)

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)

    def get_rule_data(self):
        """获取规则数据"""
        match_type_map = {
            0: "partial",
            1: "exact",
            2: "regex"
        }

        # 解析频道ID
        channels_text = self.channels_input.text().strip()
        target_channels = []
        if channels_text:
            try:
                target_channels = [int(c.strip()) for c in channels_text.split(",") if c.strip()]
            except ValueError:
                pass  # 忽略无效的频道ID

        # 获取选中的账号ID
        selected_account_ids = []
        for i in range(self.accounts_list.count()):
            item = self.accounts_list.item(i)
            if item.isSelected():
                selected_account_ids.append(item.data(Qt.ItemDataRole.UserRole))

        return {
            'keywords': [k.strip() for k in self.keywords_input.text().split(",") if k.strip()],
            'reply': self.reply_input.toPlainText().strip(),
            'match_type': match_type_map[self.match_type_combo.currentIndex()],
            'target_channels': target_channels,
            'delay_min': self.delay_min_spin.value(),
            'delay_max': self.delay_max_spin.value(),
            'is_active': self.active_checkbox.isChecked(),
            'ignore_replies': self.ignore_replies_checkbox.isChecked(),
            'ignore_mentions': self.ignore_mentions_checkbox.isChecked(),
            'case_sensitive': not self.case_sensitive_checkbox.isChecked(),
            'image_path': self.image_path_input.text().strip() or None,
            'account_ids': selected_account_ids,
        }

    def browse_image(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)

        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                current_text = self.image_path_input.text().strip()
                new_files = ";".join(selected_files)

                if current_text:
                    combined = current_text + ";" + new_files
                    files_list = list(set(combined.split(";")))
                    self.image_path_input.setText(";".join(files_list))
                else:
                    self.image_path_input.setText(new_files)


class WorkerThread(QThread):
    """工作线程，用于运行异步Discord客户端"""
    status_updated = Signal(dict)
    error_occurred = Signal(str)
    log_message = Signal(str)

    def __init__(self, discord_manager: DiscordManager):
        super().__init__()
        self.discord_manager = discord_manager
        self.running = False

    def run(self):
        """运行异步事件循环"""
        try:
            # 创建一个新的事件循环用于此线程
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            asyncio.run(self._run_clients())
        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _run_clients(self):
        """启动客户端并定期更新状态"""
        try:
            self.log_message.emit("开始启动客户端...")
            await self.discord_manager.start_all_clients()
            self.running = True

            # 等待所有客户端启动完成
            total_clients = len([acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid])

            if total_clients > 0:
                # 简单的等待策略：定期检查客户端状态
                max_wait_time = 15  # 最多等待15秒
                waited_time = 0

                while waited_time < max_wait_time:
                    await asyncio.sleep(1)
                    waited_time += 1

                    # 检查有多少客户端已经启动
                    running_count = len([c for c in self.discord_manager.clients if c.is_running])

                    if running_count == total_clients:
                        # 所有客户端都启动了
                        break
                    elif running_count > 0 and waited_time >= 3:
                        # 至少有一个客户端启动，且已经等待了3秒
                        self.log_message.emit(f"📊 {running_count}/{total_clients} 个客户端已连接...")
                        break

                if waited_time >= max_wait_time:
                    self.log_message.emit("⚠️ 客户端连接超时，但将继续运行")

            # 现在检查最终状态
            status = self.discord_manager.get_status()
            self.status_updated.emit(status)

            running_count = len([acc for acc in status["accounts"] if acc["is_running"]])
            total_count = len(status["accounts"])

            if running_count > 0:
                self.log_message.emit(f"✅ 客户端启动完成 - {running_count}/{total_count} 个客户端运行中")
            else:
                self.log_message.emit("❌ 客户端启动失败 - 没有客户端成功连接")

            while self.running:
                try:
                    await asyncio.sleep(5)  # 每5秒更新一次状态，与UI定时器同步
                    if self.running:  # 再次检查是否还在运行
                        status = self.discord_manager.get_status()
                        self.status_updated.emit(status)
                except asyncio.CancelledError:
                    # 任务被取消，正常退出
                    break
                except Exception as e:
                    error_msg = f"状态更新出错: {e}"
                    self.log_message.emit(error_msg)
                    # 如果是网络错误，继续运行
                    if "SSL" in str(e) or "Connection" in str(e):
                        self.log_message.emit("检测到网络连接问题，继续监控...")
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            # 任务被取消，正常停止
            self.log_message.emit("接收到停止信号，正在停止客户端...")
        except Exception as e:
            error_msg = f"客户端运行错误: {str(e)}"
            self.log_message.emit(error_msg)

            # 特殊处理SSL错误
            if "SSL" in str(e) or "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in str(e):
                self.log_message.emit("⚠️ 检测到SSL连接错误，这通常是网络问题，不影响功能")
            else:
                import traceback
                detailed_error = f"详细错误: {traceback.format_exc()}"
                self.log_message.emit(detailed_error)
                self.error_occurred.emit(error_msg)

        finally:
            # 确保在退出时停止所有客户端
            try:
                self.log_message.emit("正在清理资源...")
                await self.discord_manager.stop_all_clients()
                self.log_message.emit("客户端已完全停止")
            except Exception as cleanup_error:
                self.log_message.emit(f"清理资源时出错: {cleanup_error}")

    def stop(self):
        """停止工作线程"""
        print("正在停止工作线程...")
        self.running = False

        # 这种方式并不总是能优雅地停止 asyncio.run()，但在 WorkerThread 模型中，
        # 我们依靠 _run_clients 中的 loop check 和 sleep 来退出
        # 在GUI线程中我们只能等待 QThread 结束
        pass



class MainWindow(QMainWindow):
    # 定义信号
    log_signal = Signal(str, str)  # message, level

    def __init__(self):
        super().__init__()
        self.discord_manager = DiscordManager(log_callback=self.add_log_thread_safe)
        self.config_manager = ConfigManager()
        self.worker_thread = None
        self.workspaces = []
        self.active_workspace_index = 0

        self.init_ui()
        self.load_config()

        # 许可证验证
        self.check_license()

        # 连接日志信号
        self.log_signal.connect(self.add_log)

        # 更新许可证状态
        self.update_license_status()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("自动回复工具")
        self.setGeometry(100, 100, 1200, 800)

        # 纯红色软件图标
        red_pixmap = QPixmap(256, 256)
        red_pixmap.fill(QColor(255, 0, 0))
        self.setWindowIcon(QIcon(red_pixmap))

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局
        main_layout = QVBoxLayout(central_widget)

        # 工作区（多页面）栏
        workspace_layout = QHBoxLayout()
        workspace_layout.addWidget(QLabel("页面:"))
        self.workspace_tabbar = QTabBar()
        self.workspace_tabbar.setExpanding(False)
        self.workspace_tabbar.setMovable(False)
        self.workspace_tabbar.currentChanged.connect(self.on_workspace_changed)
        self.workspace_tabbar.tabBarDoubleClicked.connect(self.rename_workspace)
        workspace_layout.addWidget(self.workspace_tabbar)

        add_workspace_btn = QPushButton("新增页面")
        add_workspace_btn.clicked.connect(self.add_workspace)
        workspace_layout.addWidget(add_workspace_btn)

        rename_workspace_btn = QPushButton("重命名")
        rename_workspace_btn.clicked.connect(self.rename_workspace)
        workspace_layout.addWidget(rename_workspace_btn)

        delete_workspace_btn = QPushButton("删除页面")
        delete_workspace_btn.clicked.connect(self.delete_workspace)
        workspace_layout.addWidget(delete_workspace_btn)

        workspace_layout.addStretch()
        main_layout.addLayout(workspace_layout)

        # 创建标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 账号管理标签页
        self.create_accounts_tab()

        # 规则管理标签页
        self.create_rules_tab()

        # 自动发帖标签页
        self.create_posting_tab()

        # 自动评论标签页
        self.create_comment_tab()

        # 状态监控标签页
        self.create_status_tab()

        # 底部控制栏
        self.create_control_bar(main_layout)

        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                font-weight: bold;
            }
            QPushButton {
                padding: 8px 16px;
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton#start_button {
                background-color: #107c10;
            }
            QPushButton#start_button:hover {
                background-color: #0b5a0b;
            }
            QPushButton#stop_button {
                background-color: #d13438;
            }
            QPushButton#stop_button:pressed {
                background-color: #a12629;
            }
        """)

    def create_accounts_tab(self):
        """创建账号管理标签页"""
        accounts_widget = QWidget()
        layout = QVBoxLayout(accounts_widget)

        # 标题和操作按钮
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("账号管理"))

        header_layout.addStretch()

        revalidate_all_btn = QPushButton("重新验证所有")
        revalidate_all_btn.clicked.connect(self.revalidate_all_accounts)
        header_layout.addWidget(revalidate_all_btn)

        bulk_import_btn = QPushButton("一键导入账号")
        bulk_import_btn.clicked.connect(self.bulk_import_accounts)
        header_layout.addWidget(bulk_import_btn)

        add_account_btn = QPushButton("添加账号")
        add_account_btn.clicked.connect(self.add_account)
        header_layout.addWidget(add_account_btn)

        clear_accounts_btn = QPushButton("一键删除")
        clear_accounts_btn.clicked.connect(self.clear_all_accounts)
        header_layout.addWidget(clear_accounts_btn)

        layout.addLayout(header_layout)

        # 账号表格
        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(4)
        self.accounts_table.setHorizontalHeaderLabels(["序号", "账号", "账号状态", "操作"])
        self.accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.accounts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.accounts_table.customContextMenuRequested.connect(self.show_accounts_context_menu)
        layout.addWidget(self.accounts_table)

        # 统计信息
        self.accounts_stats_label = QLabel("总账号数: 0 | 启用账号数: 0")
        layout.addWidget(self.accounts_stats_label)

        self.tab_widget.addTab(accounts_widget, "账号管理")

    def create_rules_tab(self):
        """创建自动回复标签页"""
        rules_widget = QWidget()
        layout = QVBoxLayout(rules_widget)

        # 账号轮换和全局设置
        rotation_group = QGroupBox("账号轮换与全局设置")
        rotation_layout = QVBoxLayout(rotation_group)

        # 第一行：账号轮换设置
        rotation_row = QHBoxLayout()

        # 启用轮换
        self.rotation_enabled_checkbox = QCheckBox("启用账号轮换")
        self.rotation_enabled_checkbox.setToolTip("启用后，当账号被频率限制时会自动切换到其他账号发送消息")
        self.rotation_enabled_checkbox.stateChanged.connect(self.on_rotation_enabled_changed)
        rotation_row.addWidget(self.rotation_enabled_checkbox)

        rotation_row.addWidget(QLabel("轮换间隔:"))
        self.rotation_interval_spin = QSpinBox()
        self.rotation_interval_spin.setRange(1, 1440)  # 1分钟到24小时
        self.rotation_interval_spin.setValue(10)  # 默认10分钟
        self.rotation_interval_spin.setSuffix("分钟")
        self.rotation_interval_spin.setEnabled(True)  # 轮换间隔设置始终可用，用户可以预设参数
        rotation_row.addWidget(self.rotation_interval_spin)

        rotation_row.addStretch()

        # 轮换状态
        self.rotation_status_label = QLabel("轮换模式: 未启用")
        rotation_row.addWidget(self.rotation_status_label)

        rotation_layout.addLayout(rotation_row)

        # 自动回复启动倒计时
        reply_start_layout = QHBoxLayout()
        reply_start_layout.addWidget(QLabel("回复启动倒计时(秒):"))
        self.reply_start_delay_spin = QSpinBox()
        self.reply_start_delay_spin.setRange(0, 86400)
        self.reply_start_delay_spin.setValue(getattr(self.discord_manager, "reply_start_delay", 0))
        self.reply_start_delay_spin.setSuffix("秒")
        self.reply_start_delay_spin.valueChanged.connect(self.on_reply_start_delay_changed)
        reply_start_layout.addWidget(self.reply_start_delay_spin)
        self.reply_start_countdown_label = QLabel("启动倒计时: 未启用")
        reply_start_layout.addWidget(self.reply_start_countdown_label)
        reply_start_layout.addStretch()
        rotation_layout.addLayout(reply_start_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        rotation_layout.addWidget(line)

        # 第二行：自动回复账号设置
        reply_accounts_group = QGroupBox("自动回复账号设置")
        reply_accounts_layout = QVBoxLayout(reply_accounts_group)
        reply_accounts_layout.setContentsMargins(10, 10, 10, 10)

        self.reply_accounts_combo = QComboBox()
        self.reply_accounts_combo.addItem("随机使用所有账号", None)
        # 添加具体账号选项
        for account in self.discord_manager.accounts:
            if account.is_active and account.is_valid:
                self.reply_accounts_combo.addItem(f"仅使用 {account.alias}", account.token)
        self.reply_accounts_combo.setCurrentIndex(0)  # 默认随机使用所有账号

        reply_accounts_layout.addWidget(QLabel("回复账号:"))
        reply_accounts_layout.addWidget(self.reply_accounts_combo)

        # 应用按钮
        apply_reply_accounts_btn = QPushButton("应用回复账号设置")
        apply_reply_accounts_btn.clicked.connect(self.apply_global_reply_accounts)
        reply_accounts_layout.addWidget(apply_reply_accounts_btn)

        rotation_layout.addWidget(reply_accounts_group)


        layout.addWidget(rotation_group)

        # 标题和添加按钮
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("自动回复规则管理"))

        # 搜索框
        self.rule_search_input = QLineEdit()
        self.rule_search_input.setPlaceholderText("搜索关键词...")
        self.rule_search_input.textChanged.connect(self.filter_rules)
        header_layout.addWidget(self.rule_search_input)

        header_layout.addStretch()

        add_rule_btn = QPushButton("添加规则")
        add_rule_btn.clicked.connect(self.add_rule)
        header_layout.addWidget(add_rule_btn)

        import_rule_btn = QPushButton("自动读取")
        import_rule_btn.clicked.connect(self.import_reply_materials)
        header_layout.addWidget(import_rule_btn)

        clear_rules_btn = QPushButton("一键删除")
        clear_rules_btn.clicked.connect(self.clear_rules)
        header_layout.addWidget(clear_rules_btn)

        layout.addLayout(header_layout)

        # 规则表格
        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(9)
        self.rules_table.setHorizontalHeaderLabels(["关键词", "回复内容", "匹配类型", "频道", "延迟", "忽略回复", "忽略@", "账号", "操作"])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.rules_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rules_table.customContextMenuRequested.connect(self.show_rules_context_menu)
        layout.addWidget(self.rules_table)

        # 统计信息
        self.rules_stats_label = QLabel("总规则数: 0 | 启用规则数: 0")
        layout.addWidget(self.rules_stats_label)

        self.tab_widget.addTab(rules_widget, "自动回复")

        # 初始化全局账号设置组合框
        self.update_global_accounts_combo()

    def create_status_tab(self):
        """创建状态监控标签页"""
        status_widget = QWidget()
        layout = QVBoxLayout(status_widget)

        # 账号状态表格
        accounts_group = QGroupBox("账号状态监控")
        accounts_layout = QVBoxLayout(accounts_group)

        self.status_accounts_table = QTableWidget()
        self.status_accounts_table.setColumnCount(5)
        self.status_accounts_table.setHorizontalHeaderLabels(["别名", "连接状态", "自动回复", "自动发帖", "自动评论"])
        self.status_accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        accounts_layout.addWidget(self.status_accounts_table)

        layout.addWidget(accounts_group)

        # 规则统计
        rules_group = QGroupBox("规则统计")
        rules_layout = QVBoxLayout(rules_group)

        self.rules_stats_label = QLabel("总规则数: 0 | 激活规则数: 0")
        rules_layout.addWidget(self.rules_stats_label)

        layout.addWidget(rules_group)

        # 发送统计
        task_stats_group = QGroupBox("发送统计")
        task_stats_layout = QVBoxLayout(task_stats_group)
        self.task_stats_label = QLabel("已发送: 回复 0 | 发帖 0 | 评论 0")
        task_stats_layout.addWidget(self.task_stats_label)
        layout.addWidget(task_stats_group)

        # 许可证状态
        license_group = QGroupBox("许可证状态")
        license_layout = QVBoxLayout(license_group)

        # 当前许可证状态
        self.license_status_label = QLabel("未激活")
        self.license_status_label.setStyleSheet("font-weight: bold;")
        license_layout.addWidget(self.license_status_label)


        layout.addWidget(license_group)


        # 日志显示
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)

        # 日志控制按钮
        log_controls = QHBoxLayout()
        log_controls.addWidget(QLabel("日志:"))

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.clear_log)
        log_controls.addWidget(clear_log_btn)

        log_controls.addStretch()

        auto_scroll_checkbox = QCheckBox("自动滚动")
        auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_log = auto_scroll_checkbox.isChecked()
        auto_scroll_checkbox.stateChanged.connect(self.toggle_auto_scroll)
        log_controls.addWidget(auto_scroll_checkbox)

        log_layout.addLayout(log_controls)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 12))  # 等宽字体，便于查看
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        self.tab_widget.addTab(status_widget, "状态监控")


    def show_license_server_config(self):
        """显示许可证服务器配置对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("许可证服务器信息")
        dialog.setModal(True)
        dialog.resize(400, 180)

        layout = QVBoxLayout(dialog)

        # 标题
        title_label = QLabel("服务器地址已固定，无需配置")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # 服务器URL输入
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("服务器URL:"))
        self.server_url_input = QLineEdit()
        self.server_url_input.setText(self.discord_manager.license_manager.license_server_url)
        self.server_url_input.setReadOnly(True)
        url_layout.addWidget(self.server_url_input)
        layout.addLayout(url_layout)

        # 状态显示
        self.server_config_status = QLabel("")
        self.server_config_status.setStyleSheet("color: #666; margin-top: 5px;")
        layout.addWidget(self.server_config_status)

        # 按钮
        button_layout = QHBoxLayout()

        test_connection_btn = QPushButton("测试连接")
        test_connection_btn.clicked.connect(lambda: self.test_server_connection(dialog))
        button_layout.addWidget(test_connection_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def test_server_connection(self, dialog):
        """测试服务器连接"""
        server_url = self.server_url_input.text().strip()

        self.server_config_status.setText("🔄 正在测试连接...")
        self.server_config_status.setStyleSheet("color: blue;")

        # 创建临时许可证管理器进行测试
        from discord_client import LicenseManager
        test_license_manager = LicenseManager(
            license_server_url=server_url
        )

        # 在新线程中测试连接
        self.server_test_thread = LicenseServerTestThread(test_license_manager)
        self.server_test_thread.finished.connect(lambda success, message: self.on_server_test_finished(dialog, success, message))
        self.server_test_thread.start()

    def on_server_test_finished(self, dialog, success, message):
        """服务器连接测试完成"""
        if success:
            self.server_config_status.setText("✅ 连接成功")
            self.server_config_status.setStyleSheet("color: green;")
        else:
            self.server_config_status.setText(f"❌ 连接失败: {message}")
            self.server_config_status.setStyleSheet("color: red;")

    def save_server_config(self, dialog):
        """保存服务器配置"""
        QMessageBox.information(dialog, "提示", "服务器地址已固定，无需保存配置。")
        dialog.accept()

    def create_posting_tab(self):
        """创建自动发帖标签页"""
        posting_widget = QWidget()
        layout = QVBoxLayout(posting_widget)

        # 账号轮换与选择设置
        rotation_accounts_group = QGroupBox("账号轮换与选择设置")
        rotation_accounts_layout = QVBoxLayout(rotation_accounts_group)

        # 启用轮换
        self.posting_rotation_enabled_checkbox = QCheckBox("启用账号轮换")
        self.posting_rotation_enabled_checkbox.setToolTip("启用后，按发帖条数自动切换账号")
        self.posting_rotation_enabled_checkbox.stateChanged.connect(self.on_posting_rotation_enabled_changed)
        rotation_accounts_layout.addWidget(self.posting_rotation_enabled_checkbox)

        # 轮换条数设置
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("每发帖条数轮换:"))
        self.posting_rotation_count_spin = QSpinBox()
        self.posting_rotation_count_spin.setRange(1, 1000)  # 1到1000条
        self.posting_rotation_count_spin.setValue(10)  # 默认10条
        self.posting_rotation_count_spin.setSuffix("条")
        self.posting_rotation_count_spin.setEnabled(True)  # 发帖轮换条数设置始终可用，用户可以预设参数
        self.posting_rotation_count_spin.valueChanged.connect(self.on_posting_rotation_count_changed)
        count_layout.addWidget(self.posting_rotation_count_spin)
        count_layout.addStretch()
        rotation_accounts_layout.addLayout(count_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        rotation_accounts_layout.addWidget(line)

        # 账号选择
        self.posting_accounts_combo = QComboBox()
        self.posting_accounts_combo.addItem("随机使用所有账号")
        # 添加具体账号选项
        for account in self.discord_manager.accounts:
            if account.is_active and account.is_valid:
                self.posting_accounts_combo.addItem(f"仅使用 {account.alias}")
        self.posting_accounts_combo.setCurrentIndex(0)  # 默认随机使用所有账号

        rotation_accounts_layout.addWidget(QLabel("发帖账号:"))
        rotation_accounts_layout.addWidget(self.posting_accounts_combo)

        # 应用按钮
        apply_posting_accounts_btn = QPushButton("应用发帖账号设置")
        apply_posting_accounts_btn.clicked.connect(self.apply_global_posting_accounts)
        rotation_accounts_layout.addWidget(apply_posting_accounts_btn)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        rotation_accounts_layout.addWidget(line2)

        # 发帖间隔
        posting_interval_layout = QHBoxLayout()
        posting_interval_layout.addWidget(QLabel("发帖间隔(秒):"))
        self.posting_interval_spin = QSpinBox()
        self.posting_interval_spin.setRange(0, 86400)  # 0秒到24小时
        self.posting_interval_spin.setValue(30)  # 默认30秒
        self.posting_interval_spin.setSuffix("秒")
        self.posting_interval_spin.setEnabled(True)  # 发帖间隔应该始终可用
        self.posting_interval_spin.valueChanged.connect(self.on_posting_interval_changed)
        posting_interval_layout.addWidget(self.posting_interval_spin)
        posting_interval_layout.addStretch()
        rotation_accounts_layout.addLayout(posting_interval_layout)

        posting_cycle_layout = QHBoxLayout()
        posting_cycle_layout.addWidget(QLabel("循环轮次间隔(秒):"))
        self.posting_cycle_interval_spin = QSpinBox()
        self.posting_cycle_interval_spin.setRange(0, 86400)
        self.posting_cycle_interval_spin.setValue(getattr(self.discord_manager, "posting_cycle_interval", 30))
        self.posting_cycle_interval_spin.setSuffix("秒")
        self.posting_cycle_interval_spin.valueChanged.connect(self.on_posting_cycle_interval_changed)
        posting_cycle_layout.addWidget(self.posting_cycle_interval_spin)
        posting_cycle_layout.addStretch()
        rotation_accounts_layout.addLayout(posting_cycle_layout)

        # 发帖启动倒计时
        posting_start_layout = QHBoxLayout()
        posting_start_layout.addWidget(QLabel("启动倒计时(秒):"))
        self.posting_start_delay_spin = QSpinBox()
        self.posting_start_delay_spin.setRange(0, 86400)
        self.posting_start_delay_spin.setValue(getattr(self.discord_manager, "posting_start_delay", 0))
        self.posting_start_delay_spin.setSuffix("秒")
        self.posting_start_delay_spin.valueChanged.connect(self.on_posting_start_delay_changed)
        posting_start_layout.addWidget(self.posting_start_delay_spin)
        self.posting_start_countdown_label = QLabel("启动倒计时: 未启用")
        posting_start_layout.addWidget(self.posting_start_countdown_label)
        posting_start_layout.addStretch()
        rotation_accounts_layout.addLayout(posting_start_layout)

        # 循环发送设置
        repeat_layout = QHBoxLayout()
        self.posting_repeat_checkbox = QCheckBox("循环发送任务")
        self.posting_repeat_checkbox.setToolTip("启用后，发帖任务会按间隔循环执行")
        self.posting_repeat_checkbox.setChecked(self.discord_manager.posting_repeat_enabled)
        self.posting_repeat_checkbox.stateChanged.connect(self.on_posting_repeat_enabled_changed)
        repeat_layout.addWidget(self.posting_repeat_checkbox)
        repeat_layout.addStretch()
        rotation_accounts_layout.addLayout(repeat_layout)

        # 默认频道
        default_channel_layout = QHBoxLayout()
        default_channel_layout.addWidget(QLabel("默认频道ID:"))
        self.posting_default_channel_input = QLineEdit()
        self.posting_default_channel_input.setPlaceholderText("可选，留空则每次手动输入")
        if self.discord_manager.default_posting_channel_id:
            self.posting_default_channel_input.setText(str(self.discord_manager.default_posting_channel_id))
        self.posting_default_channel_input.editingFinished.connect(self.on_default_posting_channel_changed)
        default_channel_layout.addWidget(self.posting_default_channel_input)
        rotation_accounts_layout.addLayout(default_channel_layout)

        # 默认标签
        default_tags_layout = QHBoxLayout()
        default_tags_layout.addWidget(QLabel("默认标签:"))
        self.posting_default_tags_input = QLineEdit()
        self.posting_default_tags_input.setPlaceholderText("可选，多个用逗号或分号分隔")
        if self.discord_manager.default_posting_tags:
            self.posting_default_tags_input.setText(", ".join(self.discord_manager.default_posting_tags))
        self.posting_default_tags_input.editingFinished.connect(self.on_default_posting_tags_changed)
        default_tags_layout.addWidget(self.posting_default_tags_input)
        rotation_accounts_layout.addLayout(default_tags_layout)

        layout.addWidget(rotation_accounts_group)

        # 发帖任务列表
        tasks_group = QGroupBox("发帖任务")
        tasks_layout = QVBoxLayout(tasks_group)

        # 搜索框和添加按钮
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索内容:"))
        self.posting_search_input = QLineEdit()
        self.posting_search_input.setPlaceholderText("搜索发帖内容...")
        self.posting_search_input.textChanged.connect(self.filter_posting_tasks)
        search_layout.addWidget(self.posting_search_input)

        # 添加发帖任务按钮
        add_posting_btn = QPushButton("添加发帖任务")
        add_posting_btn.clicked.connect(self.add_posting_task)
        search_layout.addWidget(add_posting_btn)

        import_posting_btn = QPushButton("自动读取")
        import_posting_btn.clicked.connect(self.import_posting_materials)
        search_layout.addWidget(import_posting_btn)

        clear_posting_btn = QPushButton("一键删除")
        clear_posting_btn.clicked.connect(self.clear_posting_tasks)
        search_layout.addWidget(clear_posting_btn)

        tasks_layout.addLayout(search_layout)

        # 任务表格
        self.posting_tasks_table = QTableWidget()
        self.posting_tasks_table.setColumnCount(6)
        self.posting_tasks_table.setHorizontalHeaderLabels(["标题", "内容", "频道ID", "图片", "状态", "操作"])
        self.posting_tasks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tasks_layout.addWidget(self.posting_tasks_table)

        layout.addWidget(tasks_group)

        self.tab_widget.addTab(posting_widget, "自动发帖")

    def create_comment_tab(self):
        """创建自动评论标签页"""
        comment_widget = QWidget()
        layout = QVBoxLayout(comment_widget)

        # 账号轮换与选择设置
        rotation_accounts_group = QGroupBox("账号轮换与选择设置")
        rotation_accounts_layout = QVBoxLayout(rotation_accounts_group)

        # 启用轮换
        self.comment_rotation_enabled_checkbox = QCheckBox("启用账号轮换")
        self.comment_rotation_enabled_checkbox.setToolTip("启用后，按评论条数自动切换账号")
        self.comment_rotation_enabled_checkbox.stateChanged.connect(self.on_comment_rotation_enabled_changed)
        rotation_accounts_layout.addWidget(self.comment_rotation_enabled_checkbox)

        # 轮换条数设置
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("每评论条数轮换:"))
        self.comment_rotation_count_spin = QSpinBox()
        self.comment_rotation_count_spin.setRange(1, 1000)  # 1到1000条
        self.comment_rotation_count_spin.setValue(10)  # 默认10条
        self.comment_rotation_count_spin.setSuffix("条")
        self.comment_rotation_count_spin.setEnabled(True)  # 评论轮换条数设置始终可用，用户可以预设参数
        self.comment_rotation_count_spin.valueChanged.connect(self.on_comment_rotation_count_changed)
        count_layout.addWidget(self.comment_rotation_count_spin)
        count_layout.addStretch()
        rotation_accounts_layout.addLayout(count_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        rotation_accounts_layout.addWidget(line)

        # 账号选择
        self.comment_accounts_combo = QComboBox()
        self.comment_accounts_combo.addItem("随机使用所有账号")
        # 添加具体账号选项
        for account in self.discord_manager.accounts:
            if account.is_active and account.is_valid:
                self.comment_accounts_combo.addItem(f"仅使用 {account.alias}")
        self.comment_accounts_combo.setCurrentIndex(0)  # 默认随机使用所有账号

        rotation_accounts_layout.addWidget(QLabel("评论账号:"))
        rotation_accounts_layout.addWidget(self.comment_accounts_combo)

        # 应用按钮
        apply_comment_accounts_btn = QPushButton("应用评论账号设置")
        apply_comment_accounts_btn.clicked.connect(self.apply_global_comment_accounts)
        rotation_accounts_layout.addWidget(apply_comment_accounts_btn)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        rotation_accounts_layout.addWidget(line2)

        # 评论间隔
        comment_interval_layout = QHBoxLayout()
        comment_interval_layout.addWidget(QLabel("评论间隔(秒):"))
        self.comment_interval_spin = QSpinBox()
        self.comment_interval_spin.setRange(0, 86400)  # 0秒到24小时
        self.comment_interval_spin.setValue(30)  # 默认30秒
        self.comment_interval_spin.setSuffix("秒")
        self.comment_interval_spin.setEnabled(True)  # 评论间隔应该始终可用
        self.comment_interval_spin.valueChanged.connect(self.on_comment_interval_changed)
        comment_interval_layout.addWidget(self.comment_interval_spin)
        comment_interval_layout.addStretch()
        rotation_accounts_layout.addLayout(comment_interval_layout)

        comment_cycle_layout = QHBoxLayout()
        comment_cycle_layout.addWidget(QLabel("循环轮次间隔(秒):"))
        self.comment_cycle_interval_spin = QSpinBox()
        self.comment_cycle_interval_spin.setRange(0, 86400)
        self.comment_cycle_interval_spin.setValue(getattr(self.discord_manager, "comment_cycle_interval", 30))
        self.comment_cycle_interval_spin.setSuffix("秒")
        self.comment_cycle_interval_spin.valueChanged.connect(self.on_comment_cycle_interval_changed)
        comment_cycle_layout.addWidget(self.comment_cycle_interval_spin)
        comment_cycle_layout.addStretch()
        rotation_accounts_layout.addLayout(comment_cycle_layout)

        # 评论启动倒计时
        comment_start_layout = QHBoxLayout()
        comment_start_layout.addWidget(QLabel("启动倒计时(秒):"))
        self.comment_start_delay_spin = QSpinBox()
        self.comment_start_delay_spin.setRange(0, 86400)
        self.comment_start_delay_spin.setValue(getattr(self.discord_manager, "comment_start_delay", 0))
        self.comment_start_delay_spin.setSuffix("秒")
        self.comment_start_delay_spin.valueChanged.connect(self.on_comment_start_delay_changed)
        comment_start_layout.addWidget(self.comment_start_delay_spin)
        self.comment_start_countdown_label = QLabel("启动倒计时: 未启用")
        comment_start_layout.addWidget(self.comment_start_countdown_label)
        comment_start_layout.addStretch()
        rotation_accounts_layout.addLayout(comment_start_layout)

        # 循环评论设置
        comment_repeat_layout = QHBoxLayout()
        self.comment_repeat_checkbox = QCheckBox("循环评论任务")
        self.comment_repeat_checkbox.setToolTip("启用后，评论任务会按间隔循环执行")
        self.comment_repeat_checkbox.setChecked(self.discord_manager.comment_repeat_enabled)
        self.comment_repeat_checkbox.stateChanged.connect(self.on_comment_repeat_enabled_changed)
        comment_repeat_layout.addWidget(self.comment_repeat_checkbox)
        comment_repeat_layout.addStretch()
        rotation_accounts_layout.addLayout(comment_repeat_layout)

        # 多链接间隔
        link_interval_layout = QHBoxLayout()
        link_interval_layout.addWidget(QLabel("多链接间隔(秒):"))
        self.comment_link_interval_spin = QSpinBox()
        self.comment_link_interval_spin.setRange(0, 3600)
        self.comment_link_interval_spin.setValue(self.discord_manager.comment_link_interval)
        self.comment_link_interval_spin.setSuffix("秒")
        self.comment_link_interval_spin.valueChanged.connect(self.on_comment_link_interval_changed)
        link_interval_layout.addWidget(self.comment_link_interval_spin)
        link_interval_layout.addStretch()
        rotation_accounts_layout.addLayout(link_interval_layout)

        layout.addWidget(rotation_accounts_group)

        # 评论任务列表
        tasks_group = QGroupBox("评论任务")
        tasks_layout = QVBoxLayout(tasks_group)

        # 搜索框和添加按钮
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索内容:"))
        self.comment_search_input = QLineEdit()
        self.comment_search_input.setPlaceholderText("搜索评论内容...")
        self.comment_search_input.textChanged.connect(self.filter_comment_tasks)
        search_layout.addWidget(self.comment_search_input)

        # 添加评论任务按钮
        add_comment_btn = QPushButton("添加评论任务")
        add_comment_btn.clicked.connect(self.add_comment_task)
        search_layout.addWidget(add_comment_btn)

        import_comment_btn = QPushButton("自动读取")
        import_comment_btn.clicked.connect(self.import_comment_materials)
        search_layout.addWidget(import_comment_btn)

        clear_comment_btn = QPushButton("一键删除")
        clear_comment_btn.clicked.connect(self.clear_comment_tasks)
        search_layout.addWidget(clear_comment_btn)

        tasks_layout.addLayout(search_layout)

        # 任务表格
        self.comment_tasks_table = QTableWidget()
        self.comment_tasks_table.setColumnCount(5)
        self.comment_tasks_table.setHorizontalHeaderLabels(["内容", "消息链接", "图片", "状态", "操作"])
        self.comment_tasks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tasks_layout.addWidget(self.comment_tasks_table)

        layout.addWidget(tasks_group)

        self.tab_widget.addTab(comment_widget, "自动评论")

    def create_control_bar(self, parent_layout):
        """创建底部控制栏"""
        control_layout = QHBoxLayout()

        # 启动/停止按钮组
        button_group = QGroupBox("账号控制")
        button_layout = QHBoxLayout(button_group)

        # 机器人控制按钮（单个切换按钮）
        self.bot_toggle_button = QPushButton("▶️ 启动账号")
        self.bot_toggle_button.setCheckable(True)
        self.bot_toggle_button.setChecked(False)  # 默认未启动
        self.bot_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                padding: 10px 30px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
            QPushButton:checked {
                background-color: #28a745;
            }
            QPushButton:checked:hover {
                background-color: #218838;
            }
            QPushButton:checked:pressed {
                background-color: #1e7e34;
            }
        """)
        self.bot_toggle_button.clicked.connect(self.toggle_bot)
        button_layout.addWidget(self.bot_toggle_button)

        control_layout.addWidget(button_group)

        # 功能控制按钮组
        function_group = QGroupBox("功能控制")

        # 机器人控制按钮组
        button_group = QGroupBox("账号控制")
        function_layout = QHBoxLayout(function_group)

        # 自动回复按钮
        self.reply_toggle_button = QPushButton("📝 自动回复: 开启")
        self.reply_toggle_button.setCheckable(True)
        self.reply_toggle_button.setChecked(True)  # 默认开启
        self.reply_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:!checked {
                background-color: #6c757d;
            }
            QPushButton:!checked:hover {
                background-color: #5a6268;
            }
        """)
        self.reply_toggle_button.clicked.connect(self.toggle_auto_reply)
        function_layout.addWidget(self.reply_toggle_button)

        # 自动发帖按钮
        self.posting_toggle_button = QPushButton("📄 自动发帖: 关闭")
        self.posting_toggle_button.setCheckable(True)
        self.posting_toggle_button.setChecked(False)  # 默认关闭
        self.posting_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:checked {
                background-color: #28a745;
            }
            QPushButton:checked:hover {
                background-color: #218838;
            }
        """)
        self.posting_toggle_button.clicked.connect(self.toggle_auto_posting)
        function_layout.addWidget(self.posting_toggle_button)

        # 自动评论按钮
        self.comment_toggle_button = QPushButton("💬 自动评论: 关闭")
        self.comment_toggle_button.setCheckable(True)
        self.comment_toggle_button.setChecked(False)  # 默认关闭
        self.comment_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:checked {
                background-color: #28a745;
            }
            QPushButton:checked:hover {
                background-color: #218838;
            }
        """)
        self.comment_toggle_button.clicked.connect(self.toggle_auto_comment)
        function_layout.addWidget(self.comment_toggle_button)

        control_layout.addWidget(function_group)

        # 配置导入导出
        control_layout.addStretch()

        config_group = QGroupBox("配置管理")
        config_layout = QHBoxLayout(config_group)

        export_btn = QPushButton("📤 导出配置")
        export_btn.clicked.connect(self.export_config)
        config_layout.addWidget(export_btn)

        import_btn = QPushButton("📥 导入配置")
        import_btn.clicked.connect(self.import_config)
        config_layout.addWidget(import_btn)

        control_layout.addWidget(config_group)

        parent_layout.addLayout(control_layout)

    def load_config(self):
        """加载配置"""
        accounts, rules, license_config, rotation_config, posting_tasks, comment_tasks, workspaces, active_workspace = self.config_manager.load_config()
        self.discord_manager.accounts = accounts
        self.discord_manager.rules = rules
        for task in posting_tasks:
            task.next_run_at = None
        for task in comment_tasks:
            task.next_run_at = None
        self.discord_manager.posting_tasks = posting_tasks
        self.discord_manager.comment_tasks = comment_tasks
        self.workspaces = workspaces if workspaces else []
        self.active_workspace_index = active_workspace if active_workspace is not None else 0

        if not self.workspaces:
            self.workspaces = [{
                "id": self.generate_workspace_id(),
                "name": "工具1",
                "rules": self.discord_manager.rules,
                "posting_tasks": self.discord_manager.posting_tasks,
                "comment_tasks": self.discord_manager.comment_tasks,
                "rotation": rotation_config or {},
                "features": self.default_workspace_features()
            }]
            self.active_workspace_index = 0

        for index, ws in enumerate(self.workspaces):
            self.ensure_workspace_defaults(ws, index)

        # 许可证配置（固定服务器，不使用认证信息）
        license_key = license_config.get("license_key", "").strip()
        if license_key:
            self.license_key = license_key

        saved_hwid = license_config.get("hwid")
        is_activated = license_config.get("is_activated", False)
        license_info = license_config.get("license_info")
        if saved_hwid:
            self.discord_manager.license_manager.machine_fingerprint = saved_hwid

        # 优先信任本地已激活状态，避免重启后重复要求输入密钥
        if license_key and is_activated:
            self.discord_manager.license_manager.license_key = license_key
            self.discord_manager.license_manager.is_activated = True
            if isinstance(license_info, dict):
                self.discord_manager.license_manager.license_info = license_info

        # 加载轮换设置
        self.apply_rotation_config(rotation_config)

        self.update_accounts_list()
        self.update_rules_list()
        self.update_license_status()
        self.update_function_buttons()
        self.update_status()

        # 设置发帖和评论间隔的值
        self.sync_rotation_controls()

        # 更新任务列表显示
        self.update_posting_tasks_list()
        self.update_comment_tasks_list()
        self.refresh_start_countdowns()

        # 初始化工作区标签
        self.refresh_workspace_tabs()

        # 根据各页面开关重建运行上下文（支持多页面独立运行）
        self.refresh_runtime_contexts_from_workspaces()

    def generate_workspace_id(self) -> str:
        """生成页面唯一ID"""
        return f"ws_{uuid.uuid4().hex[:12]}"

    def default_workspace_features(self) -> Dict:
        """页面默认开关配置"""
        return {
            "reply_enabled": False,
            "posting_enabled": False,
            "comment_enabled": False,
            "reply_start_at": None,
            "posting_start_at": None,
            "comment_start_at": None,
        }

    def ensure_workspace_defaults(self, workspace: Dict, index: int):
        """补齐页面配置缺失字段"""
        if not workspace.get("id"):
            workspace["id"] = self.generate_workspace_id()

        features = workspace.get("features", {}) or {}
        default_features = self.default_workspace_features()
        for key, value in default_features.items():
            features.setdefault(key, value)

        # 旧版本可能残留过去的倒计时时间戳，启动时重置为未启动
        for key in ("reply_start_at", "posting_start_at", "comment_start_at"):
            if features.get(key) and features.get(key) < time.time():
                features[key] = None

        workspace["features"] = features

    def get_active_workspace(self) -> Optional[Dict]:
        """获取当前页面对象"""
        if not self.workspaces:
            return None
        if not (0 <= self.active_workspace_index < len(self.workspaces)):
            return None
        return self.workspaces[self.active_workspace_index]

    def get_active_workspace_features(self) -> Dict:
        """获取当前页面功能开关"""
        workspace = self.get_active_workspace()
        if workspace is None:
            return self.default_workspace_features()
        self.ensure_workspace_defaults(workspace, self.active_workspace_index)
        return workspace.get("features", self.default_workspace_features())

    def refresh_runtime_contexts_from_workspaces(self):
        """根据页面配置刷新运行上下文（发帖/评论/回复）"""
        previous_posting_contexts = getattr(self.discord_manager, "workspace_posting_contexts", {}) or {}
        previous_comment_contexts = getattr(self.discord_manager, "workspace_comment_contexts", {}) or {}

        posting_contexts = {}
        comment_contexts = {}
        reply_contexts = {}

        any_reply_enabled = False
        any_posting_enabled = False
        any_comment_enabled = False

        for index, workspace in enumerate(self.workspaces):
            self.ensure_workspace_defaults(workspace, index)

            workspace_id = workspace.get("id")
            workspace_name = workspace.get("name", f"工具{index + 1}")
            features = workspace.get("features", {})
            rotation = workspace.get("rotation", {}) or {}

            if features.get("reply_enabled"):
                any_reply_enabled = True
                reply_contexts[workspace_id] = {
                    "enabled": True,
                    "name": workspace_name,
                    "start_at": features.get("reply_start_at"),
                    "rules": workspace.get("rules", []),
                }

            if features.get("posting_enabled"):
                any_posting_enabled = True
                start_at = features.get("posting_start_at")
                previous_context = previous_posting_contexts.get(workspace_id)

                if previous_context:
                    context = previous_context
                    context["enabled"] = True
                    context["name"] = workspace_name
                    context["start_at"] = start_at
                    context["posting_interval"] = max(0, int(rotation.get("posting_interval", 30)))
                    context["cycle_interval"] = max(0, int(rotation.get("posting_cycle_interval", context.get("posting_interval", 30))))
                    context["repeat_enabled"] = bool(rotation.get("posting_repeat_enabled", False))
                    context["account_tokens"] = list(rotation.get("posting_account_tokens", []) or [])
                    context["rotation_enabled"] = bool(rotation.get("posting_rotation_enabled", False))
                    context["rotation_count"] = max(1, int(rotation.get("posting_rotation_count", 10)))
                else:
                    runtime_tasks = [copy.deepcopy(task) for task in workspace.get("posting_tasks", [])]
                    for task in runtime_tasks:
                        if task.is_active:
                            task.next_run_at = None
                            task.sent_count = 0

                    context = {
                        "enabled": True,
                        "name": workspace_name,
                        "tasks": runtime_tasks,
                        "cursor": 0,
                        "posting_interval": max(0, int(rotation.get("posting_interval", 30))),
                        "cycle_interval": max(0, int(rotation.get("posting_cycle_interval", 30))),
                        "repeat_enabled": bool(rotation.get("posting_repeat_enabled", False)),
                        "start_at": start_at,
                        "account_tokens": list(rotation.get("posting_account_tokens", []) or []),
                        "rotation_enabled": bool(rotation.get("posting_rotation_enabled", False)),
                        "rotation_count": max(1, int(rotation.get("posting_rotation_count", 10))),
                        "current_index": 0,
                        "count_since_rotation": 0,
                        "_initialized": False,
                    }

                posting_contexts[workspace_id] = context

            if features.get("comment_enabled"):
                any_comment_enabled = True
                start_at = features.get("comment_start_at")
                previous_context = previous_comment_contexts.get(workspace_id)

                if previous_context:
                    context = previous_context
                    context["enabled"] = True
                    context["name"] = workspace_name
                    context["start_at"] = start_at
                    context["comment_interval"] = max(0, int(rotation.get("comment_interval", 30)))
                    context["cycle_interval"] = max(0, int(rotation.get("comment_cycle_interval", context.get("comment_interval", 30))))
                    context["repeat_enabled"] = bool(rotation.get("comment_repeat_enabled", False))
                    context["comment_link_interval"] = max(0, int(rotation.get("comment_link_interval", 5)))
                    context["account_tokens"] = list(rotation.get("comment_account_tokens", []) or [])
                    context["rotation_enabled"] = bool(rotation.get("comment_rotation_enabled", False))
                    context["rotation_count"] = max(1, int(rotation.get("comment_rotation_count", 10)))
                else:
                    runtime_tasks = [copy.deepcopy(task) for task in workspace.get("comment_tasks", [])]
                    for task in runtime_tasks:
                        if task.is_active:
                            task.next_run_at = None
                            task.sent_count = 0

                    context = {
                        "enabled": True,
                        "name": workspace_name,
                        "tasks": runtime_tasks,
                        "cursor": 0,
                        "comment_interval": max(0, int(rotation.get("comment_interval", 30))),
                        "cycle_interval": max(0, int(rotation.get("comment_cycle_interval", 30))),
                        "repeat_enabled": bool(rotation.get("comment_repeat_enabled", False)),
                        "start_at": start_at,
                        "comment_link_interval": max(0, int(rotation.get("comment_link_interval", 5))),
                        "account_tokens": list(rotation.get("comment_account_tokens", []) or []),
                        "rotation_enabled": bool(rotation.get("comment_rotation_enabled", False)),
                        "rotation_count": max(1, int(rotation.get("comment_rotation_count", 10))),
                        "current_index": 0,
                        "count_since_rotation": 0,
                        "_initialized": False,
                    }

                comment_contexts[workspace_id] = context

        self.discord_manager.workspace_posting_contexts = posting_contexts
        self.discord_manager.workspace_comment_contexts = comment_contexts
        self.discord_manager.workspace_reply_contexts = reply_contexts
        self.discord_manager.reply_rule_pool = self.discord_manager.get_active_reply_rules()

        self.discord_manager.reply_enabled = any_reply_enabled
        self.discord_manager.posting_enabled = any_posting_enabled
        self.discord_manager.comment_enabled = any_comment_enabled

        # 兼容旧逻辑：保留一份平铺任务用于状态显示
        self.discord_manager.runtime_posting_tasks = [
            task
            for context in posting_contexts.values()
            for task in context.get("tasks", [])
        ]
        self.discord_manager.runtime_comment_tasks = [
            task
            for context in comment_contexts.values()
            for task in context.get("tasks", [])
        ]

        if self.discord_manager.is_running:
            for client in self.discord_manager.clients:
                client.rules = self.discord_manager.get_active_reply_rules()

            if self.discord_manager.posting_enabled:
                try:
                    asyncio.create_task(self.discord_manager.start_posting_scheduler())
                except RuntimeError:
                    pass

            if self.discord_manager.comment_enabled:
                try:
                    asyncio.create_task(self.discord_manager.start_comment_scheduler())
                except RuntimeError:
                    pass

    def apply_rotation_config(self, rotation_config: Dict):
        """应用轮换/间隔/默认配置到管理器"""
        rotation_config = rotation_config or {}
        self.discord_manager.rotation_enabled = rotation_config.get("rotation_enabled", False)
        self.discord_manager.rotation_interval = rotation_config.get("rotation_interval", 600)  # 默认10分钟
        self.discord_manager.posting_rotation_enabled = rotation_config.get("posting_rotation_enabled", False)
        self.discord_manager.posting_rotation_count = rotation_config.get("posting_rotation_count", 10)
        self.discord_manager.comment_rotation_enabled = rotation_config.get("comment_rotation_enabled", False)
        self.discord_manager.comment_rotation_count = rotation_config.get("comment_rotation_count", 10)
        self.discord_manager.posting_interval = rotation_config.get("posting_interval", 30)  # 默认30秒
        self.discord_manager.posting_cycle_interval = rotation_config.get("posting_cycle_interval", 30)
        self.discord_manager.comment_interval = rotation_config.get("comment_interval", 30)  # 默认30秒
        self.discord_manager.comment_cycle_interval = rotation_config.get("comment_cycle_interval", 30)
        self.discord_manager.posting_repeat_enabled = rotation_config.get("posting_repeat_enabled", False)
        self.discord_manager.comment_repeat_enabled = rotation_config.get("comment_repeat_enabled", False)
        self.discord_manager.comment_link_interval = rotation_config.get("comment_link_interval", 5)
        self.discord_manager.default_posting_channel_id = rotation_config.get("default_posting_channel_id")
        self.discord_manager.posting_start_delay = rotation_config.get("posting_start_delay", 0)
        self.discord_manager.comment_start_delay = rotation_config.get("comment_start_delay", 0)
        self.discord_manager.reply_start_delay = rotation_config.get("reply_start_delay", 0)
        self.discord_manager.posting_account_tokens = rotation_config.get("posting_account_tokens", []) or []
        self.discord_manager.comment_account_tokens = rotation_config.get("comment_account_tokens", []) or []
        default_tags = rotation_config.get("default_posting_tags", [])
        if isinstance(default_tags, str):
            default_tags = [t.strip() for t in default_tags.replace("\n", ",").split(",") if t.strip()]
        self.discord_manager.default_posting_tags = default_tags

    def sync_rotation_controls(self):
        """将管理器配置同步到界面控件"""
        if hasattr(self, "posting_interval_spin"):
            self.posting_interval_spin.setValue(self.discord_manager.posting_interval)
        if hasattr(self, "posting_cycle_interval_spin"):
            self.posting_cycle_interval_spin.setValue(getattr(self.discord_manager, "posting_cycle_interval", 30))
        if hasattr(self, "comment_interval_spin"):
            self.comment_interval_spin.setValue(self.discord_manager.comment_interval)
        if hasattr(self, "comment_cycle_interval_spin"):
            self.comment_cycle_interval_spin.setValue(getattr(self.discord_manager, "comment_cycle_interval", 30))
        if hasattr(self, "posting_repeat_checkbox"):
            self.posting_repeat_checkbox.setChecked(self.discord_manager.posting_repeat_enabled)
        if hasattr(self, "comment_repeat_checkbox"):
            self.comment_repeat_checkbox.setChecked(self.discord_manager.comment_repeat_enabled)
        if hasattr(self, "posting_default_channel_input"):
            if self.discord_manager.default_posting_channel_id:
                self.posting_default_channel_input.setText(str(self.discord_manager.default_posting_channel_id))
            else:
                self.posting_default_channel_input.clear()
        if hasattr(self, "posting_default_tags_input"):
            if self.discord_manager.default_posting_tags:
                self.posting_default_tags_input.setText(", ".join(self.discord_manager.default_posting_tags))
            else:
                self.posting_default_tags_input.clear()
        if hasattr(self, "comment_link_interval_spin"):
            self.comment_link_interval_spin.setValue(self.discord_manager.comment_link_interval)
        if hasattr(self, "posting_start_delay_spin"):
            self.posting_start_delay_spin.setValue(getattr(self.discord_manager, "posting_start_delay", 0))
        if hasattr(self, "comment_start_delay_spin"):
            self.comment_start_delay_spin.setValue(getattr(self.discord_manager, "comment_start_delay", 0))
        if hasattr(self, "reply_start_delay_spin"):
            self.reply_start_delay_spin.setValue(getattr(self.discord_manager, "reply_start_delay", 0))

        # 页面切换时同步账号下拉框
        self.update_global_accounts_combo()

    def collect_rotation_config(self) -> Dict:
        """从管理器收集轮换/间隔/默认配置"""
        return {
            "rotation_enabled": self.discord_manager.rotation_enabled,
            "rotation_interval": self.discord_manager.rotation_interval,
            "posting_rotation_enabled": self.discord_manager.posting_rotation_enabled,
            "posting_rotation_count": self.discord_manager.posting_rotation_count,
            "comment_rotation_enabled": self.discord_manager.comment_rotation_enabled,
            "comment_rotation_count": self.discord_manager.comment_rotation_count,
            "posting_interval": self.discord_manager.posting_interval,
            "posting_cycle_interval": getattr(self.discord_manager, "posting_cycle_interval", 30),
            "comment_interval": self.discord_manager.comment_interval,
            "comment_cycle_interval": getattr(self.discord_manager, "comment_cycle_interval", 30),
            "posting_repeat_enabled": self.discord_manager.posting_repeat_enabled,
            "comment_repeat_enabled": self.discord_manager.comment_repeat_enabled,
            "comment_link_interval": self.discord_manager.comment_link_interval,
            "default_posting_channel_id": self.discord_manager.default_posting_channel_id,
            "default_posting_tags": self.discord_manager.default_posting_tags,
            "posting_start_delay": getattr(self.discord_manager, "posting_start_delay", 0),
            "comment_start_delay": getattr(self.discord_manager, "comment_start_delay", 0),
            "reply_start_delay": getattr(self.discord_manager, "reply_start_delay", 0),
            "posting_account_tokens": getattr(self.discord_manager, "posting_account_tokens", []),
            "comment_account_tokens": getattr(self.discord_manager, "comment_account_tokens", [])
        }

    def refresh_workspace_tabs(self):
        """刷新工作区标签显示"""
        if not hasattr(self, 'workspace_tabbar'):
            return
        if not self.workspaces:
            self.workspaces = [{
                "name": "工具1",
                "rules": self.discord_manager.rules,
                "posting_tasks": self.discord_manager.posting_tasks,
                "comment_tasks": self.discord_manager.comment_tasks,
                "rotation": self.collect_rotation_config()
            }]
            self.active_workspace_index = 0

        self.workspace_tabbar.blockSignals(True)
        while self.workspace_tabbar.count() > 0:
            self.workspace_tabbar.removeTab(0)
        for i, ws in enumerate(self.workspaces):
            self.ensure_workspace_defaults(ws, i)
            self.workspace_tabbar.addTab(ws.get("name", "工具"))
        if 0 <= self.active_workspace_index < self.workspace_tabbar.count():
            self.workspace_tabbar.setCurrentIndex(self.active_workspace_index)
        self.workspace_tabbar.blockSignals(False)

    def sync_current_workspace(self):
        """将当前管理器数据同步到活动工作区"""
        if not self.workspaces:
            return
        ws = self.workspaces[self.active_workspace_index]
        self.ensure_workspace_defaults(ws, self.active_workspace_index)
        ws["rules"] = self.discord_manager.rules
        ws["posting_tasks"] = self.discord_manager.posting_tasks
        ws["comment_tasks"] = self.discord_manager.comment_tasks
        ws["rotation"] = self.collect_rotation_config()
        features = ws.get("features", self.default_workspace_features())
        if hasattr(self, "reply_toggle_button"):
            features["reply_enabled"] = self.reply_toggle_button.isChecked()
        if hasattr(self, "posting_toggle_button"):
            features["posting_enabled"] = self.posting_toggle_button.isChecked()
        if hasattr(self, "comment_toggle_button"):
            features["comment_enabled"] = self.comment_toggle_button.isChecked()
        ws["features"] = features

    def load_workspace(self, index: int):
        """加载指定工作区到管理器"""
        if not (0 <= index < len(self.workspaces)):
            return
        ws = self.workspaces[index]
        self.ensure_workspace_defaults(ws, index)
        self.discord_manager.rules = ws.get("rules", [])
        self.discord_manager.posting_tasks = ws.get("posting_tasks", [])
        self.discord_manager.comment_tasks = ws.get("comment_tasks", [])
        self.apply_rotation_config(ws.get("rotation", {}))
        self.sync_rotation_controls()
        self.update_rules_list()
        self.update_posting_tasks_list()
        self.update_comment_tasks_list()
        self.update_function_buttons()
        self.refresh_start_countdowns()

    def on_workspace_changed(self, index: int):
        """切换工作区"""
        if index == self.active_workspace_index or index < 0:
            return

        was_running = (
            self.discord_manager.reply_enabled
            or self.discord_manager.posting_enabled
            or self.discord_manager.comment_enabled
        )

        self.sync_current_workspace()
        self.active_workspace_index = index
        self.load_workspace(index)
        self.save_config()

        if was_running:
            self.add_log("已切换页面：当前运行中的任务继续执行，新页面可继续编辑", "info")

    def add_workspace(self):
        """新增工作区"""
        self.sync_current_workspace()
        new_index = len(self.workspaces) + 1
        new_name = f"工具{new_index}"
        self.workspaces.append({
            "id": self.generate_workspace_id(),
            "name": new_name,
            "rules": [],
            "posting_tasks": [],
            "comment_tasks": [],
            "rotation": self.collect_rotation_config(),
            "features": self.default_workspace_features()
        })
        self.refresh_workspace_tabs()
        self.workspace_tabbar.setCurrentIndex(len(self.workspaces) - 1)
        self.save_config()

    def rename_workspace(self, index=None):
        """重命名工作区"""
        if index is None or index < 0:
            index = self.workspace_tabbar.currentIndex() if hasattr(self, 'workspace_tabbar') else -1
        if not (0 <= index < len(self.workspaces)):
            return
        current_name = self.workspaces[index].get("name", f"工具{index + 1}")
        new_name, ok = QInputDialog.getText(self, "重命名页面", "输入新名称:", text=current_name)
        if ok and new_name.strip():
            self.workspaces[index]["name"] = new_name.strip()
            self.workspace_tabbar.setTabText(index, new_name.strip())
            self.save_config()

    def delete_workspace(self):
        """删除当前工作区"""
        if len(self.workspaces) <= 1:
            QMessageBox.information(self, "提示", "至少需要保留一个页面")
            return
        if (self.discord_manager.reply_enabled or self.discord_manager.posting_enabled or
                self.discord_manager.comment_enabled):
            QMessageBox.warning(self, "提示", "请先关闭自动回复/发帖/评论后再删除页面")
            return
        index = self.workspace_tabbar.currentIndex()
        if not (0 <= index < len(self.workspaces)):
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除页面 '{self.workspaces[index].get('name', '')}' 吗？此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.workspaces.pop(index)
        if self.active_workspace_index >= len(self.workspaces):
            self.active_workspace_index = len(self.workspaces) - 1
        self.refresh_workspace_tabs()
        self.load_workspace(self.active_workspace_index)
        self.save_config()

    def update_function_buttons(self):
        """更新功能按钮状态"""
        features = self.get_active_workspace_features()

        self.reply_toggle_button.setChecked(bool(features.get("reply_enabled", False)))
        if self.reply_toggle_button.isChecked():
            self.reply_toggle_button.setText("📝 自动回复: 开启")
        else:
            self.reply_toggle_button.setText("📝 自动回复: 关闭")

        self.posting_toggle_button.setChecked(bool(features.get("posting_enabled", False)))
        if self.posting_toggle_button.isChecked():
            self.posting_toggle_button.setText("📄 自动发帖: 开启")
        else:
            self.posting_toggle_button.setText("📄 自动发帖: 关闭")
        self.posting_interval_spin.setEnabled(True)  # 发帖间隔设置始终可用，用户可以预设参数

        self.comment_toggle_button.setChecked(bool(features.get("comment_enabled", False)))
        if self.comment_toggle_button.isChecked():
            self.comment_toggle_button.setText("💬 自动评论: 开启")
        else:
            self.comment_toggle_button.setText("💬 自动评论: 关闭")
        self.comment_interval_spin.setEnabled(True)  # 评论间隔设置始终可用，用户可以预设参数

        # 轮换设置状态
        # 规则管理标签页的轮换设置
        if hasattr(self, 'rotation_enabled_checkbox'):
            self.rotation_enabled_checkbox.setChecked(self.discord_manager.rotation_enabled)
            self.rotation_interval_spin.setEnabled(True)  # 轮换间隔设置始终可用，用户可以预设参数
            if self.discord_manager.rotation_interval:
                self.rotation_interval_spin.setValue(self.discord_manager.rotation_interval // 60)  # 转换为分钟

        # 自动发帖标签页的轮换设置
        if hasattr(self, 'posting_rotation_enabled_checkbox'):
            self.posting_rotation_enabled_checkbox.setChecked(self.discord_manager.posting_rotation_enabled)
            self.posting_rotation_count_spin.setEnabled(True)  # 发帖轮换条数设置始终可用，用户可以预设参数
            self.posting_rotation_count_spin.setValue(self.discord_manager.posting_rotation_count)

        # 自动评论标签页的轮换设置
        if hasattr(self, 'comment_rotation_enabled_checkbox'):
            self.comment_rotation_enabled_checkbox.setChecked(self.discord_manager.comment_rotation_enabled)
            self.comment_rotation_count_spin.setEnabled(True)  # 评论轮换条数设置始终可用，用户可以预设参数
            self.comment_rotation_count_spin.setValue(self.discord_manager.comment_rotation_count)

    def save_config(self):
        """保存配置"""
        if self.workspaces:
            self.sync_current_workspace()
        # 使用当前有效的许可证密钥，如果没有则使用空字符串
        current_license_key = getattr(self, 'license_key', '')
        if not current_license_key and hasattr(self, 'license_key_input'):
            current_license_key = self.license_key_input.text().strip()

        license_info = self.discord_manager.license_manager.license_info
        license_config = {
            "license_key": current_license_key,
            "hwid": self.discord_manager.license_manager.machine_fingerprint
            if self.discord_manager.license_manager.is_activated else None,
            "is_activated": self.discord_manager.license_manager.is_activated,
            "license_info": license_info if isinstance(license_info, dict) else None
        }

        # 轮换配置
        rotation_config = self.collect_rotation_config()

        self.config_manager.save_config(
            self.discord_manager.accounts,
            self.discord_manager.rules,
            license_config,
            rotation_config,
            self.discord_manager.posting_tasks,
            self.discord_manager.comment_tasks,
            self.workspaces,
            self.active_workspace_index
        )

    def update_accounts_list(self):
        """更新账号表格显示"""
        self.accounts_table.setRowCount(len(self.discord_manager.accounts))

        for row, account in enumerate(self.discord_manager.accounts):
            # 序号
            index_item = QTableWidgetItem(str(row + 1))
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.accounts_table.setItem(row, 0, index_item)

            # 账号
            username = account.alias  # 使用alias属性，它会自动生成用户名
            username_item = QTableWidgetItem(username)
            username_item.setData(Qt.ItemDataRole.UserRole, account.token)  # 使用token作为标识
            self.accounts_table.setItem(row, 1, username_item)

            # 账号状态
            token_type = account.user_info.get('token_type') if account.user_info and isinstance(account.user_info, dict) else None
            if account.is_valid:
                if token_type == 'bot':
                    token_status = "有效 (Bot)"
                    bg_color = QColor(144, 238, 144)  # 浅绿色
                elif token_type == 'user':
                    token_status = "有效 (用户)"
                    bg_color = QColor(255, 255, 224)  # 浅黄色 - 警告色
                else:
                    token_status = "有效"
                    bg_color = QColor(144, 238, 144)  # 浅绿色
            else:
                token_status = "无效"
                bg_color = QColor(255, 182, 193)  # 浅红色

            token_status_item = QTableWidgetItem(token_status)
            token_status_item.setBackground(bg_color)

            # 添加工具提示
            if token_type == 'user':
                token_status_item.setToolTip("用户账号可以验证但无法连接，请使用Bot账号")
            elif token_type == 'bot':
                token_status_item.setToolTip("Bot账号，完全支持连接和消息处理")

            self.accounts_table.setItem(row, 2, token_status_item)

            # 操作按钮
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, token=account.token: self.edit_account_by_token(token))

            validate_btn = QPushButton("验证")
            validate_btn.clicked.connect(lambda checked, token=account.token: self.revalidate_account_by_token(token))

            delete_btn = QPushButton("删除")
            delete_btn.clicked.connect(lambda checked, token=account.token: self.remove_account_by_token(token))

            # 创建按钮容器
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(2, 2, 2, 2)
            button_layout.addWidget(edit_btn)
            button_layout.addWidget(validate_btn)
            button_layout.addWidget(delete_btn)

            self.accounts_table.setCellWidget(row, 3, button_widget)

        # 更新统计信息
        total_accounts = len(self.discord_manager.accounts)
        active_accounts = len([acc for acc in self.discord_manager.accounts if acc.is_active])
        self.accounts_stats_label.setText(f"总账号数: {total_accounts} | 启用账号数: {active_accounts}")

        # 更新全局账号设置组合框
        self.update_global_accounts_combo()

    def update_global_accounts_combo(self):
        """更新全局账号设置组合框"""
        # 更新自动回复组合框
        if hasattr(self, 'reply_accounts_combo'):
            current_token = self.reply_accounts_combo.currentData()
            current_index = self.reply_accounts_combo.currentIndex()
            self.reply_accounts_combo.clear()
            self.reply_accounts_combo.addItem("随机使用所有账号", None)

            # 添加具体账号选项
            for account in self.discord_manager.accounts:
                if account.is_active and account.is_valid:
                    self.reply_accounts_combo.addItem(f"仅使用 {account.alias}", account.token)

            # 根据当前规则优先恢复选择（全空=随机；全同一个账号=仅使用该账号）
            selected_token = None
            if self.discord_manager.rules:
                token_set = {
                    rule.account_ids[0]
                    for rule in self.discord_manager.rules
                    if getattr(rule, "account_ids", None) and len(rule.account_ids) == 1
                }
                if len(token_set) == 1:
                    selected_token = next(iter(token_set))

            if selected_token is None:
                selected_token = current_token

            if selected_token is not None:
                selected_index = self.reply_accounts_combo.findData(selected_token)
                if selected_index >= 0:
                    self.reply_accounts_combo.setCurrentIndex(selected_index)
                elif current_index < self.reply_accounts_combo.count():
                    self.reply_accounts_combo.setCurrentIndex(current_index)
            elif current_index < self.reply_accounts_combo.count():
                self.reply_accounts_combo.setCurrentIndex(current_index)

        # 更新自动发帖组合框
        if hasattr(self, 'posting_accounts_combo'):
            current_index = self.posting_accounts_combo.currentIndex()
            self.posting_accounts_combo.clear()
            self.posting_accounts_combo.addItem("随机使用所有账号")

            valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
            for account in valid_accounts:
                self.posting_accounts_combo.addItem(f"仅使用 {account.alias}")

            selected_token = self.discord_manager.posting_account_tokens[0] if self.discord_manager.posting_account_tokens else None
            if selected_token:
                selected_index = next((i for i, acc in enumerate(valid_accounts) if acc.token == selected_token), None)
                if selected_index is not None:
                    self.posting_accounts_combo.setCurrentIndex(selected_index + 1)
                else:
                    self.posting_accounts_combo.setCurrentIndex(0)
            elif current_index < self.posting_accounts_combo.count():
                self.posting_accounts_combo.setCurrentIndex(current_index)

        # 更新自动评论组合框
        if hasattr(self, 'comment_accounts_combo'):
            current_index = self.comment_accounts_combo.currentIndex()
            self.comment_accounts_combo.clear()
            self.comment_accounts_combo.addItem("随机使用所有账号")

            valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
            for account in valid_accounts:
                self.comment_accounts_combo.addItem(f"仅使用 {account.alias}")

            selected_token = self.discord_manager.comment_account_tokens[0] if self.discord_manager.comment_account_tokens else None
            if selected_token:
                selected_index = next((i for i, acc in enumerate(valid_accounts) if acc.token == selected_token), None)
                if selected_index is not None:
                    self.comment_accounts_combo.setCurrentIndex(selected_index + 1)
                else:
                    self.comment_accounts_combo.setCurrentIndex(0)
            elif current_index < self.comment_accounts_combo.count():
                self.comment_accounts_combo.setCurrentIndex(current_index)

    def update_rules_list(self):
        """更新规则表格显示"""
        self.rules_table.setRowCount(len(self.discord_manager.rules))

        for row, rule in enumerate(self.discord_manager.rules):
            # 关键词
            keywords_str = ", ".join(rule.keywords[:2])
            if len(rule.keywords) > 2:
                keywords_str += "..."
            keywords_item = QTableWidgetItem(keywords_str)
            keywords_item.setData(Qt.ItemDataRole.UserRole, row)
            keywords_item.setToolTip(", ".join(rule.keywords))  # 悬停显示所有关键词
            self.rules_table.setItem(row, 0, keywords_item)

            # 回复内容
            reply_display = rule.reply[:30] + "..." if len(rule.reply) > 30 else rule.reply
            reply_item = QTableWidgetItem(reply_display)
            reply_item.setToolTip(rule.reply)  # 悬停显示完整回复
            self.rules_table.setItem(row, 1, reply_item)

            # 匹配类型
            match_type_name = {
                "partial": "部分匹配",
                "exact": "精确匹配",
                "regex": "正则表达式"
            }[rule.match_type.value]
            match_item = QTableWidgetItem(match_type_name)
            self.rules_table.setItem(row, 2, match_item)

            # 频道信息
            channels_info = f"{len(rule.target_channels)}个频道" if rule.target_channels else "全部频道"
            channels_display = ", ".join(map(str, rule.target_channels[:2]))
            if len(rule.target_channels) > 2:
                channels_display += "..."
            channels_item = QTableWidgetItem(channels_display if rule.target_channels else "全部")
            channels_item.setToolTip(", ".join(map(str, rule.target_channels)) if rule.target_channels else "监听所有频道")
            self.rules_table.setItem(row, 3, channels_item)

            # 延迟
            delay_info = f"{rule.delay_min:.1f}-{rule.delay_max:.1f}秒"
            delay_item = QTableWidgetItem(delay_info)
            self.rules_table.setItem(row, 4, delay_item)

            # 忽略回复
            ignore_replies_status = "是" if getattr(rule, 'ignore_replies', False) else "否"
            ignore_item = QTableWidgetItem(ignore_replies_status)
            ignore_item.setData(Qt.ItemDataRole.ToolTipRole, "是否忽略回复他人的消息")
            self.rules_table.setItem(row, 5, ignore_item)

            # 忽略@
            ignore_mentions_status = "是" if getattr(rule, 'ignore_mentions', False) else "否"
            mentions_item = QTableWidgetItem(ignore_mentions_status)
            mentions_item.setData(Qt.ItemDataRole.ToolTipRole, "是否忽略包含@他人的消息")
            self.rules_table.setItem(row, 6, mentions_item)

            # 账号信息
            account_ids = getattr(rule, 'account_ids', [])
            if not account_ids:
                account_info = "所有账号"
                account_tooltip = "随机使用所有可用账号"
            else:
                account_names = []
                for account_token in account_ids:
                    account = next((acc for acc in self.discord_manager.accounts if acc.token == account_token), None)
                    if account:
                        account_names.append(account.alias.split('#')[0])  # 只显示用户名部分
                account_info = ", ".join(account_names[:2])
                if len(account_names) > 2:
                    account_info += "..."
                account_tooltip = ", ".join(account_names) if account_names else "指定的账号"

            account_item = QTableWidgetItem(account_info)
            account_item.setToolTip(account_tooltip)
            self.rules_table.setItem(row, 7, account_item)

            # 操作按钮
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, index=row: self.edit_rule_by_index(index))

            delete_btn = QPushButton("删除")
            delete_btn.clicked.connect(lambda checked, index=row: self.remove_rule_by_index(index))

            # 创建按钮容器
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(5, 2, 5, 2)
            button_layout.addWidget(edit_btn)
            button_layout.addWidget(delete_btn)
            button_layout.addStretch()

            self.rules_table.setCellWidget(row, 8, button_widget)

        # 更新统计信息
        total_rules = len(self.discord_manager.rules)
        active_rules = len([rule for rule in self.discord_manager.rules if rule.is_active])
        self.rules_stats_label.setText(f"总规则数: {total_rules} | 启用规则数: {active_rules}")

        # 应用当前搜索过滤
        self.filter_rules()

    def filter_rules(self):
        """根据搜索关键词过滤规则显示"""
        search_text = self.rule_search_input.text().strip().lower()

        for row in range(self.rules_table.rowCount()):
            show_row = True
            if search_text:
                # 检查关键词列是否包含搜索文本
                keywords_item = self.rules_table.item(row, 0)
                if keywords_item:
                    keywords = keywords_item.toolTip().lower() if keywords_item.toolTip() else keywords_item.text().lower()
                    if search_text not in keywords:
                        show_row = False

            self.rules_table.setRowHidden(row, not show_row)

    def filter_posting_tasks(self):
        """根据搜索内容过滤发帖任务显示"""
        search_text = self.posting_search_input.text().strip().lower()

        for row in range(self.posting_tasks_table.rowCount()):
            show_row = True
            if search_text:
                # 检查标题和内容列是否包含搜索文本
                title_item = self.posting_tasks_table.item(row, 0)
                content_item = self.posting_tasks_table.item(row, 1)
                title_text = title_item.text().lower() if title_item else ""
                content_text = content_item.text().lower() if content_item else ""
                if search_text not in title_text and search_text not in content_text:
                    show_row = False

            self.posting_tasks_table.setRowHidden(row, not show_row)

    def filter_comment_tasks(self):
        """根据搜索内容过滤评论任务显示"""
        search_text = self.comment_search_input.text().strip().lower()

        for row in range(self.comment_tasks_table.rowCount()):
            show_row = True
            if search_text:
                # 检查内容列是否包含搜索文本
                content_item = self.comment_tasks_table.item(row, 0)
                if content_item:
                    content = content_item.text().lower()
                    if search_text not in content:
                        show_row = False

            self.comment_tasks_table.setRowHidden(row, not show_row)

    def update_status(self):
        """更新状态显示"""
        try:
            status = self.discord_manager.get_status()

            # 更新账号表格
            account_count = len(status["accounts"])
            self.status_accounts_table.setRowCount(account_count)

            for i, acc in enumerate(status["accounts"]):
                # 别名
                current_alias = self.status_accounts_table.item(i, 0)
                if not current_alias or current_alias.text() != acc["alias"]:
                    self.status_accounts_table.setItem(i, 0, QTableWidgetItem(acc["alias"]))

                # 连接状态
                connection_status = "已连接" if acc["is_running"] else "未连接"
                current_connection = self.status_accounts_table.item(i, 1)
                if not current_connection or current_connection.text() != connection_status:
                    item = QTableWidgetItem(connection_status)
                    if acc["is_running"]:
                        item.setBackground(QColor(144, 238, 144))  # 浅绿色
                    else:
                        item.setBackground(QColor(255, 182, 193))  # 浅红色
                    self.status_accounts_table.setItem(i, 1, item)

                # 自动回复状态
                reply_status = "运行中" if acc["is_running"] and self.discord_manager.reply_enabled else "未启用"
                current_reply = self.status_accounts_table.item(i, 2)
                if not current_reply or current_reply.text() != reply_status:
                    item = QTableWidgetItem(reply_status)
                    if acc["is_running"] and self.discord_manager.reply_enabled:
                        item.setBackground(QColor(144, 238, 144))  # 浅绿色
                    elif self.discord_manager.reply_enabled:
                        item.setBackground(QColor(255, 255, 224))  # 浅黄色
                    else:
                        item.setBackground(QColor(240, 240, 240))  # 浅灰色
                    self.status_accounts_table.setItem(i, 2, item)

                # 自动发帖状态
                posting_status = "运行中" if acc["is_running"] and self.discord_manager.posting_enabled else "未启用"
                current_posting = self.status_accounts_table.item(i, 3)
                if not current_posting or current_posting.text() != posting_status:
                    item = QTableWidgetItem(posting_status)
                    if acc["is_running"] and self.discord_manager.posting_enabled:
                        item.setBackground(QColor(144, 238, 144))  # 浅绿色
                    elif self.discord_manager.posting_enabled:
                        item.setBackground(QColor(255, 255, 224))  # 浅黄色
                    else:
                        item.setBackground(QColor(240, 240, 240))  # 浅灰色
                    self.status_accounts_table.setItem(i, 3, item)

                # 自动评论状态
                comment_status = "运行中" if acc["is_running"] and self.discord_manager.comment_enabled else "未启用"
                current_comment = self.status_accounts_table.item(i, 4)
                if not current_comment or current_comment.text() != comment_status:
                    item = QTableWidgetItem(comment_status)
                    if acc["is_running"] and self.discord_manager.comment_enabled:
                        item.setBackground(QColor(144, 238, 144))  # 浅绿色
                    elif self.discord_manager.comment_enabled:
                        item.setBackground(QColor(255, 255, 224))  # 浅黄色
                    else:
                        item.setBackground(QColor(240, 240, 240))  # 浅灰色
                    self.status_accounts_table.setItem(i, 4, item)

            # 更新规则统计
            rules_text = f"总规则数: {status['rules_count']} | 激活规则数: {status['active_rules']}"
            if self.rules_stats_label.text() != rules_text:
                self.rules_stats_label.setText(rules_text)

            if hasattr(self, 'task_stats_label'):
                sent_text = (
                    f"已发送: 回复 {status.get('reply_sent_total', 0)} | "
                    f"发帖 {status.get('posting_sent_total', 0)} | "
                    f"评论 {status.get('comment_sent_total', 0)}"
                )
                if self.task_stats_label.text() != sent_text:
                    self.task_stats_label.setText(sent_text)

            # 刷新任务倒计时
            self.refresh_task_countdowns()

        except Exception as e:
            # 静默处理状态更新错误，避免影响用户体验
            print(f"状态更新错误: {e}")

    def refresh_task_countdowns(self):
        """刷新发帖/评论任务倒计时显示"""
        now = time.time()

        runtime_posting = {}
        if self.discord_manager.posting_enabled and self.discord_manager.runtime_posting_tasks:
            runtime_posting = {task.id: task for task in self.discord_manager.runtime_posting_tasks}

        runtime_comment = {}
        if self.discord_manager.comment_enabled and self.discord_manager.runtime_comment_tasks:
            runtime_comment = {task.id: task for task in self.discord_manager.runtime_comment_tasks}

        for row, task in enumerate(self.discord_manager.posting_tasks):
            if row >= self.posting_tasks_table.rowCount():
                break
            runtime_task = runtime_posting.get(task.id, task)
            is_active = bool(getattr(runtime_task, "is_active", task.is_active))
            sent_count = getattr(runtime_task, "sent_count", getattr(task, "sent_count", 0))
            next_run_at = getattr(runtime_task, "next_run_at", None)

            status_text = "激活" if is_active else "禁用"
            if is_active:
                if not self.discord_manager.posting_repeat_enabled and sent_count > 0:
                    status_text = "已发送"
                elif next_run_at is not None:
                    remaining = max(0, int(next_run_at - now))
                    status_text = f"激活 | 倒计时: {remaining}秒" if remaining > 0 else "激活 | 待发送"
                else:
                    status_text = "激活 | 待发送"

            status_item = self.posting_tasks_table.item(row, 4)
            if status_item:
                status_item.setText(status_text)

        for row, task in enumerate(self.discord_manager.comment_tasks):
            if row >= self.comment_tasks_table.rowCount():
                break
            runtime_task = runtime_comment.get(task.id, task)
            is_active = bool(getattr(runtime_task, "is_active", task.is_active))
            sent_count = getattr(runtime_task, "sent_count", getattr(task, "sent_count", 0))
            next_run_at = getattr(runtime_task, "next_run_at", None)

            status_text = "激活" if is_active else "禁用"
            if is_active:
                if not self.discord_manager.comment_repeat_enabled and sent_count > 0:
                    status_text = "已发送"
                elif next_run_at is not None:
                    remaining = max(0, int(next_run_at - now))
                    status_text = f"激活 | 倒计时: {remaining}秒" if remaining > 0 else "激活 | 待发送"
                else:
                    status_text = "激活 | 待发送"

            status_item = self.comment_tasks_table.item(row, 3)
            if status_item:
                status_item.setText(status_text)

        self.refresh_start_countdowns(now)

    def refresh_start_countdowns(self, now=None):
        """刷新启动倒计时显示"""
        if now is None:
            now = time.time()

        features = self.get_active_workspace_features()

        def has_enabled_in_any_workspace(feature_key: str) -> bool:
            for index, workspace in enumerate(self.workspaces):
                self.ensure_workspace_defaults(workspace, index)
                ws_features = workspace.get("features", {})
                if ws_features.get(feature_key):
                    return True
            return False

        def get_label_text(feature_key: str, start_key: str) -> str:
            enabled_current = bool(features.get(feature_key, False))
            enabled_any = has_enabled_in_any_workspace(feature_key)

            if not enabled_current:
                if enabled_any:
                    return "启动倒计时: 当前页未启用（其他页面运行中）"
                return "启动倒计时: 未启用"

            start_at = features.get(start_key)
            if start_at and now < start_at:
                remaining = max(0, int(start_at - now))
                return f"启动倒计时: {remaining}秒"
            return "启动倒计时: 已启动"

        if hasattr(self, 'posting_start_countdown_label'):
            self.posting_start_countdown_label.setText(
                get_label_text("posting_enabled", "posting_start_at")
            )

        if hasattr(self, 'comment_start_countdown_label'):
            self.comment_start_countdown_label.setText(
                get_label_text("comment_enabled", "comment_start_at")
            )

        if hasattr(self, 'reply_start_countdown_label'):
            self.reply_start_countdown_label.setText(
                get_label_text("reply_enabled", "reply_start_at")
            )

    def show_accounts_context_menu(self, position):
        """显示账号右键菜单"""
        selected_rows = set()
        for item in self.accounts_table.selectedItems():
            selected_rows.add(item.row())

        menu = QMenu()

        if len(selected_rows) == 1:
            # 单个账号的菜单
            current_row = list(selected_rows)[0]
            edit_action = menu.addAction("编辑账号")
            delete_action = menu.addAction("删除账号")
        elif len(selected_rows) > 1:
            # 多个账号的菜单
            delete_multiple_action = menu.addAction(f"删除选中的 {len(selected_rows)} 个账号")
        else:
            # 没有选中账号时的菜单
            return

        action = menu.exec(self.accounts_table.mapToGlobal(position))

        if len(selected_rows) == 1:
            current_row = list(selected_rows)[0]
            if action == edit_action:
                token_item = self.accounts_table.item(current_row, 1)
                if token_item:
                    token = token_item.data(Qt.ItemDataRole.UserRole)
                    self.edit_account_by_token(token)
            elif action == delete_action:
                token_item = self.accounts_table.item(current_row, 1)
                if token_item:
                    token = token_item.data(Qt.ItemDataRole.UserRole)
                    self.remove_account_by_token(token)
        elif len(selected_rows) > 1:
            if action == delete_multiple_action:
                self.remove_multiple_accounts(list(selected_rows))

    def show_rules_context_menu(self, position):
        """显示规则右键菜单"""
        selected_rows = set()
        for item in self.rules_table.selectedItems():
            selected_rows.add(item.row())

        menu = QMenu()

        if len(selected_rows) == 1:
            # 单个规则的菜单
            current_row = list(selected_rows)[0]
            edit_action = menu.addAction("编辑规则")
            delete_action = menu.addAction("删除规则")
        elif len(selected_rows) > 1:
            # 多个规则的菜单
            delete_multiple_action = menu.addAction(f"删除选中的 {len(selected_rows)} 个规则")
        else:
            # 没有选中规则时的菜单
            return

        action = menu.exec(self.rules_table.mapToGlobal(position))

        if len(selected_rows) == 1:
            current_row = list(selected_rows)[0]
            if action == edit_action:
                self.edit_rule_by_index(current_row)
            elif action == delete_action:
                self.remove_rule_by_index(current_row)
        elif len(selected_rows) > 1:
            if action == delete_multiple_action:
                self.remove_multiple_rules(list(selected_rows))

    def add_account(self):
        """添加新账号"""
        dialog = AccountDialog(self, discord_manager=self.discord_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_account_data()

            if not data['token']:
                QMessageBox.warning(self, "错误", "账号不能为空")
                return

            # 检查账号是否重复
            if any(acc.token == data['token'] for acc in self.discord_manager.accounts):
                QMessageBox.warning(self, "错误", "该账号已存在")
                return

            # 使用异步方法添加账号
            import asyncio
            try:
                async def add_account_async():
                    success, message = await self.discord_manager.add_account_async(data['token'])
                    # 设置激活状态
                    if success and data['token'] in [acc.token for acc in self.discord_manager.accounts]:
                        for acc in self.discord_manager.accounts:
                            if acc.token == data['token']:
                                acc.is_active = data['is_active']
                                break
                    return success, message

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success, message = loop.run_until_complete(add_account_async())

                if success:
                    self.add_log(message, "success")
                    self.update_accounts_list()
                    self.save_config()
                    QMessageBox.information(self, "成功", message)
                else:
                    self.log_text.append(f"❌ {message}")
                    QMessageBox.warning(self, "添加失败", message)

            except Exception as e:
                error_msg = f"添加账号时出错: {str(e)}"
                self.add_log(error_msg, "error")
                QMessageBox.critical(self, "错误", error_msg)

    def bulk_import_accounts(self):
        """批量导入账号"""
        dialog = QDialog(self)
        dialog.setWindowTitle("一键导入账号")
        dialog.setModal(True)
        dialog.resize(600, 420)

        layout = QVBoxLayout(dialog)

        tips_label = QLabel("一次粘贴多个账号：支持换行 / 空格 / 逗号 / 分号分隔")
        tips_label.setStyleSheet("color: #555;")
        layout.addWidget(tips_label)

        text_edit = QTextEdit()
        text_edit.setPlaceholderText("在此粘贴账号列表…")
        layout.addWidget(text_edit)

        options_layout = QHBoxLayout()
        validate_checkbox = QCheckBox("导入时验证账号（较慢）")
        validate_checkbox.setChecked(False)
        options_layout.addWidget(validate_checkbox)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        progress_label = QLabel("")
        layout.addWidget(progress_label)

        progress_bar = QProgressBar()
        progress_bar.setVisible(False)
        layout.addWidget(progress_bar)

        button_layout = QHBoxLayout()
        paste_btn = QPushButton("从剪贴板粘贴")
        button_layout.addWidget(paste_btn)
        button_layout.addStretch()
        import_btn = QPushButton("开始导入")
        cancel_btn = QPushButton("取消")
        button_layout.addWidget(import_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        def paste_from_clipboard():
            clipboard_text = QApplication.clipboard().text().strip()
            if clipboard_text:
                text_edit.setPlainText(clipboard_text)

        def parse_tokens(raw_text: str) -> List[str]:
            import re
            parts = re.split(r"[\s,;，；]+", raw_text.strip())
            tokens = []
            for part in parts:
                item = part.strip()
                if not item:
                    continue

                # 支持“序号:账号”“名称----账号”等批量格式，优先取最后一段
                for separator in ("----", "|", ":", "："):
                    if separator in item:
                        item = item.split(separator)[-1].strip()

                if item:
                    tokens.append(item)
            # 去重且保持顺序
            seen = set()
            ordered = []
            for t in tokens:
                if t not in seen:
                    seen.add(t)
                    ordered.append(t)
            return ordered

        def do_import():
            raw_text = text_edit.toPlainText()
            tokens = parse_tokens(raw_text)
            if not tokens:
                QMessageBox.information(dialog, "提示", "未检测到可导入的账号")
                return

            existing_tokens = {acc.token for acc in self.discord_manager.accounts}
            tokens_to_add = [t for t in tokens if t not in existing_tokens]

            if not tokens_to_add:
                QMessageBox.information(dialog, "提示", "这些账号已经全部存在，无需重复导入")
                return

            validate_now = validate_checkbox.isChecked()

            success_count = 0
            skip_count = len(tokens) - len(tokens_to_add)
            fail_count = 0

            if validate_now:
                progress_bar.setVisible(True)
                progress_bar.setMinimum(0)
                progress_bar.setMaximum(len(tokens_to_add))

                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    for idx, token in enumerate(tokens_to_add, start=1):
                        progress_label.setText(f"正在验证并导入账号 {idx}/{len(tokens_to_add)} ...")
                        QApplication.processEvents()
                        success, message = loop.run_until_complete(self.discord_manager.add_account_async(token))
                        if success:
                            success_count += 1
                        else:
                            fail_count += 1
                            self.add_log(f"账号导入失败: {message}", "error")
                        progress_bar.setValue(idx)
                finally:
                    loop.close()
            else:
                for token in tokens_to_add:
                    self.discord_manager.accounts.append(
                        Account(
                            token=token,
                            is_active=True,
                            is_valid=False,
                            last_verified=None,
                            user_info=None
                        )
                    )
                    success_count += 1

            self.update_accounts_list()
            self.save_config()

            QMessageBox.information(
                dialog, "导入完成",
                f"导入完成\n成功: {success_count}\n跳过重复: {skip_count}\n失败: {fail_count}"
            )
            dialog.accept()

        paste_btn.clicked.connect(paste_from_clipboard)
        import_btn.clicked.connect(do_import)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def clear_all_accounts(self):
        """一键删除所有账号"""
        if not self.discord_manager.accounts:
            QMessageBox.information(self, "提示", "当前没有账号可删除")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除全部账号吗？此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.accounts.clear()
            self.update_accounts_list()
            self.save_config()
            self.add_log("已删除全部账号", "info")

    def edit_account_by_token(self, token):
        """通过账号标识编辑账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.token == token), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return

        dialog = AccountDialog(self, account, discord_manager=self.discord_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_account_data()

            if not data['token']:
                QMessageBox.warning(self, "错误", "账号不能为空")
                return

            # 检查账号是否重复（排除当前账号）
            if data['token'] != token and any(acc.token == data['token'] for acc in self.discord_manager.accounts):
                QMessageBox.warning(self, "错误", "该账号已存在")
                return

            # 更新账号信息
            account.token = data['token']
            account.is_active = data['is_active']
            account.is_valid = data.get('is_valid', False)
            account.user_info = data.get('user_info')

            self.add_log(f"账号 '{account.alias}' 更新成功", "success")
            self.update_accounts_list()
            self.save_config()
            QMessageBox.information(self, "成功", "账号编辑成功")

    def edit_account_by_alias(self, alias):
        """通过别名编辑账号（兼容旧调用）"""
        account = next((acc for acc in self.discord_manager.accounts if acc.alias == alias), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return
        self.edit_account_by_token(account.token)


    def apply_global_reply_accounts(self):
        """应用全局账号设置到所有规则"""
        selected_token = self.reply_accounts_combo.currentData()
        valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
        valid_tokens = {acc.token for acc in valid_accounts}

        if selected_token is not None and selected_token not in valid_tokens:
            QMessageBox.information(self, "提示", "未找到可用账号，请先验证账号")
            return

        target_rule_lists = [self.discord_manager.rules]
        if self.workspaces:
            target_rule_lists = [workspace.get("rules", []) for workspace in self.workspaces]

        for rule_list in target_rule_lists:
            for rule in rule_list:
                rule.account_ids = [selected_token] if selected_token else []

        self.refresh_runtime_contexts_from_workspaces()
        self.update_rules_list()
        self.save_config()
        QMessageBox.information(self, "成功", "自动回复账号设置已应用到所有规则")

    def apply_global_posting_accounts(self):
        """应用全局账号设置到所有发帖任务"""
        current_index = self.posting_accounts_combo.currentIndex()

        if current_index == 0:
            # 随机使用所有账号
            self.discord_manager.posting_account_tokens = []
            self.refresh_runtime_contexts_from_workspaces()
            self.save_config()
            QMessageBox.information(self, "提示", "发帖任务将随机使用所有可用账号")
        else:
            # 仅使用指定账号
            selected_account_index = current_index - 1
            valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
            if selected_account_index < len(valid_accounts):
                selected_account = valid_accounts[selected_account_index]
                self.discord_manager.posting_account_tokens = [selected_account.token]
                self.refresh_runtime_contexts_from_workspaces()
                self.save_config()
                QMessageBox.information(self, "提示", f"发帖任务仅使用账号：{selected_account.alias}")
            else:
                QMessageBox.information(self, "提示", "未找到可用账号，请先验证账号")

    def apply_global_comment_accounts(self):
        """应用全局账号设置到所有评论任务"""
        current_index = self.comment_accounts_combo.currentIndex()

        if current_index == 0:
            # 随机使用所有账号
            self.discord_manager.comment_account_tokens = []
            self.refresh_runtime_contexts_from_workspaces()
            self.save_config()
            QMessageBox.information(self, "提示", "评论任务将随机使用所有可用账号")
        else:
            # 仅使用指定账号
            selected_account_index = current_index - 1
            valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
            if selected_account_index < len(valid_accounts):
                selected_account = valid_accounts[selected_account_index]
                self.discord_manager.comment_account_tokens = [selected_account.token]
                self.refresh_runtime_contexts_from_workspaces()
                self.save_config()
                QMessageBox.information(self, "提示", f"评论任务仅使用账号：{selected_account.alias}")
            else:
                QMessageBox.information(self, "提示", "未找到可用账号，请先验证账号")

    def revalidate_all_accounts(self):
        """重新验证所有账号"""
        if not self.discord_manager.accounts:
            QMessageBox.information(self, "提示", "没有账号需要验证")
            return

            self.add_log("开始重新验证所有账号", "info")

        # 在新的事件循环中运行异步验证
        import asyncio
        try:
            async def revalidate_all():
                results = await self.discord_manager.revalidate_all_accounts()
                return results

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(revalidate_all())

            success_count = 0
            fail_count = 0

            for result in results:
                alias = result['alias']
                is_valid = result['is_valid']
                error_msg = result['error_msg']

                if is_valid:
                    user_info = result['user_info']
                    if user_info and isinstance(user_info, dict):
                        username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
                        self.add_log(f"账号 '{alias}' 验证成功 - 用户名: {username}", "success")
                    else:
                        self.add_log(f"账号 '{alias}' 验证成功", "success")
                    success_count += 1
                else:
                    self.add_log(f"账号 '{alias}' 验证失败: {error_msg}", "error")
                    fail_count += 1

            self.add_log(f"批量验证完成 - 成功: {success_count}, 失败: {fail_count}", "info")
            self.update_accounts_list()
            self.save_config()

            QMessageBox.information(
                self, "批量验证完成",
                f"验证完成\n成功: {success_count}\n失败: {fail_count}"
            )

        except Exception as e:
            error_msg = f"批量验证过程中出错: {str(e)}"
            self.add_log(error_msg, "error")
            QMessageBox.critical(self, "验证错误", error_msg)

    def revalidate_account_by_token(self, token):
        """重新验证账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.token == token), None)
        if account:
            self.add_log(f"正在重新验证账号 '{account.alias}'", "info")
        else:
            self.add_log("账号不存在", "error")
            return

        # 在新的事件循环中运行异步验证
        import asyncio
        try:
            async def revalidate():
                success, message = await self.discord_manager.revalidate_account(account.token)
                return success, message

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, message = loop.run_until_complete(revalidate())

            if success:
                self.add_log(message, "success")
                QMessageBox.information(self, "验证成功", message)
            else:
                self.log_text.append(f"❌ {message}")
                QMessageBox.warning(self, "验证失败", message)

            self.update_accounts_list()
            self.save_config()

        except Exception as e:
            error_msg = f"验证过程中出错: {str(e)}"
            self.add_log(error_msg, "error")
            QMessageBox.critical(self, "验证错误", error_msg)

    def revalidate_account_by_alias(self, alias):
        """通过别名重新验证账号（兼容旧调用）"""
        account = next((acc for acc in self.discord_manager.accounts if acc.alias == alias), None)
        if not account:
            self.add_log("账号不存在", "error")
            return
        self.revalidate_account_by_token(account.token)

    def remove_account_by_token(self, token):
        """通过token删除账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.token == token), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除账号 '{account.alias}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_account(token)
            self.add_log(f"账号 '{account.alias}' 已删除", "info")
            self.update_accounts_list()
            self.save_config()

    def remove_account_by_alias(self, alias):
        """通过别名删除账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.alias == alias), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除账号 '{alias}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_account(account.token)
            self.update_accounts_list()
            self.save_config()

    def remove_multiple_accounts(self, indices):
        """批量删除多个账号"""
        indices.sort(reverse=True)  # 从大到小排序，避免删除时索引变化

        reply = QMessageBox.question(
            self, "确认批量删除",
            f"确定要删除选中的 {len(indices)} 个账号吗？\n此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for index in indices:
                try:
                    # 获取账号信息用于日志
                    if index < len(self.discord_manager.accounts):
                        account = self.discord_manager.accounts[index]
                        account_name = account.alias
                        self.discord_manager.remove_account(account.token)
                        deleted_count += 1
                        self.add_log(f"账号 '{account_name}' 已删除", "info")
                except (IndexError, ValueError) as e:
                    # 账号可能已经被删除，跳过
                    continue

            self.update_accounts_list()
            self.save_config()
            self.add_log(f"成功删除 {deleted_count} 个账号", "success")


    def add_rule(self):
        """添加新规则"""
        dialog = RuleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_rule_data()

            if not data['keywords'] or not data['reply']:
                QMessageBox.warning(self, "错误", "关键词和回复内容不能为空")
                return

            self.discord_manager.add_rule(
                data['keywords'],
                data['reply'],
                MatchType(data['match_type']),
                data['target_channels'],
                data['delay_min'],
                data['delay_max'],
                data.get('ignore_replies', False),
                data.get('ignore_mentions', False),
                data.get('case_sensitive', False),
                data.get('image_path'),
                data.get('account_ids')
            )

            # 设置激活状态
            if self.discord_manager.rules:
                self.discord_manager.rules[-1].is_active = data['is_active']

            self.update_rules_list()
            self.save_config()
            QMessageBox.information(self, "成功", "规则添加成功")

    def edit_rule_by_index(self, index):
        """通过索引编辑规则"""
        if 0 <= index < len(self.discord_manager.rules):
            rule = self.discord_manager.rules[index]
            dialog = RuleDialog(self, rule)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                data = dialog.get_rule_data()

                if not data['keywords'] or not data['reply']:
                    QMessageBox.warning(self, "错误", "关键词和回复内容不能为空")
                    return

                self.discord_manager.update_rule(
                    index,
                    keywords=data['keywords'],
                    reply=data['reply'],
                    match_type=MatchType(data['match_type']),
                    target_channels=data['target_channels'],
                    delay_min=data['delay_min'],
                    delay_max=data['delay_max'],
                    is_active=data['is_active'],
                    ignore_replies=data.get('ignore_replies', False),
                    ignore_mentions=data.get('ignore_mentions', False),
                    case_sensitive=data.get('case_sensitive', False),
                    image_path=data.get('image_path'),
                    account_ids=data.get('account_ids')
                )

                self.update_rules_list()
                self.save_config()
                QMessageBox.information(self, "成功", "规则编辑成功")

    def remove_rule_by_index(self, index):
        """通过索引删除规则"""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除规则 {index+1} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_rule(index)
            self.update_rules_list()
            self.save_config()

    def remove_multiple_rules(self, indices):
        """批量删除多个规则"""
        indices.sort(reverse=True)  # 从大到小排序，避免删除时索引变化

        reply = QMessageBox.question(
            self, "确认批量删除",
            f"确定要删除选中的 {len(indices)} 个规则吗？\n此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for index in indices:
                try:
                    self.discord_manager.remove_rule(index)
                    deleted_count += 1
                except IndexError:
                    # 规则可能已经被删除，跳过
                    continue

            self.update_rules_list()
            self.save_config()
            self.add_log(f"成功删除 {deleted_count} 个规则", "success")

    def clear_rules(self):
        """一键删除所有自动回复规则"""
        if not self.discord_manager.rules:
            QMessageBox.information(self, "提示", "当前没有自动回复规则")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除所有自动回复规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.rules.clear()
            self.update_rules_list()
            self.save_config()
            self.add_log("所有自动回复规则已删除", "info")




    def has_enabled_reply_rules(self) -> bool:
        """检查所有已启用自动回复的页面是否至少配置了一条规则"""
        if self.workspaces:
            for index, workspace in enumerate(self.workspaces):
                self.ensure_workspace_defaults(workspace, index)
                features = workspace.get("features", {})
                if features.get("reply_enabled") and workspace.get("rules"):
                    return True
            return False

        return bool(self.discord_manager.rules)

    def start_bot(self):
        """启动账号"""
        self.add_log("🔄 正在检查启动条件...", "info")

        # 启动前刷新一次多页面运行上下文
        self.refresh_runtime_contexts_from_workspaces()

        if not self.discord_manager.accounts:
            self.add_log("❌ 启动失败：请先添加至少一个账号", "error")
            QMessageBox.warning(self, "错误", "请先添加至少一个账号")
            return

        # 只有启用自动回复功能时才需要检查规则
        if self.discord_manager.reply_enabled and not self.has_enabled_reply_rules():
            self.add_log("❌ 启动失败：启用自动回复功能时请先添加至少一个规则", "error")
            QMessageBox.warning(self, "错误", "启用自动回复功能时请先添加至少一个规则")
            return

        # 检查是否有有效的账号
        valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
        if not valid_accounts:
            self.add_log("❌ 启动失败：没有有效的账号（请先验证账号）", "error")
            QMessageBox.warning(self, "错误", "没有有效的账号，请先验证账号")
            return

        try:
            self.add_log("🚀 正在启动账号...", "info")

            self.worker_thread = WorkerThread(self.discord_manager)
            self.worker_thread.status_updated.connect(self.update_status)
            self.worker_thread.error_occurred.connect(self.on_error)
            self.worker_thread.log_message.connect(self.add_log)
            self.worker_thread.start()

            # 更新切换按钮状态
            self.bot_toggle_button.setChecked(True)
            self.bot_toggle_button.setText("⏹️ 停止账号")

            self.add_log("✅ 账号启动命令已发送，正在连接服务器...", "success")

        except Exception as e:
            error_msg = f"启动失败: {str(e)}"
            self.add_log(f"❌ {error_msg}", "error")
            QMessageBox.critical(self, "错误", error_msg)
            # 启动失败时重置按钮状态
            self.bot_toggle_button.setChecked(False)
            self.bot_toggle_button.setText("▶️ 启动账号")

    def stop_bot(self):
        """停止账号"""
        if self.worker_thread:
            self.add_log("正在停止账号...", "info")

            # 设置停止标志
            self.worker_thread.running = False

            # 等待线程完成，最多等待12秒（增加等待时间）
            if self.worker_thread.wait(12000):  # 增加等待时间到12秒
                self.add_log("账号停止完成", "success")
            else:
                self.add_log("账号停止超时，但后台清理将继续进行", "warning")

            # 清理线程
            self.worker_thread = None

            # 更新切换按钮状态
            self.bot_toggle_button.setChecked(False)
            self.bot_toggle_button.setText("▶️ 启动账号")

            # 强制更新状态显示
            self.update_status()

            # 添加最终日志
            self.add_log("账号已停止", "info")

    def toggle_bot(self):
        """切换账号启动/停止状态"""
        if self.bot_toggle_button.isChecked():
            # 启动账号
            self.start_bot()
        else:
            # 停止账号
            self.stop_bot()

    def add_log(self, message, level="info"):
        """添加日志"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # 根据级别设置颜色和前缀
        if level == "error":
            colored_msg = f'<span style="color: red;">[{timestamp}] ❌ {message}</span>'
        elif level == "warning":
            colored_msg = f'<span style="color: orange;">[{timestamp}] ⚠️ {message}</span>'
        elif level == "success":
            colored_msg = f'<span style="color: green;">[{timestamp}] ✅ {message}</span>'
        elif level == "info":
            colored_msg = f'<span style="color: blue;">[{timestamp}] ℹ️ {message}</span>'
        else:
            colored_msg = f'[{timestamp}] {message}'

        # 添加到日志文本框，增加行距
        current_text = self.log_text.toHtml()
        if current_text:
            new_text = current_text + '<div style="margin: 2px 0;">' + colored_msg + '</div>'
        else:
            new_text = '<div style="margin: 2px 0;">' + colored_msg + '</div>'

        self.log_text.setHtml(new_text)

        # 自动滚动到底部
        if self.auto_scroll_log:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_text.setTextCursor(cursor)

    def add_log_thread_safe(self, message, level="info"):
        """线程安全的日志添加"""
        self.log_signal.emit(message, level)

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.add_log("日志已清空", "info")

    def closeEvent(self, event):
        """窗口关闭事件"""
        try:
            self.save_config()
        except Exception as e:
            print(f"保存配置失败: {e}")

        if self.worker_thread and self.worker_thread.running:
            self.worker_thread.running = False
        event.accept()

    def toggle_auto_scroll(self, state):
        """切换自动滚动"""
        self.auto_scroll_log = state == 2  # 2表示选中状态

    def on_rotation_enabled_changed(self, state):
        """轮换启用状态改变"""
        enabled = state == Qt.CheckState.Checked

        # 更新DiscordManager设置
        self.discord_manager.rotation_enabled = enabled
        if enabled:
            self.discord_manager.rotation_interval = self.rotation_interval_spin.value() * 60  # 转换为秒
            self.rotation_status_label.setText(f"轮换模式: 已启用 (间隔{self.rotation_interval_spin.value()}分钟)")
        else:
            self.rotation_status_label.setText("轮换模式: 未启用")

        # 保存配置
        self.save_config()

        # 记录日志
        status = "启用" if enabled else "禁用"
        self.add_log(f"账号轮换模式已{status}")

    def on_error(self, error_msg):
        """错误处理"""
        QMessageBox.critical(self, "错误", f"运行时错误: {error_msg}")
        self.add_log(f"运行时错误: {error_msg}", "error")

    def export_config(self):
        """导出配置"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "", "JSON 文件 (*.json)"
        )
        if filename:
            if self.config_manager.export_config(
                filename, self.discord_manager.accounts, self.discord_manager.rules
            ):
                QMessageBox.information(self, "成功", "配置导出成功")
            else:
                QMessageBox.warning(self, "错误", "配置导出失败")

    def import_config(self):
        """导入配置"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入配置", "", "JSON 文件 (*.json)"
        )
        if filename:
            accounts, rules = self.config_manager.import_config(filename)
            if accounts or rules:
                self.discord_manager.accounts = accounts
                self.discord_manager.rules = rules
                self.update_accounts_list()
                self.update_rules_list()
                self.update_license_status()
                self.save_config()
                QMessageBox.information(self, "成功", "配置导入成功")
            else:
                QMessageBox.warning(self, "错误", "配置导入失败")

    def update_license_status(self):
        """更新许可证状态显示"""
        if self.discord_manager.license_manager.is_license_valid():
            license_info = self.discord_manager.license_manager.get_license_info()
            status_text = None
            if isinstance(license_info, dict):
                days = license_info.get("days")
                expiry = license_info.get("expiry")
                if isinstance(days, int):
                    if days == -1:
                        status_text = "有效期: 永久"
                    else:
                        status_text = f"有效期: {days}天"
                elif expiry and expiry not in ("Unknown", "未知"):
                    status_text = f"激活至: {expiry}"

            if not status_text:
                status_text = "激活状态: 有效"

            self.license_status_label.setText(status_text)
            self.license_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.license_status_label.setText("未激活")
            self.license_status_label.setStyleSheet("color: red; font-weight: bold;")

    def check_license(self):
        """检查许可证"""
        # 已通过本地验证则不再请求服务器
        if self.discord_manager.license_manager.is_license_valid():
            self.update_license_status()
            return

        # 从配置中读取许可证密钥
        license_config = self.config_manager.load_config()[2]  # 获取许可证配置
        license_key = license_config.get("license_key", "").strip()

        if not license_key:
            # 没有配置许可证密钥，直接显示输入对话框
            self.show_license_input_dialog()
            return

        try:
            # 尝试激活/验证配置中的许可证密钥
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, message = loop.run_until_complete(
                self.discord_manager.license_manager.validate_license(license_key)
            )
            loop.close()

            if success:
                self.license_key = license_key
                self.update_license_status()
                self.save_config()
                return
            else:
                # 许可证无效或其他错误
                self.add_log(f"❌ 许可证验证失败: {message}", "error")
                QMessageBox.warning(self, "验证失败", message)
        except Exception as e:
            self.add_log(f"❌ 许可证检查出错: {e}", "error")
            QMessageBox.warning(self, "错误", f"许可证检查出错：{e}")

        # 许可证无效或其他问题，显示输入对话框
        self.show_license_input_dialog()

    def show_license_input_dialog(self):
        """显示许可证输入对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("许可证验证")
        dialog.setModal(True)
        dialog.resize(400, 200)

        layout = QVBoxLayout(dialog)

        # 标题
        title_label = QLabel("请输入许可证密钥")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # 许可证输入框
        self.license_key_input = QLineEdit()
        self.license_key_input.setPlaceholderText("输入许可证密钥...")

        # 如果配置文件中有许可证密钥，则显示它
        license_config = self.config_manager.load_config()[2]  # 获取许可证配置
        saved_license_key = license_config.get("license_key", "")
        if saved_license_key:
            self.license_key_input.setText(saved_license_key)
        else:
            self.license_key_input.setText("")  # 空值让用户手动输入
        layout.addWidget(self.license_key_input)

        # 状态显示
        self.license_status_display = QLabel("")
        self.license_status_display.setStyleSheet("color: #666; margin-top: 5px;")
        layout.addWidget(self.license_status_display)

        # 按钮
        button_layout = QHBoxLayout()

        verify_button = QPushButton("验证")
        verify_button.clicked.connect(lambda: self.verify_license_key(dialog))
        button_layout.addWidget(verify_button)

        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

        # 显示对话框
        result = dialog.exec()

        # 如果用户点击取消，显示警告并重新显示对话框
        while result != QDialog.DialogCode.Accepted:
            reply = QMessageBox.question(
                self, "需要许可证",
                "软件需要有效的许可证才能运行。\n\n"
                "如果您没有许可证，请联系管理员获取。\n\n"
                "是否重新输入许可证？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # 重新显示对话框
                result = dialog.exec()
            else:
                # 用户确认退出
                QMessageBox.information(self, "退出", "软件将退出。")
                sys.exit(0)

    def verify_license_key(self, dialog):
        """验证许可证密钥"""
        license_key = self.license_key_input.text().strip()
        if not license_key:
            QMessageBox.warning(dialog, "警告", "请输入许可证密钥")
            return

        self.license_status_display.setText("🔄 正在验证许可证...")
        self.license_status_display.setStyleSheet("color: blue;")

        # 在新线程中验证并激活许可证
        self.license_verify_thread = LicenseVerifyThread(self.discord_manager.license_manager, license_key, activate=True)
        self.license_verify_thread.finished.connect(lambda success, message: self.on_license_verify_finished(dialog, success, message))
        self.license_verify_thread.error.connect(lambda error: self.on_license_verify_error(dialog, error))
        self.license_verify_thread.start()

    def on_license_verify_finished(self, dialog, success, message):
        """许可证验证完成"""
        if success:
            # 保存成功的许可证密钥
            self.license_key = self.license_key_input.text().strip()

            self.license_status_display.setText("✅ 许可证验证成功!")
            self.license_status_display.setStyleSheet("color: green;")
            QMessageBox.information(dialog, "成功", f"许可证验证成功!\n{message}")
            self.update_license_status()

            # 保存配置
            self.save_config()

            dialog.accept()
        else:
            self.license_status_display.setText(f"❌ 验证失败: {message}")
            self.license_status_display.setStyleSheet("color: red;")

            # 提供更友好的错误提示
            if "已被其他设备激活" in message:
                friendly_message = f"{message}\n\n请联系管理员获取新的许可证。"
            elif "超时" in message or "网络" in message:
                friendly_message = f"{message}\n\n请检查网络连接后重试。"
            else:
                friendly_message = f"{message}\n\n请确认许可证密钥是否正确。"

            QMessageBox.warning(dialog, "验证失败", friendly_message)

    def on_license_verify_error(self, dialog, error):
        """许可证验证错误"""
        self.license_status_display.setText(f"❌ 验证错误: {error}")
        self.license_status_display.setStyleSheet("color: red;")
        QMessageBox.critical(dialog, "错误", f"验证过程中发生错误: {error}")

        # ============ 功能切换 ============

    def toggle_auto_reply(self):
        """切换自动回复功能"""
        is_checked = self.reply_toggle_button.isChecked()
        workspace = self.get_active_workspace()
        if workspace is None:
            return

        features = self.get_active_workspace_features()
        features["reply_enabled"] = is_checked

        if is_checked:
            delay = max(0, getattr(self.discord_manager, "reply_start_delay", 0))
            features["reply_start_at"] = time.time() + delay if delay > 0 else None
        else:
            features["reply_start_at"] = None

        workspace["features"] = features
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

        if is_checked:
            self.reply_toggle_button.setText("📝 自动回复: 开启")
            if features.get("reply_start_at"):
                remaining = int(features["reply_start_at"] - time.time())
                self.add_log(f"自动回复已开启，将在 {max(0, remaining)} 秒后启动", "info")
            else:
                self.add_log("自动回复已开启", "info")
        else:
            self.reply_toggle_button.setText("📝 自动回复: 关闭")
            self.add_log("自动回复已关闭", "info")

    def toggle_auto_posting(self):
        """切换自动发帖功能"""
        is_checked = self.posting_toggle_button.isChecked()
        workspace = self.get_active_workspace()
        if workspace is None:
            return

        features = self.get_active_workspace_features()
        features["posting_enabled"] = is_checked

        if is_checked:
            delay = max(0, getattr(self.discord_manager, "posting_start_delay", 0))
            features["posting_start_at"] = time.time() + delay if delay > 0 else None
        else:
            features["posting_start_at"] = None

        workspace["features"] = features
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

        if is_checked:
            self.posting_toggle_button.setText("📄 自动发帖: 开启")
            if features.get("posting_start_at"):
                remaining = int(features["posting_start_at"] - time.time())
                self.add_log(f"自动发帖已启用，将在 {max(0, remaining)} 秒后启动", "info")
            else:
                self.add_log("自动发帖已启用", "info")
        else:
            self.posting_toggle_button.setText("📄 自动发帖: 关闭")
            self.add_log("自动发帖已禁用", "info")

    def toggle_auto_comment(self):
        """切换自动评论功能"""
        is_checked = self.comment_toggle_button.isChecked()
        workspace = self.get_active_workspace()
        if workspace is None:
            return

        features = self.get_active_workspace_features()
        features["comment_enabled"] = is_checked

        if is_checked:
            delay = max(0, getattr(self.discord_manager, "comment_start_delay", 0))
            features["comment_start_at"] = time.time() + delay if delay > 0 else None
        else:
            features["comment_start_at"] = None

        workspace["features"] = features
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

        if is_checked:
            self.comment_toggle_button.setText("💬 自动评论: 开启")
            if features.get("comment_start_at"):
                remaining = int(features["comment_start_at"] - time.time())
                self.add_log(f"自动评论已启用，将在 {max(0, remaining)} 秒后启动", "info")
            else:
                self.add_log("自动评论已启用", "info")
        else:
            self.comment_toggle_button.setText("💬 自动评论: 关闭")
            self.add_log("自动评论已禁用", "info")

        # ============ 发帖功能 ============

    def on_posting_enabled_changed(self, state):
        """发帖启用状态改变（向后兼容）"""
        enabled = state == Qt.CheckState.Checked
        self.posting_toggle_button.setChecked(enabled)
        self.toggle_auto_posting()

    def on_posting_rotation_enabled_changed(self, state):
        """发帖轮换启用状态改变"""
        enabled = state == Qt.CheckState.Checked
        self.discord_manager.posting_rotation_enabled = enabled
        self.discord_manager.posting_rotation_count = self.posting_rotation_count_spin.value()
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()
        if enabled:
            self.add_log(f"发帖账号轮换已启用 (每{self.posting_rotation_count_spin.value()}条轮换)", "info")
        else:
            self.add_log("发帖账号轮换已禁用", "info")

    def on_posting_rotation_count_changed(self, value=None):
        """发帖轮换条数改变"""
        if value is None:
            value = self.posting_rotation_count_spin.value()
        self.discord_manager.posting_rotation_count = max(1, int(value))
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def on_comment_rotation_enabled_changed(self, state):
        """评论轮换启用状态改变"""
        enabled = state == Qt.CheckState.Checked
        self.discord_manager.comment_rotation_enabled = enabled
        self.discord_manager.comment_rotation_count = self.comment_rotation_count_spin.value()
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()
        if enabled:
            self.add_log(f"评论账号轮换已启用 (每{self.comment_rotation_count_spin.value()}条轮换)", "info")
        else:
            self.add_log("评论账号轮换已禁用", "info")

    def on_comment_rotation_count_changed(self, value=None):
        """评论轮换条数改变"""
        if value is None:
            value = self.comment_rotation_count_spin.value()
        self.discord_manager.comment_rotation_count = max(1, int(value))
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def add_posting_task(self):
        """添加发帖任务"""
        dialog = PostingTaskDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                data = dialog.get_data()
            except ValueError:
                QMessageBox.warning(self, "错误", "频道ID格式错误，请输入数字")
                return
            if data['channel_id'] is None and not self.discord_manager.default_posting_channel_id:
                QMessageBox.warning(self, "错误", "请输入频道ID或先设置默认频道")
                return
            task_id = self.discord_manager.add_posting_task(
                data['content'],
                data['channel_id'],
                data['image_path'],
                0,  # 使用全局发帖间隔，不再有单独延时
                data['title'],
                data.get('tags')
            )
            self.update_posting_tasks_list()
            self.save_config()
            self.add_log(f"发帖任务已添加: {task_id}", "info")

    def import_posting_materials(self):
        """自动读取发帖素材"""
        folder = QFileDialog.getExistingDirectory(self, "选择素材文件夹")
        if not folder:
            return

        def parse_tags(value):
            if not value:
                return []
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
            text = str(value).strip()
            separators = [';', ',', '\n']
            for sep in separators:
                if sep in text:
                    return [t.strip() for t in text.split(sep) if t.strip()]
            return [text]

        def parse_task_dict(data):
            if not isinstance(data, dict):
                return None
            content = (
                data.get("content")
                or data.get("text")
                or data.get("body")
                or data.get("内容")
                or data.get("正文")
                or data.get("文案")
            )
            if isinstance(content, list):
                content = "\n".join(str(v) for v in content if v is not None)
            if content is not None:
                content = str(content).strip()
            title = data.get("title") or data.get("标题")
            if title is not None:
                title = str(title).strip()
            channel_value = (
                data.get("channel_id")
                or data.get("channel")
                or data.get("channelId")
                or data.get("频道")
                or data.get("频道ID")
            )
            channel_id = None
            if channel_value:
                channel_text = str(channel_value).strip().replace("<#", "").replace(">", "")
                try:
                    channel_id = int(channel_text)
                except ValueError:
                    parts = [part for part in channel_text.split("/") if part]
                    for part in reversed(parts):
                        if part.isdigit():
                            channel_id = int(part)
                            break
            image_value = (
                data.get("image_path")
                or data.get("images")
                or data.get("image")
                or data.get("图片")
                or data.get("图片路径")
            )
            image_path = None
            if isinstance(image_value, list):
                image_path = ";".join(str(v) for v in image_value if str(v).strip())
            elif image_value:
                image_path = str(image_value).strip()
            tags = parse_tags(data.get("tags") or data.get("标签"))
            return {
                "content": content,
                "title": title or None,
                "channel_id": channel_id,
                "image_path": image_path or None,
                "tags": tags
            }

        def parse_task_folder(path):
            content = None
            title = None
            channel_id = None
            tags = []

            title_path = None
            for name in ("title.txt", "标题.txt"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    title_path = candidate
                    break
            if title_path and os.path.exists(title_path):
                with open(title_path, "r", encoding="utf-8") as f:
                    title = f.read().strip()

            channel_path = None
            for name in ("channel.txt", "channels.txt", "channel_id.txt", "频道.txt", "频道ID.txt", "频道id.txt"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    channel_path = candidate
                    break
            if channel_path and os.path.exists(channel_path):
                with open(channel_path, "r", encoding="utf-8") as f:
                    channel_text = f.read().strip()
                if channel_text:
                    channel_text = channel_text.replace("<#", "").replace(">", "")
                    try:
                        channel_id = int(channel_text)
                    except ValueError:
                        parts = [part for part in channel_text.split("/") if part]
                        for part in reversed(parts):
                            if part.isdigit():
                                channel_id = int(part)
                                break

            tags_path = None
            for name in ("tags.txt", "标签.txt"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    tags_path = candidate
                    break
            if tags_path and os.path.exists(tags_path):
                with open(tags_path, "r", encoding="utf-8") as f:
                    tags = parse_tags(f.read())

            content_path = None
            for name in ("content.txt", "内容.txt", "正文.txt", "文案.txt", "text.txt"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    content_path = candidate
                    break
            if content_path and os.path.exists(content_path):
                with open(content_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            else:
                text_files = [
                    f for f in os.listdir(path)
                    if f.lower().endswith((".txt", ".md"))
                    and f.lower() not in (
                        "title.txt", "channel.txt", "channels.txt", "channel_id.txt",
                        "tags.txt", "match_type.txt"
                    )
                    and f not in ("标题.txt", "频道.txt", "频道ID.txt", "频道id.txt", "标签.txt", "匹配类型.txt")
                ]
                if text_files:
                    first_text = os.path.join(path, text_files[0])
                    with open(first_text, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if not title:
                        title = os.path.splitext(text_files[0])[0]

            image_files = []
            for name in os.listdir(path):
                lower_name = name.lower()
                if lower_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                    image_files.append(os.path.join(path, name))
            image_path = ";".join(image_files) if image_files else None

            return {
                "content": content,
                "title": title or None,
                "channel_id": channel_id,
                "image_path": image_path,
                "tags": tags
            }

        tasks = []
        json_files = [f for f in os.listdir(folder) if f.lower().endswith(".json")]
        csv_files = [f for f in os.listdir(folder) if f.lower().endswith(".csv")]

        for filename in json_files:
            try:
                with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        task = parse_task_dict(item)
                        if task:
                            tasks.append(task)
                elif isinstance(data, dict):
                    items = data.get("tasks") or data.get("data") or data.get("posts") or data.get("素材")
                    if isinstance(items, list):
                        for item in items:
                            task = parse_task_dict(item)
                            if task:
                                tasks.append(task)
                    else:
                        task = parse_task_dict(data)
                        if task:
                            tasks.append(task)
            except Exception as e:
                self.add_log(f"读取JSON失败: {filename} - {e}", "warning")

        for filename in csv_files:
            try:
                with open(os.path.join(folder, filename), "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        task = parse_task_dict(row)
                        if task:
                            tasks.append(task)
            except Exception as e:
                self.add_log(f"读取CSV失败: {filename} - {e}", "warning")

        if not tasks:
            subdirs = [os.path.join(folder, d) for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
            if subdirs:
                for subdir in sorted(subdirs):
                    task = parse_task_folder(subdir)
                    if task:
                        tasks.append(task)
            else:
                text_files = [f for f in os.listdir(folder) if f.lower().endswith((".txt", ".md"))]
                for filename in sorted(text_files):
                    with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if not content:
                        continue
                    title = os.path.splitext(filename)[0]
                    base_name = os.path.splitext(filename)[0]
                    image_path = None
                    for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                        candidate = os.path.join(folder, base_name + ext)
                        if os.path.exists(candidate):
                            image_path = candidate
                            break
                    tasks.append({
                        "content": content,
                        "title": title,
                        "channel_id": None,
                        "image_path": image_path,
                        "tags": []
                    })

        if not tasks:
            QMessageBox.information(self, "提示", "未发现可读取的素材")
            return

        added = 0
        skipped = 0
        for task in tasks:
            content = task.get("content")
            if not content:
                skipped += 1
                continue
            channel_id = task.get("channel_id")
            if channel_id is None and not self.discord_manager.default_posting_channel_id:
                skipped += 1
                continue
            self.discord_manager.add_posting_task(
                content,
                channel_id,
                task.get("image_path"),
                0,
                task.get("title"),
                task.get("tags")
            )
            added += 1

        self.update_posting_tasks_list()
        self.save_config()
        QMessageBox.information(self, "完成", f"已读取 {added} 条素材，跳过 {skipped} 条")

    def import_comment_materials(self):
        """自动读取评论素材"""
        folder = QFileDialog.getExistingDirectory(self, "选择评论素材文件夹")
        if not folder:
            return

        import re

        def split_simple_text(value):
            if value is None:
                return []
            if isinstance(value, list):
                items = []
                for item in value:
                    items.extend(split_simple_text(item))
                return [v for v in items if v]
            text = str(value).strip()
            if not text:
                return []
            return [v.strip() for v in re.split(r"[\n,;，；]+", text) if v.strip()]

        def parse_comment_blocks(value):
            if value is None:
                return []
            if isinstance(value, list):
                blocks = []
                for item in value:
                    text = str(item).strip()
                    if text:
                        blocks.append(text)
                return blocks

            text = str(value).strip()
            if not text:
                return []

            sep_blocks = [b.strip() for b in re.split(r"\n(?:-{3,}|={3,})\n", text) if b.strip()]
            if len(sep_blocks) > 1:
                return sep_blocks

            line_blocks = [line.strip() for line in text.splitlines() if line.strip()]
            return line_blocks if len(line_blocks) > 1 else [text]

        def normalize_image_path(value, base_dir):
            if not value:
                return None

            raw_paths = []
            if isinstance(value, list):
                for item in value:
                    if item:
                        raw_paths.extend(split_simple_text(item))
            else:
                raw_paths.extend(split_simple_text(value))

            if not raw_paths:
                return None

            resolved = []
            for raw in raw_paths:
                candidate = raw
                if not os.path.isabs(candidate):
                    joined = os.path.join(base_dir, candidate)
                    if os.path.exists(joined):
                        candidate = joined
                resolved.append(candidate)

            unique_paths = []
            seen = set()
            for path in resolved:
                if path not in seen:
                    seen.add(path)
                    unique_paths.append(path)

            return ";".join(unique_paths) if unique_paths else None

        def build_comment_tasks(comments, links, image_path):
            comments = [c.strip() for c in comments if c and str(c).strip()]
            links = [l.strip() for l in links if l and str(l).strip()]
            if not comments or not links:
                return []

            if len(comments) == 1:
                return [{
                    "content": comments[0],
                    "links": links,
                    "image_path": image_path
                }]

            buckets = [[] for _ in comments]
            for idx, link in enumerate(links):
                buckets[idx % len(comments)].append(link)

            tasks = []
            for comment, bucket in zip(comments, buckets):
                if not bucket:
                    continue
                tasks.append({
                    "content": comment,
                    "links": bucket,
                    "image_path": image_path
                })
            return tasks

        def parse_comment_dict(data, base_dir):
            if not isinstance(data, dict):
                return []

            comment_value = (
                data.get("content")
                or data.get("comment")
                or data.get("comments")
                or data.get("reply")
                or data.get("text")
                or data.get("body")
                or data.get("内容")
                or data.get("评论")
                or data.get("文案")
                or data.get("正文")
            )
            comments = parse_comment_blocks(comment_value)
            title_value = data.get("title") or data.get("标题") or data.get("name")
            title_text = ""
            if title_value is not None:
                title_text = str(title_value).strip()
            if title_text:
                if comments:
                    comments = [
                        f"【{title_text}】\n{comment}" if title_text not in comment else comment
                        for comment in comments
                    ]
                else:
                    comments = [title_text]

            links_value = (
                data.get("message_link")
                or data.get("message_links")
                or data.get("links")
                or data.get("link")
                or data.get("url")
                or data.get("target")
                or data.get("channel_id")
                or data.get("channel")
                or data.get("链接")
                or data.get("地址")
                or data.get("帖子链接")
                or data.get("消息链接")
                or data.get("频道")
                or data.get("频道ID")
            )
            links = split_simple_text(links_value)

            image_value = (
                data.get("image_path")
                or data.get("images")
                or data.get("image")
                or data.get("图片")
                or data.get("图片路径")
            )
            image_path = normalize_image_path(image_value, base_dir)

            return build_comment_tasks(comments, links, image_path)

        def parse_task_folder(path):
            comments = []
            links = []
            title_text = ""

            for name in ("title.txt", "标题.txt"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        title_text = f.read().strip()
                    if title_text:
                        break

            for name in (
                "content.txt", "comment.txt", "comments.txt", "reply.txt", "text.txt",
                "内容.txt", "评论.txt", "文案.txt", "正文.txt"
            ):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        comments = parse_comment_blocks(f.read())
                    if comments:
                        break

            for name in (
                "links.txt", "link.txt", "url.txt", "urls.txt", "message_link.txt",
                "链接.txt", "地址.txt", "帖子链接.txt", "消息链接.txt"
            ):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        links = split_simple_text(f.read())
                    if links:
                        break

            image_files = []
            for file_name in os.listdir(path):
                if file_name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                    image_files.append(os.path.join(path, file_name))
            image_path = ";".join(sorted(image_files)) if image_files else None

            if title_text:
                if comments:
                    comments = [
                        f"【{title_text}】\n{comment}" if title_text not in comment else comment
                        for comment in comments
                    ]
                else:
                    comments = [title_text]

            return build_comment_tasks(comments, links, image_path)

        tasks = []
        json_files = [f for f in os.listdir(folder) if f.lower().endswith(".json")]
        csv_files = [f for f in os.listdir(folder) if f.lower().endswith(".csv")]

        for filename in json_files:
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for item in data:
                        tasks.extend(parse_comment_dict(item, folder))
                elif isinstance(data, dict):
                    payload = data.get("tasks") or data.get("data") or data.get("comments") or data.get("素材")
                    if isinstance(payload, list):
                        for item in payload:
                            tasks.extend(parse_comment_dict(item, folder))
                    else:
                        tasks.extend(parse_comment_dict(data, folder))
            except Exception as e:
                self.add_log(f"读取评论JSON失败: {filename} - {e}", "warning")

        for filename in csv_files:
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tasks.extend(parse_comment_dict(row, folder))
            except Exception as e:
                self.add_log(f"读取评论CSV失败: {filename} - {e}", "warning")

        if not tasks:
            links_file = None
            for name in ("links.txt", "link.txt", "url.txt", "urls.txt", "链接.txt", "地址.txt", "帖子链接.txt", "消息链接.txt"):
                candidate = os.path.join(folder, name)
                if os.path.exists(candidate):
                    links_file = candidate
                    break

            comments_file = None
            for name in ("comments.txt", "content.txt", "reply.txt", "text.txt", "内容.txt", "评论.txt", "文案.txt", "正文.txt"):
                candidate = os.path.join(folder, name)
                if os.path.exists(candidate):
                    comments_file = candidate
                    break

            title_file = None
            for name in ("title.txt", "标题.txt"):
                candidate = os.path.join(folder, name)
                if os.path.exists(candidate):
                    title_file = candidate
                    break

            if links_file and (comments_file or title_file):
                with open(links_file, "r", encoding="utf-8") as f:
                    links = split_simple_text(f.read())
                comments = []
                if comments_file:
                    with open(comments_file, "r", encoding="utf-8") as f:
                        comments = parse_comment_blocks(f.read())
                if not comments and title_file:
                    with open(title_file, "r", encoding="utf-8") as f:
                        title_text = f.read().strip()
                    if title_text:
                        comments = [title_text]
                tasks.extend(build_comment_tasks(comments, links, None))

        if not tasks:
            subdirs = [os.path.join(folder, d) for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
            for subdir in sorted(subdirs):
                tasks.extend(parse_task_folder(subdir))

        if not tasks:
            QMessageBox.information(self, "提示", "未发现可读取的评论素材")
            return

        added = 0
        skipped = 0
        for task in tasks:
            content = task.get("content", "").strip()
            links = [link.strip() for link in task.get("links", []) if link and str(link).strip()]
            if not content or not links:
                skipped += 1
                continue

            self.discord_manager.add_comment_task(
                content,
                "\n".join(links),
                task.get("image_path"),
                0
            )
            added += 1

        self.update_comment_tasks_list()
        self.save_config()
        QMessageBox.information(self, "完成", f"已读取 {added} 条评论任务，跳过 {skipped} 条")

    def import_reply_materials(self):
        """自动读取自动回复素材"""
        folder = QFileDialog.getExistingDirectory(self, "选择自动回复素材文件夹")
        if not folder:
            return

        import re

        def split_text(value):
            if value is None:
                return []
            if isinstance(value, list):
                items = []
                for item in value:
                    items.extend(split_text(item))
                return [v for v in items if v]
            text = str(value).strip()
            if not text:
                return []
            return [v.strip() for v in re.split(r"[\n,;，；]+", text) if v.strip()]

        def parse_bool(value, default=True):
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in ("1", "true", "yes", "y", "on", "是"):
                return True
            if text in ("0", "false", "no", "n", "off", "否"):
                return False
            return default

        def safe_float(value, default):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def extract_channel_id(raw):
            if raw is None:
                return None
            text = str(raw).strip().replace("<#", "").replace(">", "")
            if not text:
                return None
            if text.isdigit():
                try:
                    return int(text)
                except ValueError:
                    return None

            # 支持 Discord 链接:
            # https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
            match = re.search(r"/channels/\d+/(\d+)(?:/\d+)?", text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    return None

            parts = [part for part in re.split(r"[/?#]", text) if part]
            if "channels" in parts:
                idx = parts.index("channels")
                numeric_parts = [part for part in parts[idx + 1:] if part.isdigit()]
                if len(numeric_parts) >= 2:
                    try:
                        return int(numeric_parts[1])
                    except ValueError:
                        return None
                if len(numeric_parts) == 1:
                    try:
                        return int(numeric_parts[0])
                    except ValueError:
                        return None

            return None

        def normalize_image_path(value, base_dir):
            paths = []
            if isinstance(value, list):
                for item in value:
                    paths.extend(split_text(item))
            else:
                paths.extend(split_text(value))

            if not paths:
                return None

            resolved = []
            seen = set()
            for raw in paths:
                candidate = raw
                if not os.path.isabs(candidate):
                    joined = os.path.join(base_dir, candidate)
                    if os.path.exists(joined):
                        candidate = joined
                if candidate not in seen:
                    seen.add(candidate)
                    resolved.append(candidate)

            return ";".join(resolved) if resolved else None

        def parse_rule_dict(data, base_dir):
            if not isinstance(data, dict):
                return None

            keywords = (
                data.get("keywords")
                or data.get("keyword")
                or data.get("title")
                or data.get("titles")
                or data.get("name")
                or data.get("标题")
                or data.get("关键词")
            )
            keywords = split_text(keywords)

            reply_text = (
                data.get("reply")
                or data.get("content")
                or data.get("text")
                or data.get("body")
                or data.get("message")
                or data.get("内容")
                or data.get("正文")
                or data.get("文案")
            )
            if isinstance(reply_text, list):
                reply_text = "\n".join(str(v) for v in reply_text if v is not None)
            reply_text = str(reply_text).strip() if reply_text is not None else ""

            channels_raw = (
                data.get("channel_id")
                or data.get("channels")
                or data.get("channel")
                or data.get("link")
                or data.get("url")
                or data.get("链接")
                or data.get("频道")
                or data.get("频道ID")
                or data.get("频道链接")
                or data.get("内容链接")
                or data.get("消息链接")
                or data.get("帖子链接")
            )
            target_channels = []
            for token in split_text(channels_raw):
                channel_id = extract_channel_id(token)
                if channel_id is not None and channel_id not in target_channels:
                    target_channels.append(channel_id)

            match_type = str(data.get("match_type") or data.get("匹配类型") or "partial").lower()
            if match_type not in ("partial", "exact", "regex"):
                match_type = "partial"

            rule_data = {
                "keywords": keywords,
                "reply": reply_text,
                "match_type": match_type,
                "target_channels": target_channels,
                "delay_min": safe_float(data.get("delay_min") or data.get("最小延迟") or data.get("延迟下限") or 0.1, 0.1),
                "delay_max": safe_float(data.get("delay_max") or data.get("最大延迟") or data.get("延迟上限") or 1.0, 1.0),
                "is_active": parse_bool(data.get("is_active") if "is_active" in data else data.get("启用"), True),
                "ignore_replies": parse_bool(data.get("ignore_replies") if "ignore_replies" in data else data.get("忽略回复"), True),
                "ignore_mentions": parse_bool(data.get("ignore_mentions") if "ignore_mentions" in data else data.get("忽略提及"), True),
                "case_sensitive": parse_bool(data.get("case_sensitive") if "case_sensitive" in data else data.get("区分大小写"), False),
                "image_path": normalize_image_path(
                    data.get("image")
                    or data.get("images")
                    or data.get("image_path")
                    or data.get("图片")
                    or data.get("图片路径"),
                    base_dir
                ),
                "account_ids": split_text(
                    data.get("account_ids")
                    or data.get("accounts")
                    or data.get("账号")
                    or data.get("账号列表")
                )
            }

            if not rule_data["keywords"] or not rule_data["reply"]:
                return None
            if rule_data["delay_max"] < rule_data["delay_min"]:
                rule_data["delay_max"] = rule_data["delay_min"]
            return rule_data

        def parse_rule_folder(path):
            data = {}

            for file_name, key in (
                ("keywords.txt", "keywords"),
                ("keyword.txt", "keywords"),
                ("title.txt", "keywords"),
                ("标题.txt", "keywords"),
                ("关键词.txt", "keywords"),
                ("reply.txt", "reply"),
                ("content.txt", "reply"),
                ("text.txt", "reply"),
                ("内容.txt", "reply"),
                ("正文.txt", "reply"),
                ("文案.txt", "reply"),
                ("channel.txt", "channel"),
                ("channels.txt", "channels"),
                ("link.txt", "link"),
                ("频道.txt", "channel"),
                ("频道链接.txt", "link"),
                ("内容链接.txt", "link"),
                ("消息链接.txt", "link"),
                ("帖子链接.txt", "link"),
                ("链接.txt", "link"),
                ("match_type.txt", "match_type"),
                ("匹配类型.txt", "match_type"),
            ):
                candidate = os.path.join(path, file_name)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        data[key] = f.read().strip()

            if "keywords" not in data:
                data["keywords"] = os.path.basename(path)

            image_files = []
            for file_name in os.listdir(path):
                if file_name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                    image_files.append(os.path.join(path, file_name))
            if image_files:
                data["image_path"] = ";".join(sorted(image_files))

            return parse_rule_dict(data, path)

        rules_to_add = []
        json_files = [f for f in os.listdir(folder) if f.lower().endswith(".json")]
        csv_files = [f for f in os.listdir(folder) if f.lower().endswith(".csv")]

        for filename in json_files:
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for item in data:
                        rule_data = parse_rule_dict(item, folder)
                        if rule_data:
                            rules_to_add.append(rule_data)
                elif isinstance(data, dict):
                    payload = data.get("rules") or data.get("data") or data.get("tasks")
                    if isinstance(payload, list):
                        for item in payload:
                            rule_data = parse_rule_dict(item, folder)
                            if rule_data:
                                rules_to_add.append(rule_data)
                    else:
                        rule_data = parse_rule_dict(data, folder)
                        if rule_data:
                            rules_to_add.append(rule_data)
            except Exception as e:
                self.add_log(f"读取自动回复JSON失败: {filename} - {e}", "warning")

        for filename in csv_files:
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rule_data = parse_rule_dict(row, folder)
                        if rule_data:
                            rules_to_add.append(rule_data)
            except Exception as e:
                self.add_log(f"读取自动回复CSV失败: {filename} - {e}", "warning")

        if not rules_to_add:
            subdirs = [os.path.join(folder, d) for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
            for subdir in sorted(subdirs):
                rule_data = parse_rule_folder(subdir)
                if rule_data:
                    rules_to_add.append(rule_data)

        if not rules_to_add:
            text_files = [f for f in os.listdir(folder) if f.lower().endswith((".txt", ".md"))]
            for filename in sorted(text_files):
                if filename.lower() in ("keywords.txt", "keyword.txt", "reply.txt", "content.txt", "channel.txt", "channels.txt"):
                    continue
                file_path = os.path.join(folder, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    reply_text = f.read().strip()
                if not reply_text:
                    continue
                rules_to_add.append({
                    "keywords": [os.path.splitext(filename)[0]],
                    "reply": reply_text,
                    "match_type": "partial",
                    "target_channels": [],
                    "delay_min": 0.1,
                    "delay_max": 1.0,
                    "is_active": True,
                    "ignore_replies": True,
                    "ignore_mentions": True,
                    "case_sensitive": False,
                    "image_path": None,
                    "account_ids": []
                })

        if not rules_to_add:
            QMessageBox.information(self, "提示", "未发现可读取的自动回复素材")
            return

        added = 0
        skipped = 0
        for rule_data in rules_to_add:
            keywords = rule_data.get("keywords") or []
            reply_text = rule_data.get("reply", "").strip()
            if not keywords or not reply_text:
                skipped += 1
                continue

            self.discord_manager.add_rule(
                keywords,
                reply_text,
                MatchType(rule_data.get("match_type", "partial")),
                rule_data.get("target_channels", []),
                rule_data.get("delay_min", 0.1),
                rule_data.get("delay_max", 1.0),
                rule_data.get("ignore_replies", True),
                rule_data.get("ignore_mentions", True),
                rule_data.get("case_sensitive", False),
                rule_data.get("image_path"),
                rule_data.get("account_ids", [])
            )
            if self.discord_manager.rules:
                self.discord_manager.rules[-1].is_active = rule_data.get("is_active", True)
            added += 1

        self.update_rules_list()
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()
        QMessageBox.information(self, "完成", f"已读取 {added} 条自动回复规则，跳过 {skipped} 条")

    def remove_posting_task_by_id(self, row):
        """根据表格行号删除发帖任务（通过任务ID）"""
        # 从表格项中获取任务ID
        content_item = self.posting_tasks_table.item(row, 0)
        if not content_item:
            QMessageBox.warning(self, "错误", "无法获取任务信息")
            return

        task_id = content_item.data(Qt.ItemDataRole.UserRole)
        if not task_id:
            QMessageBox.warning(self, "错误", "无法获取任务ID")
            return

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除发帖任务 '{task_id}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 从DiscordManager中删除任务
            task_to_remove = None
            for task in self.discord_manager.posting_tasks:
                if task.id == task_id:
                    task_to_remove = task
                    break

            if task_to_remove:
                self.discord_manager.posting_tasks.remove(task_to_remove)
                self.update_posting_tasks_list()
                self.save_config()
                self.add_log(f"发帖任务已删除: {task_id}", "info")
                QMessageBox.information(self, "成功", "发帖任务已删除")
            else:
                QMessageBox.warning(self, "错误", "未找到要删除的任务")

    def clear_posting_tasks(self):
        """一键删除所有发帖任务"""
        if not self.discord_manager.posting_tasks:
            QMessageBox.information(self, "提示", "当前没有发帖任务")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除所有发帖任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.posting_tasks.clear()
            self.update_posting_tasks_list()
            self.save_config()
            self.add_log("所有发帖任务已删除", "info")

    def remove_comment_task_by_row(self, row):
        """根据行号删除评论任务"""
        if row < 0 or row >= len(self.discord_manager.comment_tasks):
            QMessageBox.warning(self, "错误", "无效的行号")
            return

        task = self.discord_manager.comment_tasks[row]
        task_id = task.id

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除评论任务 '{task_id}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 从DiscordManager中删除任务
            self.discord_manager.comment_tasks.remove(task)
            self.update_comment_tasks_list()
            self.save_config()
            self.add_log(f"评论任务已删除: {task_id}", "info")

    def clear_comment_tasks(self):
        """一键删除所有评论任务"""
        if not self.discord_manager.comment_tasks:
            QMessageBox.information(self, "提示", "当前没有评论任务")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除所有评论任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.comment_tasks.clear()
            self.update_comment_tasks_list()
            self.save_config()
            self.add_log("所有评论任务已删除", "info")

    def edit_posting_task_by_id(self, row):
        """根据表格行号编辑发帖任务（通过任务ID）"""
        # 从表格项中获取任务ID
        content_item = self.posting_tasks_table.item(row, 0)
        if not content_item:
            QMessageBox.warning(self, "错误", "无法获取任务信息")
            return

        task_id = content_item.data(Qt.ItemDataRole.UserRole)
        if not task_id:
            QMessageBox.warning(self, "错误", "无法获取任务ID")
            return

        # 找到对应的任务
        task = None
        for t in self.discord_manager.posting_tasks:
            if t.id == task_id:
                task = t
                break

        if not task:
            QMessageBox.warning(self, "错误", "未找到要编辑的任务")
            return

        dialog = PostingTaskDialog(self, task)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                data = dialog.get_data()
                # 更新任务数据
                channel_id = data['channel_id']
                if channel_id is None:
                    channel_id = self.discord_manager.default_posting_channel_id or task.channel_id
                    if channel_id is None:
                        QMessageBox.warning(self, "错误", "请输入频道ID或先设置默认频道")
                        return
                task.channel_id = channel_id
                task.title = data['title']
                task.content = data['content']
                task.image_path = data['image_path']
                task.tags = data.get('tags') or []
                task.delay_seconds = 0  # 保持为0，使用全局间隔
                task.sent_count = 0
                task.next_run_at = None

                # 更新UI
                self.update_posting_tasks_list()
                self.save_config()
                self.add_log(f"发帖任务已更新: {task.id}", "info")
                QMessageBox.information(self, "成功", "发帖任务已更新")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"更新任务失败: {str(e)}")

    def edit_comment_task_by_id(self, row):
        """根据表格行号编辑评论任务（通过任务ID）"""
        # 从表格项中获取任务ID
        content_item = self.comment_tasks_table.item(row, 0)
        if not content_item:
            QMessageBox.warning(self, "错误", "无法获取任务信息")
            return

        task_id = content_item.data(Qt.ItemDataRole.UserRole)
        if not task_id:
            QMessageBox.warning(self, "错误", "无法获取任务ID")
            return

        # 找到对应的任务
        task = None
        for t in self.discord_manager.comment_tasks:
            if t.id == task_id:
                task = t
                break

        if not task:
            QMessageBox.warning(self, "错误", "未找到要编辑的任务")
            return

        dialog = CommentTaskDialog(self, task)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                data = dialog.get_data()
                # 更新任务数据
                task.message_link = data['message_link']
                task.content = data['content']
                task.image_path = data['image_path']
                task.delay_seconds = 0  # 保持为0，使用全局间隔
                task.sent_count = 0
                task.next_run_at = None

                # 更新UI
                self.update_comment_tasks_list()
                self.save_config()
                self.add_log(f"评论任务已更新: {task.id}", "info")
                QMessageBox.information(self, "成功", "评论任务已更新")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"更新任务失败: {str(e)}")

    def update_posting_tasks_list(self):
        """更新发帖任务列表"""
        self.posting_tasks_table.setRowCount(len(self.discord_manager.posting_tasks))
        for row, task in enumerate(self.discord_manager.posting_tasks):
            title_text = task.title or "无标题"
            title_item = QTableWidgetItem(title_text)
            title_item.setData(Qt.ItemDataRole.UserRole, task.id)  # 存储任务ID
            self.posting_tasks_table.setItem(row, 0, title_item)

            content_preview = task.content[:50] + "..." if len(task.content) > 50 else task.content
            content_item = QTableWidgetItem(content_preview)
            self.posting_tasks_table.setItem(row, 1, content_item)

            self.posting_tasks_table.setItem(row, 2, QTableWidgetItem(str(task.channel_id)))
            self.posting_tasks_table.setItem(row, 3, QTableWidgetItem(task.image_path or "无"))

            status_text = "激活" if task.is_active else "禁用"
            if task.is_active:
                if not self.discord_manager.posting_repeat_enabled and getattr(task, "sent_count", 0) > 0:
                    status_text = "已发送"
                elif task.next_run_at is not None:
                    remaining = max(0, int(task.next_run_at - time.time()))
                    status_text = f"激活 | 倒计时: {remaining}秒" if remaining > 0 else "激活 | 待发送"
                else:
                    status_text = "激活 | 待发送"
            self.posting_tasks_table.setItem(row, 4, QTableWidgetItem(status_text))

            # 创建操作按钮
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(2)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(50, 25)
            edit_btn.clicked.connect(lambda checked, r=row: self.edit_posting_task_by_id(r))

            delete_btn = QPushButton("删除")
            delete_btn.setFixedSize(50, 25)
            delete_btn.clicked.connect(lambda checked, r=row: self.remove_posting_task_by_id(r))

            action_layout.addWidget(edit_btn)
            action_layout.addWidget(delete_btn)
            action_layout.addStretch()

            self.posting_tasks_table.setCellWidget(row, 5, action_widget)

    # ============ 评论功能 ============

    def on_comment_enabled_changed(self, state):
        """评论启用状态改变（向后兼容）"""
        enabled = state == Qt.CheckState.Checked
        self.comment_toggle_button.setChecked(enabled)
        self.toggle_auto_comment()

    def add_comment_task(self):
        """添加评论任务"""
        dialog = CommentTaskDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            task_id = self.discord_manager.add_comment_task(
                data['content'],
                data['message_link'],
                data['image_path'],
                0  # 使用全局评论间隔，不再有单独延时
            )
            self.update_comment_tasks_list()
            self.save_config()
            self.add_log(f"评论任务已添加: {task_id}", "info")

    def remove_comment_task(self):
        """删除评论任务"""
        current_row = self.comment_tasks_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "警告", "请先选择要删除的任务")
            return

        # 获取选中行的任务ID
        content_item = self.comment_tasks_table.item(current_row, 0)
        if not content_item:
            QMessageBox.warning(self, "错误", "无法获取任务信息")
            return

        task_id = content_item.data(Qt.ItemDataRole.UserRole)
        if not task_id:
            QMessageBox.warning(self, "错误", "无法获取任务ID")
            return

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除评论任务 '{task_id}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 从DiscordManager中删除任务
            task_to_remove = None
            for task in self.discord_manager.comment_tasks:
                if task.id == task_id:
                    task_to_remove = task
                    break

            if task_to_remove:
                self.discord_manager.comment_tasks.remove(task_to_remove)
                self.update_comment_tasks_list()
                self.save_config()
                self.add_log(f"评论任务已删除: {task_id}", "info")
                QMessageBox.information(self, "成功", "评论任务已删除")
            else:
                QMessageBox.warning(self, "错误", "未找到要删除的任务")

    def on_posting_interval_changed(self, value=None):
        """发帖间隔改变"""
        if value is None:
            value = self.posting_interval_spin.value()
        self.discord_manager.posting_interval = value
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def on_posting_cycle_interval_changed(self, value=None):
        """发帖循环轮次间隔改变"""
        if value is None:
            value = self.posting_cycle_interval_spin.value()
        self.discord_manager.posting_cycle_interval = value
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def on_posting_start_delay_changed(self, value=None):
        """发帖启动倒计时改变"""
        if value is None:
            value = self.posting_start_delay_spin.value()
        self.discord_manager.posting_start_delay = value
        self.save_config()

    def on_posting_repeat_enabled_changed(self, state):
        """发帖循环发送开关"""
        enabled = state == Qt.CheckState.Checked
        self.discord_manager.posting_repeat_enabled = enabled
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()
        if enabled:
            self.add_log("发帖任务将循环发送", "info")
        else:
            self.add_log("发帖任务将仅执行一次", "info")

    def on_default_posting_channel_changed(self):
        """默认发帖频道改变"""
        value = self.posting_default_channel_input.text().strip()
        if not value:
            self.discord_manager.default_posting_channel_id = None
            self.save_config()
            return

        try:
            channel_id = int(value)
        except ValueError:
            QMessageBox.warning(self, "错误", "默认频道ID格式无效，请输入数字")
            if self.discord_manager.default_posting_channel_id:
                self.posting_default_channel_input.setText(str(self.discord_manager.default_posting_channel_id))
            else:
                self.posting_default_channel_input.clear()
            return

        self.discord_manager.default_posting_channel_id = channel_id
        self.save_config()

    def on_default_posting_tags_changed(self):
        """默认发帖标签改变"""
        value = self.posting_default_tags_input.text().strip()
        if not value:
            self.discord_manager.default_posting_tags = []
            self.save_config()
            return

        separators = [';', ',', '\n']
        tags = None
        for sep in separators:
            if sep in value:
                tags = [t.strip() for t in value.split(sep) if t.strip()]
                break
        if tags is None:
            tags = [value]

        self.discord_manager.default_posting_tags = tags
        self.save_config()

    def on_comment_interval_changed(self, value=None):
        """评论间隔改变"""
        if value is None:
            value = self.comment_interval_spin.value()
        self.discord_manager.comment_interval = value
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def on_comment_cycle_interval_changed(self, value=None):
        """评论循环轮次间隔改变"""
        if value is None:
            value = self.comment_cycle_interval_spin.value()
        self.discord_manager.comment_cycle_interval = value
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def on_comment_start_delay_changed(self, value=None):
        """评论启动倒计时改变"""
        if value is None:
            value = self.comment_start_delay_spin.value()
        self.discord_manager.comment_start_delay = value
        self.save_config()

    def on_reply_start_delay_changed(self, value=None):
        """自动回复启动倒计时改变"""
        if value is None:
            value = self.reply_start_delay_spin.value()
        self.discord_manager.reply_start_delay = value
        self.save_config()

    def on_comment_repeat_enabled_changed(self, state):
        """循环评论任务开关"""
        enabled = state == Qt.CheckState.Checked
        self.discord_manager.comment_repeat_enabled = enabled
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()
        if enabled:
            self.add_log("评论任务将循环发送", "info")
        else:
            self.add_log("评论任务将仅执行一次", "info")

    def on_comment_link_interval_changed(self, value=None):
        """评论多链接间隔改变"""
        if value is None:
            value = self.comment_link_interval_spin.value()
        self.discord_manager.comment_link_interval = value
        self.refresh_runtime_contexts_from_workspaces()
        self.save_config()

    def update_comment_tasks_list(self):
        """更新评论任务列表"""
        self.comment_tasks_table.setRowCount(len(self.discord_manager.comment_tasks))
        for row, task in enumerate(self.discord_manager.comment_tasks):
            content_item = QTableWidgetItem(task.content[:50] + "..." if len(task.content) > 50 else task.content)
            content_item.setData(Qt.ItemDataRole.UserRole, task.id)  # 存储任务ID
            self.comment_tasks_table.setItem(row, 0, content_item)
            self.comment_tasks_table.setItem(row, 1, QTableWidgetItem(task.message_link))
            self.comment_tasks_table.setItem(row, 2, QTableWidgetItem(task.image_path or "无"))
            status_text = "激活" if task.is_active else "禁用"
            if task.is_active:
                if not self.discord_manager.comment_repeat_enabled and getattr(task, "sent_count", 0) > 0:
                    status_text = "已发送"
                elif task.next_run_at is not None:
                    remaining = max(0, int(task.next_run_at - time.time()))
                    status_text = f"激活 | 倒计时: {remaining}秒" if remaining > 0 else "激活 | 待发送"
                else:
                    status_text = "激活 | 待发送"
            self.comment_tasks_table.setItem(row, 3, QTableWidgetItem(status_text))

            # 创建操作按钮
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(2)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(50, 25)
            edit_btn.clicked.connect(lambda checked, r=row: self.edit_comment_task_by_id(r))

            delete_btn = QPushButton("删除")
            delete_btn.setFixedSize(50, 25)
            delete_btn.clicked.connect(lambda checked, r=row: self.remove_comment_task_by_row(r))

            action_layout.addWidget(edit_btn)
            action_layout.addWidget(delete_btn)
            action_layout.addStretch()

            self.comment_tasks_table.setCellWidget(row, 4, action_widget)


class PostingTaskDialog(QDialog):
    """发帖任务对话框"""

    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("编辑发帖任务" if task else "添加发帖任务")
        self.setModal(True)
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        # 频道ID
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("频道ID:"))
        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("输入Discord频道ID")
        if not task and hasattr(parent, 'discord_manager') and parent.discord_manager.default_posting_channel_id:
            self.channel_input.setText(str(parent.discord_manager.default_posting_channel_id))
        channel_layout.addWidget(self.channel_input)
        layout.addLayout(channel_layout)

        # 帖子标题
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("帖子标题 (可选):"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("输入帖子标题...")
        title_layout.addWidget(self.title_input)
        layout.addLayout(title_layout)

        # 发帖内容
        content_layout = QVBoxLayout()
        content_layout.addWidget(QLabel("发帖内容:"))
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("输入要发帖的内容...")
        content_layout.addWidget(self.content_input)
        layout.addLayout(content_layout)

        # 图片路径（支持多选）
        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("图片 (可选):"))
        self.image_input = QLineEdit()
        self.image_input.setPlaceholderText("选择图片文件路径（多个用分号或逗号分隔）...")
        image_layout.addWidget(self.image_input)

        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self.browse_image)
        image_layout.addWidget(browse_button)

        clear_button = QPushButton("清空")
        clear_button.clicked.connect(lambda: self.image_input.clear())
        image_layout.addWidget(clear_button)

        layout.addLayout(image_layout)

        # 论坛标签
        tags_layout = QHBoxLayout()
        tags_layout.addWidget(QLabel("标签 (可选):"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("留空使用默认标签；多个用逗号或分号分隔")
        tags_layout.addWidget(self.tags_input)
        layout.addLayout(tags_layout)

        # 注意：延时设置已移除，使用全局发帖间隔

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        buttons_layout.addWidget(ok_btn)

        layout.addLayout(buttons_layout)

    def browse_image(self):
        """浏览选择图片文件（支持多选）"""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)  # 改为多选模式

        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                # 将多个文件路径用分号连接
                current_text = self.image_input.text().strip()
                new_files = ";".join(selected_files)

                if current_text:
                    # 如果已有内容，追加到后面
                    combined = current_text + ";" + new_files
                    # 去重
                    files_list = list(set(combined.split(";")))
                    self.image_input.setText(";".join(files_list))
                else:
                    self.image_input.setText(new_files)

    def get_data(self):
        """获取对话框数据"""
        channel_text = self.channel_input.text().strip()
        channel_id = int(channel_text) if channel_text else None
        tags_text = self.tags_input.text().strip()
        tags = []
        if tags_text:
            separators = [';', ',', '\n']
            for sep in separators:
                if sep in tags_text:
                    tags = [t.strip() for t in tags_text.split(sep) if t.strip()]
                    break
            else:
                tags = [tags_text]
        return {
            'channel_id': channel_id,
            'title': self.title_input.text().strip() or None,
            'content': self.content_input.toPlainText().strip(),
            'image_path': self.image_input.text().strip() or None,
            'delay_seconds': 0,  # 使用全局发帖间隔，不再有单独延时
            'tags': tags
        }

    def showEvent(self, event):
        """对话框显示事件"""
        super().showEvent(event)
        # 在对话框显示时加载任务数据
        self.load_task_data()

    def load_task_data(self):
        """加载任务数据到对话框（用于编辑）"""
        if self.task:
            self.channel_input.setText(str(self.task.channel_id))
            if hasattr(self, 'title_input'):
                self.title_input.setText(self.task.title or "")
            if hasattr(self, 'content_input'):
                self.content_input.setPlainText(self.task.content)
            if hasattr(self, 'image_input'):
                self.image_input.setText(self.task.image_path or "")
            if hasattr(self, 'tags_input'):
                self.tags_input.setText(", ".join(self.task.tags or []))
            # 不再设置delay_spin，因为已移除


class CommentTaskDialog(QDialog):
    """评论任务对话框"""

    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("编辑评论任务" if task else "添加评论任务")
        self.setModal(True)
        self.resize(500, 450)

        layout = QVBoxLayout(self)

        link_layout = QVBoxLayout()
        link_label = QLabel("消息ID或链接（支持多个，每行一个或用分号分隔）:")
        link_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        link_layout.addWidget(link_label)

        self.link_input = QTextEdit()
        self.link_input.setMaximumHeight(100)
        self.link_input.setPlaceholderText(
            "示例（每行一个）：\n"
            "1234567890\n"
            "https://discord.com/channels/123/456/789\n"
            "\n"
            "或用分号分隔：\n"
            "1234567890;9876543210"
        )
        link_layout.addWidget(self.link_input)
        layout.addLayout(link_layout)

        # 评论内容
        content_layout = QVBoxLayout()
        content_layout.addWidget(QLabel("评论内容:"))
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("输入要评论的内容...")
        content_layout.addWidget(self.content_input)
        layout.addLayout(content_layout)

        # 图片路径
        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("图片 (可选):"))
        self.image_input = QLineEdit()
        self.image_input.setPlaceholderText("选择图片文件路径...")
        image_layout.addWidget(self.image_input)

        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self.browse_image)
        image_layout.addWidget(browse_button)
        layout.addLayout(image_layout)

        # 注意：延时设置已移除，使用全局评论间隔

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        buttons_layout.addWidget(ok_btn)

        layout.addLayout(buttons_layout)

    def browse_image(self):
        """浏览选择图片文件（支持多选）"""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)  # 改为多选模式

        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                # 将多个文件路径用分号连接
                current_text = self.image_input.text().strip()
                new_files = ";".join(selected_files)

                if current_text:
                    # 如果已有内容，追加到后面
                    combined = current_text + ";" + new_files
                    # 去重
                    files_list = list(set(combined.split(";")))
                    self.image_input.setText(";".join(files_list))
                else:
                    self.image_input.setText(new_files)

    def get_data(self):
        return {
            'message_link': self.link_input.toPlainText().strip(),
            'content': self.content_input.toPlainText().strip(),
            'image_path': self.image_input.text().strip() or None,
            'delay_seconds': 0
        }

        self.load_task_data()

    def showEvent(self, event):
        super().showEvent(event)
        self.load_task_data()

    def load_task_data(self):
        if self.task:
            if hasattr(self, 'link_input'):
                self.link_input.setPlainText(self.task.message_link)
            if hasattr(self, 'content_input'):
                self.content_input.setPlainText(self.task.content)
            if hasattr(self, 'image_input'):
                self.image_input.setText(self.task.image_path or "")



def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用更现代的样式

    red_pixmap = QPixmap(256, 256)
    red_pixmap.fill(QColor(255, 0, 0))
    app.setWindowIcon(QIcon(red_pixmap))

    # 设置应用程序属性，确保在macOS上正确显示
    app.setApplicationName("Discord Auto Reply")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DiscordAutoReply")

    # 修复macOS上的NSOpenPanel警告和视觉问题
    import platform
    if platform.system() == 'Darwin':  # macOS
        # 禁用原生文件对话框以避免NSOpenPanel警告
        app.setAttribute(Qt.AA_DontUseNativeDialogs, True)

    window = MainWindow()
    window.show()
    window.raise_()  # 确保窗口在前台显示
    window.activateWindow()  # 激活窗口

    # 创建定时器定期更新状态
    timer = QTimer()
    timer.timeout.connect(window.update_status)
    timer.start(5000)  # 每5秒更新一次

    countdown_timer = QTimer()
    countdown_timer.timeout.connect(window.refresh_task_countdowns)
    countdown_timer.start(1000)  # 每秒刷新倒计时

    # 运行Qt应用程序事件循环，不使用 asyncio.run()
    # PySide6 的事件循环会接管主线程
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
