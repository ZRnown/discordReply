#!/usr/bin/env python3
"""
Discord Auto Reply Tool - Windows EXE Builder
构建 Windows 可执行文件
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def check_requirements():
    """检查构建要求"""
    print("🔍 检查构建要求...")

    # 检查 Python 版本
    if sys.version_info < (3, 8):
        print("❌ 需要 Python 3.8 或更高版本")
        return False

    # 检查操作系统
    if platform.system() != "Windows":
        print("⚠️  此脚本针对 Windows 优化，当前系统:", platform.system())

    print("✅ 构建要求检查通过")
    return True

def install_dependencies():
    """安装构建依赖"""
    print("📦 安装构建依赖...")

    try:
        # 升级 pip
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)

        # 安装项目依赖
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

        print("✅ 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        return False

def build_exe():
    """使用 Nuitka 构建 EXE"""
    print("🔨 开始构建 EXE...")

    config_dir = Path("config")
    if not config_dir.exists():
        config_dir.mkdir()
        print("创建 config 目录")

    example_config = Path("config/example_config.json")
    main_config = Path("config/config.json")
    if example_config.exists() and not main_config.exists():
        import shutil
        shutil.copy(example_config, main_config)
        print("复制示例配置文件")

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--windows-uac-admin",
        "--windows-company-name=Discord Auto Reply",
        "--windows-product-name=Discord Auto Reply Tool",
        "--windows-file-description=Discord Auto Reply Tool",
        "--windows-file-version=1.0.0.0",
        "--windows-product-version=1.0.0.0",
        "--enable-plugin=pyside6",
        "--enable-plugin=multiprocessing",
        "--windows-console-mode=disable",
        "--include-package=discord",
        "--include-package=aiohttp",
        "--include-package=asyncio",
        "--include-package=src",
        "--include-package=src.discord_client",
        "--include-package=src.config_manager",
        "--include-package=src.gui",
        "--include-data-dir=config=config",
        "--assume-yes-for-downloads",
        "--output-filename=DiscordAutoReply.exe",
        "--output-dir=dist",
        "run.py"
    ]

    try:
        print("执行构建命令...")
        subprocess.run(cmd, check=True)
        print("✅ EXE 构建完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ EXE 构建失败: {e}")
        return False

def compress_exe():
    """使用 UPX 压缩 EXE"""
    print("🗜️  压缩 EXE 文件...")

    exe_path = Path("dist/DiscordAutoReply.exe")
    if not exe_path.exists():
        print("❌ 找不到 EXE 文件")
        return False

    try:
        # 检查 UPX 是否可用
        result = subprocess.run(["upx", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("⚠️  UPX 未安装，跳过压缩")
            return True

        # 压缩 EXE
        subprocess.run(["upx", "--best", str(exe_path)], check=True)
        print("✅ EXE 压缩完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ EXE 压缩失败: {e}")
        return False

def create_archive():
    """创建发布归档"""
    print("📦 创建发布归档...")

    exe_path = Path("dist/DiscordAutoReply.exe")
    if not exe_path.exists():
        print("❌ 找不到 EXE 文件")
        return False

    try:
        zip_name = "DiscordAutoReply-windows.zip"

        if platform.system() == "Windows":
            ps_cmd = f'Compress-Archive -Path "{exe_path}" -DestinationPath "{zip_name}" -Force'
            subprocess.run(["powershell", "-Command", ps_cmd], check=True)
        else:
            import zipfile
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(exe_path, exe_path.name)

        print(f"✅ 归档创建完成: {zip_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 归档创建失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 归档创建失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 Discord Auto Reply Tool - Windows EXE 构建器")
    print("=" * 50)

    # 检查要求
    if not check_requirements():
        return 1

    # 安装依赖
    if not install_dependencies():
        return 1

    # 构建 EXE
    if not build_exe():
        return 1

    # 压缩 EXE
    compress_exe()

    # 创建归档
    create_archive()

    print("\n🎉 构建完成！")
    print("生成的文件:")
    print("  - dist/DiscordAutoReply.exe")
    print("  - DiscordAutoReply-windows.zip")

    return 0

if __name__ == "__main__":
    sys.exit(main())
