#!/usr/bin/env python3
"""
测试许可证激活脚本
"""

import sys
import os
import asyncio

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from discord_client import LicenseManager

async def test_activation(license_key):
    """测试许可证激活"""
    print(f"🔄 测试激活许可证: {license_key}")
    print("=" * 50)

    # 创建许可证管理器，使用默认配置
    license_manager = LicenseManager(
        license_server_url="https://license.thy1cc.top",
        client_username="client",
        client_password="qq1383766",
        admin_username="admin",  # 关键：设置管理员认证
        admin_password="qq1383766",
        api_path="/api/v1"
    )

    print("配置信息:")
    print(f"  服务器: {license_manager.license_server_url}")
    print(f"  客户端认证: {license_manager.client_username}")
    print(f"  管理员认证: {license_manager.admin_username}")

    try:
        # 首先验证许可证
        print("\n1. 验证许可证...")
        is_valid, message = await license_manager.validate_license(license_key)
        print(f"验证结果: {'✅' if is_valid else '❌'} {message}")

        if is_valid and "未激活" in message:
            print("\n2. 激活许可证...")
            success, activate_message = await license_manager.activate_license(license_key)
            print(f"激活结果: {'✅' if success else '❌'} {activate_message}")

            if success:
                print("\n3. 重新验证...")
                is_valid_after, message_after = await license_manager.validate_license(license_key)
                print(f"最终状态: {'✅' if is_valid_after else '❌'} {message_after}")
        elif is_valid and "已激活" in message:
            print("\n✅ 许可证已经激活")
        else:
            print(f"\n❌ 许可证无效: {message}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python test_activation.py <许可证密钥>")
        print("示例: python test_activation.py a95bc441387835d33b564c6af7cc69bd")
        sys.exit(1)

    license_key = sys.argv[1].strip()

    if not license_key:
        print("❌ 许可证密钥不能为空")
        sys.exit(1)

    # 运行异步测试
    asyncio.run(test_activation(license_key))

if __name__ == "__main__":
    main()
