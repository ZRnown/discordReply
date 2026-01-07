#!/usr/bin/env python3
"""
测试GUI重新验证许可证功能
"""
import sys
import os

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer

class MockGUI:
    """模拟GUI来测试reverify_license方法"""

    def __init__(self):
        from config_manager import ConfigManager
        from discord_client import LicenseManager

        self.config_manager = ConfigManager()
        self.discord_manager = type('MockDiscordManager', (), {
            'license_manager': LicenseManager()
        })()

        # 加载配置
        accounts, rules, license_config = self.config_manager.load_config()
        self.discord_manager.license_manager.client_username = license_config.get("client_username", "client")
        self.discord_manager.license_manager.client_password = license_config.get("client_password", "qq1383766")
        self.discord_manager.license_manager.admin_username = license_config.get("admin_username", "admin")
        self.discord_manager.license_manager.admin_password = license_config.get("admin_password", "qq1383766")
        self.discord_manager.license_manager.license_server_url = license_config.get("server_url", "https://license.thy1cc.top")
        self.discord_manager.license_manager.api_path = license_config.get("api_path", "/api/v1")

    def add_log(self, message, level="info"):
        """模拟日志记录"""
        print(f"[{level.upper()}] {message}")

    def update_license_status(self):
        """模拟更新许可证状态"""
        print("更新许可证状态显示")

    def reverify_license(self):
        """重新验证当前已保存的许可证"""
        # 从配置中读取许可证密钥
        license_config = self.config_manager.load_config()[2]  # 获取许可证配置
        license_key = license_config.get("license_key", "").strip()

        if not license_key:
            # 没有配置许可证密钥，提示用户输入
            print("❌ 没有保存的许可证密钥")
            return

        try:
            # 重新验证当前许可证
            self.add_log("🔄 正在重新验证许可证...", "info")

            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, message = loop.run_until_complete(
                self.discord_manager.license_manager.validate_license(license_key)
            )
            loop.close()

            if success:
                self.add_log(f"✅ 许可证验证成功: {message}", "success")
                print(f"✅ 许可证验证成功: {message}")
            else:
                self.add_log(f"❌ 许可证验证失败: {message}", "error")
                print(f"❌ 许可证验证失败: {message}")

        except Exception as e:
            self.add_log(f"❌ 验证过程中发生错误: {e}", "error")
            print(f"❌ 验证过程中发生错误: {e}")

        # 更新许可证状态显示
        self.update_license_status()

def main():
    """主测试函数"""
    print("🔄 测试GUI重新验证许可证功能")
    print("=" * 50)

    app = QApplication(sys.argv)

    # 创建模拟GUI
    gui = MockGUI()

    # 测试重新验证功能
    gui.reverify_license()

    print("\n测试完成")

if __name__ == "__main__":
    main()
