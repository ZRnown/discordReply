#!/usr/bin/env python3
"""
Discord自动回复工具运行脚本
"""

import sys
import os
from pathlib import Path

def main():
    # 1. 路径设置 - 修复打包后的工作目录问题
    if getattr(sys, 'frozen', False):
        # 运行在打包后的 EXE 中
        exe_dir = Path(sys.executable).parent
        os.chdir(exe_dir)
        project_root = exe_dir
    else:
        # 运行在开发环境中
        project_root = Path(__file__).parent

    src_dir = project_root / "src"
    sys.path.insert(0, str(src_dir))

    # 2. 依赖检查
    try:
        import discord
        import PySide6

        # 移除了对 Intents 的检查，因为 discord.py-self 2.0+ 已经废弃了它
        print(f"Discord 库版本: {getattr(discord, '__version__', '未知')}")
        print("环境依赖检查通过。")

    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install discord.py-self PySide6 typing-extensions")
        return 1

    # 3. 启动 GUI - 添加错误捕获
    try:
        from src.gui import main as gui_main
        result = gui_main()
        return result if result is not None else 0
    except Exception as e:
        error_msg = f"程序启动失败: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()

        # 尝试显示错误对话框（仅在 Windows 上）
        try:
            if sys.platform == 'win32':
                import ctypes
                error_details = f"{error_msg}\n\n详细信息:\n{traceback.format_exc()}"
                ctypes.windll.user32.MessageBoxW(0, error_details, "Discord Auto Reply - 错误", 0x10)
        except:
            pass

        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code if exit_code is not None else 0)