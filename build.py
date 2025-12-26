#!/usr/bin/env python3
"""
Discord自动回复工具打包脚本
支持Mac和Windows平台打包
"""

import os
import sys
import platform
import subprocess
from pathlib import Path


def run_command(command, description):
    """运行命令并显示状态"""
    print(f"正在{description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description}成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description}失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False


def check_dependencies():
    """检查依赖"""
    print("检查依赖...")

    try:
        import PyInstaller
        print("✅ PyInstaller 已安装")
    except ImportError:
        print("❌ PyInstaller 未安装，请运行: pip install pyinstaller")
        return False

    try:
        import discord
        print("✅ discord.py-self 已安装")
    except ImportError:
        print("❌ discord.py-self 未安装，请运行: pip install discord.py-self")
        return False

    try:
        import PyQt6
        print("✅ PyQt6 已安装")
    except ImportError:
        print("❌ PyQt6 未安装，请运行: pip install PyQt6")
        return False

    # qasync不再需要，直接使用asyncio集成

    return True


def clean_build():
    """清理构建文件"""
    print("清理构建文件...")

    dirs_to_clean = ["build", "dist"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            import shutil
            shutil.rmtree(dir_name)
            print(f"✅ 删除 {dir_name} 目录")

    # 清理spec文件生成的缓存
    spec_files = ["DiscordAutoReply.spec"]
    for spec_file in spec_files:
        if os.path.exists(spec_file):
            os.remove(spec_file)
            print(f"✅ 删除 {spec_file}")


def build_app(target_platform="auto"):
    """构建应用程序"""
    if target_platform == "auto":
        system = platform.system().lower()
    else:
        system = target_platform.lower()

    print(f"目标平台: {system}")

    # 基础PyInstaller命令
    cmd = [
        "pyinstaller",
        "--onefile",  # 打包成单个文件
        "--windowed",  # 无控制台窗口
        "--clean",  # 清理临时文件
        "--name", "DiscordAutoReply",
    ]

    # 根据平台添加特定选项
    if system == "darwin" or system == "mac":  # macOS
        cmd.extend([
            "--target-arch", "universal2",  # 通用二进制
            "--osx-bundle-identifier", "com.discordautoreply.app",
        ])
        print("使用macOS打包配置")
    elif system == "windows" or system == "win":  # Windows
        cmd.extend([
            "--win-private-assemblies",  # Windows特定选项
        ])
        print("使用Windows打包配置")
    else:
        print(f"不支持的平台: {system}")
        return False

    # 添加数据文件
    if os.path.exists("config"):
        if system == "windows":
            cmd.extend(["--add-data", "config;config"])
        else:  # macOS and others
            cmd.extend(["--add-data", "config:config"])

    if os.path.exists("assets"):
        if system == "windows":
            cmd.extend(["--add-data", "assets;assets"])
        else:  # macOS and others
            cmd.extend(["--add-data", "assets:assets"])

    # 添加主文件
    cmd.append("src/main.py")

    # 运行PyInstaller
    command_str = " ".join(cmd)
    print(f"执行命令: {command_str}")

    return run_command(command_str, "打包应用程序")


def create_dmg():
    """为macOS创建DMG文件"""
    if platform.system().lower() != "darwin":
        return True

    print("为macOS创建DMG文件...")

    app_path = "dist/DiscordAutoReply.app"
    dmg_path = "dist/DiscordAutoReply.dmg"

    if not os.path.exists(app_path):
        print("❌ 未找到.app文件")
        return False

    # 使用hdiutil创建DMG
    cmd = f"hdiutil create -volname 'DiscordAutoReply' -srcfolder {app_path} -ov -format UDZO {dmg_path}"

    return run_command(cmd, "创建DMG文件")


def main():
    """主函数"""
    print("🚀 Discord自动回复工具打包器")
    print("=" * 50)

    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='打包Discord自动回复工具')
    parser.add_argument('--target', choices=['windows', 'mac', 'auto'],
                       default='auto', help='目标平台 (默认: 自动检测)')
    parser.add_argument('--no-dmg', action='store_true',
                       help='macOS不创建DMG文件')
    args = parser.parse_args()

    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ 需要Python 3.8或更高版本")
        return False

    print(f"Python版本: {sys.version}")
    print(f"目标平台: {args.target}")

    # 检查依赖
    if not check_dependencies():
        return False

    # 切换到项目根目录
    project_root = Path(__file__).parent
    os.chdir(project_root)

    # 清理旧的构建文件
    clean_build()

    # 构建应用程序
    if not build_app(args.target):
        return False

    # 为macOS创建DMG（如果不是Windows目标且没有禁用DMG）
    if not args.no_dmg and platform.system().lower() == "darwin":
        if not create_dmg():
            return False

    print("\n" + "=" * 50)
    print("🎉 打包完成！")

    # 显示输出文件信息
    dist_dir = Path("dist")
    if dist_dir.exists():
        print("\n输出文件:")
        for file_path in dist_dir.iterdir():
            if file_path.is_file():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                print(".2f")

    print("\n📖 使用说明:")
    print("1. 运行生成的可执行文件")
    print("2. 在程序中添加Discord账号和自动回复规则")
    print("3. 点击启动开始监听和自动回复")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
