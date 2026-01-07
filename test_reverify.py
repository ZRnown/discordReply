#!/usr/bin/env python3
"""
测试重新验证许可证功能
"""
import asyncio
import sys
import os

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from config_manager import ConfigManager
    from discord_client import LicenseManager
except ImportError:
    # 如果相对导入失败，直接导入
    import config_manager
    import discord_client
    ConfigManager = config_manager.ConfigManager
    LicenseManager = discord_client.LicenseManager

async def test_reverify_license():
    """测试重新验证许可证功能"""
    print("🔄 测试重新验证许可证功能")
    print("=" * 50)

    # 初始化配置管理器和许可证管理器
    config_manager = ConfigManager()
    license_manager = LicenseManager()

    # 加载配置
    accounts, rules, license_config = config_manager.load_config()
    license_manager.client_username = license_config.get("client_username", "client")
    license_manager.client_password = license_config.get("client_password", "qq1383766")
    license_manager.admin_username = license_config.get("admin_username", "admin")
    license_manager.admin_password = license_config.get("admin_password", "qq1383766")
    license_manager.license_server_url = license_config.get("server_url", "https://license.thy1cc.top")
    license_manager.api_path = license_config.get("api_path", "/api/v1")

    # 获取当前保存的许可证密钥
    license_key = license_config.get("license_key", "").strip()

    if not license_key:
        print("❌ 没有找到保存的许可证密钥")
        return

    print(f"当前保存的许可证密钥: {license_key}")

    try:
        # 重新验证许可证
        print("正在验证许可证...")
        success, message = await license_manager.validate_license(license_key)

        if success:
            print(f"✅ 许可证验证成功: {message}")
        else:
            print(f"❌ 许可证验证失败: {message}")

    except Exception as e:
        print(f"❌ 验证过程中发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_reverify_license())
