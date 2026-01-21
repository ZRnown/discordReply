#!/usr/bin/env python3
"""
Discord 自动回复工具
支持多账号、多规则的Discord自动回复桌面应用

此软件受版权保护，未经授权禁止逆向工程、修改或分发。
违反者将承担法律责任。
"""

import sys
import os
import platform
import hashlib
import time

# 反逆向保护：检查是否在调试环境中运行
def anti_debug_check():
    """反调试检查"""
    # 检查常见的调试器进程
    debug_processes = ['ollydbg.exe', 'ida.exe', 'ida64.exe', 'x32dbg.exe', 'x64dbg.exe',
                      'windbg.exe', 'gdb', 'lldb', 'dbx', 'ddd']

    try:
        if platform.system() == 'Windows':
            import subprocess
            result = subprocess.run(['tasklist'], capture_output=True, text=True, timeout=5)
            for process in debug_processes:
                if process.lower() in result.stdout.lower():
                    print("检测到调试器进程，程序退出")
                    sys.exit(1)
    except:
        pass  # 如果检查失败，继续运行

    # 检查调试标志
    try:
        import pdb
        if hasattr(sys, 'gettrace') and sys.gettrace():
            print("检测到调试模式，程序退出")
            sys.exit(1)
    except:
        pass

# 完整性检查
def integrity_check():
    """代码完整性检查"""
    try:
        # 计算当前文件的哈希值
        current_hash = hashlib.sha256(open(__file__, 'rb').read()).hexdigest()
        expected_hash = "PLACEHOLDER_HASH"  # 在构建时替换为实际哈希值

        if expected_hash != "PLACEHOLDER_HASH" and current_hash != expected_hash:
            print("文件完整性检查失败，程序可能已被篡改")
            sys.exit(1)
    except:
        pass  # 如果检查失败，继续运行

# 许可证检查
def license_check():
    """许可证预检查"""
    try:
        from discord_client import LicenseManager
        from config_manager import ConfigManager
        license_manager = LicenseManager()

        config_manager = ConfigManager()
        license_config = config_manager.load_config()[2]
        license_key = license_config.get("license_key", "").strip()
        saved_hwid = license_config.get("hwid")
        is_activated = license_config.get("is_activated", False)
        license_info = license_config.get("license_info")

        if license_key and is_activated and saved_hwid == license_manager.machine_fingerprint:
            license_manager.license_key = license_key
            license_manager.is_activated = True
            if isinstance(license_info, dict):
                license_manager.license_info = license_info

        # 尝试加载已保存的许可证信息
        # 这里可以添加从配置文件加载许可证的逻辑

        if not license_manager.is_license_valid():
            print("许可证无效，请先激活软件")
            # 不在这里退出，由GUI处理许可证验证
    except Exception as e:
        print(f"许可证检查失败: {e}")
        # 许可证检查失败时继续运行，由GUI处理

def main():
    """主函数"""
    # 执行反逆向检查
    anti_debug_check()
    integrity_check()
    license_check()

    # 添加src目录到Python路径
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    try:
        from gui import main as gui_main
    except ImportError:
        # 如果相对导入失败，尝试绝对导入
        import gui
        gui_main = gui.main

    # 启动GUI
    gui_main()

if __name__ == "__main__":
    # 直接调用 main()，因为 gui.main() 是同步的 (app.exec())
    # 不要使用 asyncio.run()，因为 PySide6 的事件循环接管了主线程
    main()
