#!/usr/bin/env python3
"""
修复许可证配置脚本
确保配置文件包含正确的管理员认证信息
"""

import json
import os

def fix_config():
    """修复许可证配置"""
    config_file = "config/config.json"

    if not os.path.exists(config_file):
        print("❌ 配置文件不存在")
        return False

    try:
        # 读取当前配置
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 修复许可证配置
        if "license" not in config:
            config["license"] = {}

        license_config = config["license"]

        # 设置默认值（如果不存在）
        license_config["username"] = license_config.get("username", "client")
        license_config["password"] = license_config.get("password", "qq1383766")
        license_config["admin_username"] = license_config.get("admin_username", "admin")
        license_config["admin_password"] = license_config.get("admin_password", "qq1383766")
        license_config["server_url"] = license_config.get("server_url", "https://license.thy1cc.top")
        license_config["api_path"] = license_config.get("api_path", "/api/v1")

        # 保存修复后的配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print("✅ 许可证配置已修复!")
        print(f"客户端认证: {license_config['username']}")
        print(f"管理员认证: {license_config['admin_username']}")
        print(f"服务器URL: {license_config['server_url']}")

        return True

    except Exception as e:
        print(f"❌ 修复失败: {e}")
        return False

if __name__ == "__main__":
    fix_config()
