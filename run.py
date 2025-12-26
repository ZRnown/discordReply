#!/usr/bin/env python3
"""
Discord自动回复工具运行脚本
"""

import sys
import os
from pathlib import Path

def main():
    """主函数"""
    # 添加src目录到Python路径
    project_root = Path(__file__).parent
    src_dir = project_root / "src"
    sys.path.insert(0, str(src_dir))

    # 检查依赖
    try:
        import PySide6
        import discord
        import qasync
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        return

    # 运行程序
    from src.gui import main
    main()

if __name__ == "__main__":
    main()
