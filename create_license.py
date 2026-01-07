#!/usr/bin/env python3
"""
创建许可证脚本
用于在License Mate服务器上创建新许可证
"""

import sys
import os
import requests
import json
from datetime import datetime, timedelta

def create_license(server_url, username, password, license_data):
    """创建许可证"""
    url = f"{server_url}/api/v1/create"
    headers = {'Content-Type': 'application/json'}

    try:
        # 发送请求
        response = requests.post(url, json=license_data, headers=headers, auth=(username, password))

        print(f"请求URL: {url}")
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("✅ 许可证创建成功!")
            print(f"许可证ID: {result.get('_id', '未知')}")
            return result
        elif response.status_code == 404:
            print("❌ 创建失败：缺少必需字段")
            print("必需字段:", response.text)
        elif response.status_code == 406:
            print("❌ 创建失败：需要JSON payload")
        else:
            print(f"❌ 创建失败: HTTP {response.status_code}")
            print("响应:", response.text)

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")

    return None

def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("用法:")
        print("  python create_license.py <服务器URL> <用户名> <密码> [许可证密钥]")
        print()
        print("示例:")
        print("  python create_license.py https://license.thy1cc.top admin password")
        print("  python create_license.py https://license.thy1cc.top admin password 09c4661532162b8ad4a4b04bbb1f80e2")
        print()
        print("如果不指定许可证密钥，将使用当前机器的指纹")
        sys.exit(1)

    server_url = sys.argv[1].rstrip('/')
    username = sys.argv[2]
    password = sys.argv[3]
    license_key = sys.argv[4] if len(sys.argv) > 4 else None

    # 如果没有指定许可证密钥，生成一个随机的唯一ID
    if not license_key:
        import uuid
        # 生成一个32字符的十六进制字符串（类似于你现有的许可证格式）
        license_key = uuid.uuid4().hex[:32]
        print(f"生成随机许可证ID: {license_key}")

    # 计算过期时间（从现在起1年）
    expiry_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')

    # 生成完全唯一的随机数据
    import random
    import time

    # 使用时间戳 + 随机数确保唯一性
    timestamp = int(time.time() * 1000000)  # 微秒级时间戳
    random_part = random.randint(1000, 9999)

    machine_sn = timestamp + random_part  # 确保唯一的序列号
    unique_suffix = f"{timestamp}_{random_part}"

    # 构建许可证数据 - 使用完全唯一的数据
    license_data = {
        "name": f"自动回复工具用户 {unique_suffix}",
        "email": f"user_{unique_suffix}@example.com",
        "company": f"个人用户 {unique_suffix}",
        "product": "Discord Auto Reply Tool",
        "length": 365,  # 365天
        "machine-node": "NOT_ACTIVATED",
        "machine-sn": machine_sn
    }

    print(f"🔧 创建许可证配置:")
    print(f"  服务器: {server_url}")
    print(f"  用户名: {username}")
    print(f"  许可证ID: {license_key}")
    print(f"  过期时间: {expiry_date}")
    print(f"  机器节点: {license_data['machine-node']}")
    print()

    # 创建许可证
    result = create_license(server_url, username, password, license_data)

    if result:
        print("\n🎉 许可证创建成功!")
        print("现在你可以在软件中激活这个许可证了")
        print(f"许可证ID: {result.get('_id', license_key)}")

if __name__ == "__main__":
    main()
