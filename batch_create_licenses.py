#!/usr/bin/env python3
"""
批量创建许可证脚本
用于批量创建多个许可证
"""

import sys
import os
import requests
import json
import uuid
import random
from datetime import datetime, timedelta

def create_license(server_url, username, password, license_data):
    """创建单个许可证"""
    url = f"{server_url}/api/v1/create"
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, json=license_data, headers=headers, auth=(username, password))

        if response.status_code == 200:
            result = response.json()
            return True, result.get('_id', 'Unknown'), None
        elif response.status_code == 404:
            return False, None, "Missing required fields"
        elif response.status_code == 406:
            return False, None, "Requires JSON payload"
        else:
            return False, None, f"HTTP {response.status_code}: {response.text}"

    except requests.exceptions.RequestException as e:
        return False, None, f"Network error: {e}"

def batch_create_licenses(server_url, username, password, count=10, prefix="AUTO"):
    """批量创建许可证"""
    print(f"🔄 批量创建 {count} 个许可证...")
    print(f"服务器: {server_url}")
    print(f"用户名: {username}")
    print("=" * 60)

    created_licenses = []

    for i in range(count):
        # 生成唯一许可证ID
        license_id = uuid.uuid4().hex[:32]

        # 生成完全唯一的随机数据
        timestamp = int(datetime.now().timestamp() * 1000000)  # 微秒级时间戳
        random_part = random.randint(1000, 9999) + i * 10000  # 确保每个许可证都不相同

        machine_sn = timestamp + random_part  # 确保唯一的序列号
        unique_suffix = f"{timestamp}_{random_part}_{i}"

        # 构建许可证数据 - 使用完全唯一的数据
        license_data = {
            "name": f"{prefix} 用户 {i+1:03d} {unique_suffix}",
            "email": f"user{i+1:03d}_{unique_suffix}@example.com",
            "company": f"批量创建用户 {unique_suffix}",
            "product": "Discord Auto Reply Tool",
            "length": 365,  # 365天
            "machine-node": "NOT_ACTIVATED",
            "machine-sn": machine_sn
        }

        print(f"📝 创建许可证 {i+1}/{count}: {license_id}")

        success, created_id, error = create_license(server_url, username, password, license_data)

        if success:
            print(f"  ✅ 成功: {created_id}")
            created_licenses.append(created_id)
        else:
            print(f"  ❌ 失败: {error}")

    print("\n" + "=" * 60)
    print(f"📊 批量创建完成!")
    print(f"✅ 成功: {len(created_licenses)} 个")
    print(f"❌ 失败: {count - len(created_licenses)} 个")

    if created_licenses:
        print("\n📋 创建的许可证ID:")
        for i, license_id in enumerate(created_licenses, 1):
            print(f"  {i:2d}. {license_id}")

        # 保存到文件
        filename = f"licenses_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# 批量创建的许可证\n")
            f.write(f"# 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总数: {len(created_licenses)}\n")
            f.write("# 格式: 许可证ID\n")
            f.write("#\n")
            for license_id in created_licenses:
                f.write(f"{license_id}\n")

        print(f"\n💾 许可证ID已保存到文件: {filename}")

    return created_licenses

def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("批量创建许可证工具")
        print("=" * 40)
        print("用法:")
        print("  python batch_create_licenses.py <服务器URL> <用户名> <密码> [数量] [前缀]")
        print()
        print("参数:")
        print("  服务器URL: License Mate服务器地址")
        print("  用户名: 管理员用户名")
        print("  密码: 管理员密码")
        print("  数量: 创建的许可证数量（默认10）")
        print("  前缀: 用户名前缀（默认AUTO）")
        print()
        print("示例:")
        print("  python batch_create_licenses.py https://license.thy1cc.top admin password")
        print("  python batch_create_licenses.py https://license.thy1cc.top admin password 50 VIP")
        sys.exit(1)

    server_url = sys.argv[1].rstrip('/')
    username = sys.argv[2]
    password = sys.argv[3]
    count = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    prefix = sys.argv[5] if len(sys.argv) > 5 else "AUTO"

    if count <= 0 or count > 1000:
        print("❌ 数量必须在1-1000之间")
        sys.exit(1)

    # 确认操作
    print(f"⚠️  将要创建 {count} 个许可证，确认吗？(输入 'yes' 继续)")
    confirmation = input().strip().lower()
    if confirmation != 'yes':
        print("❌ 操作已取消")
        sys.exit(0)

    # 批量创建
    batch_create_licenses(server_url, username, password, count, prefix)

if __name__ == "__main__":
    main()
