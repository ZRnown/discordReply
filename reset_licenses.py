#!/usr/bin/env python3
"""
重置许可证状态脚本
将所有许可证的machine-node重置为NOT_ACTIVATED状态
"""

import sys
import os
import requests
import json

def reset_license(server_url, username, password, license_key):
    """重置单个许可证状态"""
    url = f"{server_url}/api/v1/update"

    payload = {
        "_id": license_key,
        "machine-node": "NOT_ACTIVATED",
        "machine-sn": 0
    }

    try:
        response = requests.patch(url, json=payload, auth=(username, password))

        if response.status_code == 200:
            return True, "重置成功"
        elif response.status_code == 404:
            return False, "许可证不存在"
        else:
            return False, f"重置失败: HTTP {response.status_code}"

    except requests.exceptions.RequestException as e:
        return False, f"网络错误: {e}"

def reset_all_licenses(server_url, username, password):
    """重置所有许可证状态"""
    print(f"重置服务器 {server_url} 上的所有许可证...")
    print("=" * 60)

    # 首先获取所有许可证
    list_url = f"{server_url}/api/v1/get-all"
    try:
        response = requests.get(list_url, auth=(username, password))
        if response.status_code != 200:
            print(f"❌ 获取许可证列表失败: HTTP {response.status_code}")
            return

        data = response.json()
        licenses = data.get('license-database', [])

        print(f"找到 {len(licenses)} 个许可证")

        reset_count = 0
        for license_info in licenses:
            license_id = license_info.get('_id')
            machine_node = license_info.get('machine-node')

            # 只重置非NOT_ACTIVATED状态的许可证
            if machine_node != "NOT_ACTIVATED":
                print(f"重置许可证: {license_id} (当前状态: {machine_node})")
                success, message = reset_license(server_url, username, password, license_id)
                if success:
                    print(f"  ✅ {message}")
                    reset_count += 1
                else:
                    print(f"  ❌ {message}")
            else:
                print(f"跳过许可证: {license_id} (已经是NOT_ACTIVATED状态)")

        print("\n" + "=" * 60)
        print(f"📊 重置完成! 成功重置 {reset_count} 个许可证")

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")

def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("许可证重置工具")
        print("=" * 30)
        print("用法:")
        print("  python reset_licenses.py <服务器URL> <管理员用户名> <管理员密码>")
        print()
        print("功能:")
        print("  将所有许可证的machine-node重置为NOT_ACTIVATED状态")
        print("  这样可以让许可证重新分配给其他用户")
        print()
        print("示例:")
        print("  python reset_licenses.py https://license.thy1cc.top admin qq1383766")
        print()
        print("⚠️  警告: 此操作会重置所有许可证的状态，用户需要重新激活!")
        sys.exit(1)

    server_url = sys.argv[1].rstrip('/')
    username = sys.argv[2]
    password = sys.argv[3]

    # 确认操作
    print("⚠️  此操作将重置所有许可证的状态!")
    print("   用户将需要重新激活他们的许可证。")
    print()
    confirmation = input("确认继续吗？输入 'yes' 继续: ").strip().lower()
    if confirmation != 'yes':
        print("❌ 操作已取消")
        sys.exit(0)

    # 执行重置
    reset_all_licenses(server_url, username, password)

if __name__ == "__main__":
    main()
