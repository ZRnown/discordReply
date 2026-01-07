#!/usr/bin/env python3
"""
许可证管理脚本
用于管理License Mate服务器上的许可证
"""

import sys
import os
import requests
import json
from datetime import datetime

def validate_license(server_url, username, password, license_key):
    """验证许可证"""
    url = f"{server_url}/api/v1/validate"
    params = {'_id': license_key}

    try:
        response = requests.get(url, params=params, auth=(username, password))

        print(f"验证许可证: {license_key}")
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("✅ 许可证有效")
            license_details = data.get('license-details', {})
            print(f"  名称: {license_details.get('name', '未知')}")
            print(f"  邮箱: {license_details.get('email', '未知')}")
            print(f"  公司: {license_details.get('company', '未知')}")
            print(f"  产品: {license_details.get('product', '未知')}")
            print(f"  创建时间: {license_details.get('created', '未知')}")
            print(f"  过期时间: {license_details.get('expiry', '未知')}")
            print(f"  机器节点: {license_details.get('machine-node', '未知')}")
            print(f"  续期次数: {license_details.get('renew_count', 0)}")
            return True, data
        elif response.status_code == 202:
            data = response.json()
            print("⚠️  许可证已过期")
            return False, data
        elif response.status_code == 404:
            print("❌ 许可证不存在")
            return False, None
        else:
            print(f"❌ 验证失败: HTTP {response.status_code}")
            return False, None

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
        return False, None

def update_license(server_url, username, password, license_key, updates):
    """更新许可证"""
    url = f"{server_url}/api/v1/update"

    payload = {"_id": license_key}
    payload.update(updates)

    try:
        response = requests.patch(url, json=payload, auth=(username, password))

        print(f"更新许可证: {license_key}")
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            print("✅ 许可证更新成功")
            return True
        elif response.status_code == 404:
            print("❌ 许可证不存在")
        else:
            print(f"❌ 更新失败: HTTP {response.status_code}")
            print(f"响应: {response.text}")

        return False

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
        return False


def activate_license(server_url, admin_username, admin_password, license_key):
    """激活许可证（设置机器节点）"""
    # 获取当前机器指纹
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    from discord_client import LicenseManager
    license_manager = LicenseManager()
    machine_fingerprint = license_manager.machine_fingerprint

    print(f"激活许可证: {license_key}")
    print(f"绑定到机器: {machine_fingerprint}")

    # 更新许可证，设置机器节点
    updates = {
        "machine-node": machine_fingerprint,
        "machine-sn": int(__import__('time').time())
    }

    return update_license(server_url, admin_username, admin_password, license_key, updates)

def get_all_licenses(server_url, username, password):
    """获取所有许可证"""
    url = f"{server_url}/api/v1/get-all"

    try:
        response = requests.get(url, auth=(username, password))

        print("获取所有许可证")
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            licenses = data.get('license-database', [])
            print(f"✅ 找到 {len(licenses)} 个许可证")

            for i, license_info in enumerate(licenses, 1):
                print(f"\n{i}. ID: {license_info.get('_id', '未知')}")
                print(f"   名称: {license_info.get('name', '未知')}")
                print(f"   邮箱: {license_info.get('email', '未知')}")
                print(f"   机器节点: {license_info.get('machine-node', 'NOT_ACTIVATED')}")
                print(f"   过期时间: {license_info.get('expiry', '未知')}")

            return licenses
        else:
            print(f"❌ 获取失败: HTTP {response.status_code}")

        return []

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
        return []

def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("许可证管理工具")
        print("=" * 50)
        print("用法:")
        print("  python manage_license.py <命令> <服务器URL> <用户名> <密码> [其他参数]")
        print()
        print("命令:")
        print("  validate <许可证ID>    - 验证许可证")
        print("  update <许可证ID> <字段> <值>  - 更新许可证字段")
        print("  activate <许可证ID>    - 激活许可证（绑定到当前机器）")
        print("  list                   - 列出所有许可证")
        print()
        print("示例:")
        print("  python manage_license.py validate https://license.thy1cc.top admin password 09c4661532162b8ad4a4b04bbb1f80e2")
        print("  python manage_license.py update https://license.thy1cc.top admin password 09c4661532162b8ad4a4b04bbb1f80e2 machine-node Greece-Laptop")
        print("  python manage_license.py list https://license.thy1cc.top admin password")
        sys.exit(1)

    command = sys.argv[1].lower()
    server_url = sys.argv[2].rstrip('/')
    username = sys.argv[3]
    password = sys.argv[4]

    if command == "validate":
        if len(sys.argv) < 6:
            print("❌ 验证命令需要许可证ID")
            sys.exit(1)
        license_key = sys.argv[5]
        validate_license(server_url, username, password, license_key)

    elif command == "update":
        if len(sys.argv) < 8:
            print("❌ 更新命令需要许可证ID、字段名和值")
            sys.exit(1)
        license_key = sys.argv[5]
        field = sys.argv[6]
        value = sys.argv[7]

        # 处理不同类型的字段
        if field in ["machine-sn", "renew_count"]:
            try:
                value = int(value)
            except ValueError:
                print(f"❌ 字段 {field} 必须是整数")
                sys.exit(1)

        updates = {field: value}
        update_license(server_url, username, password, license_key, updates)

    elif command == "list":
        get_all_licenses(server_url, username, password)

    elif command == "activate":
        if len(sys.argv) < 6:
            print("❌ activate命令需要许可证ID")
            sys.exit(1)
        license_key = sys.argv[5]
        activate_license(server_url, username, password, license_key)

    else:
        print(f"❌ 未知命令: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
