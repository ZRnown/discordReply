#!/usr/bin/env python3
"""
测试许可证配置脚本
检查当前配置的许可证认证信息
"""

import sys
import os

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gui import MainWindow

def test_config():
    """测试许可证配置"""
    print("🔧 测试许可证配置...")
    print("=" * 50)

    # 创建主窗口实例（不会显示GUI）
    app = MainWindow.__new__(MainWindow)
    app.config_manager = type('MockConfig', (), {
        'load_config': lambda: ([], [], {
            "username": "client",
            "password": "qq1383766",
            "admin_username": "admin",
            "admin_password": "qq1383766",
            "license_key": "",
            "server_url": "https://license.thy1cc.top",
            "api_path": "/api/v1"
        }, {}, [], [])
    })()

    # 手动初始化许可证管理器
    from discord_client import DiscordManager
    app.discord_manager = DiscordManager()

    # 模拟加载配置
    try:
        accounts, rules, license_config, rotation_config, posting_tasks, comment_tasks = app.config_manager.load_config()

        print(f"客户端用户名: {license_config.get('username', '未设置')}")
        print(f"客户端密码: {'*' * len(license_config.get('password', '')) if license_config.get('password') else '未设置'}")
        print(f"管理员用户名: {license_config.get('admin_username', '未设置')}")
        print(f"管理员密码: {'*' * len(license_config.get('admin_password', '')) if license_config.get('admin_password') else '未设置'}")
        print(f"服务器URL: {license_config.get('server_url', '未设置')}")
        print(f"API路径: {license_config.get('api_path', '未设置')}")

        # 配置许可证管理器
        username = license_config.get("username", "client")
        password = license_config.get("password", "qq1383766")
        admin_username = license_config.get("admin_username")
        admin_password = license_config.get("admin_password")
        api_path = license_config.get("api_path", "/api/v1")
        server_url = license_config.get("server_url", "https://license.thy1cc.top")

        app.discord_manager.configure_license_auth(username, password, api_path)
        app.discord_manager.license_manager.license_server_url = server_url
        app.discord_manager.license_manager.admin_username = admin_username
        app.discord_manager.license_manager.admin_password = admin_password

        print("\n✅ 配置检查完成!")
        print(f"许可证管理器 - 客户端认证: {app.discord_manager.license_client_username}")
        print(f"许可证管理器 - 管理员认证: {getattr(app.discord_manager.license_manager, 'admin_username', '未设置')}")

        if admin_username and admin_password:
            print("✅ 管理员认证信息已配置")
        else:
            print("❌ 管理员认证信息未配置 - 这会导致激活失败!")

    except Exception as e:
        print(f"❌ 配置测试失败: {e}")

if __name__ == "__main__":
    test_config()
