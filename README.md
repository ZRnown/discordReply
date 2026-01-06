# Discord Auto Reply Tool

一个强大的 Discord 自动回复工具，支持多账号、定时任务、图片发送等功能。

## 🚀 功能特性

- **自动回复**: 基于关键词的智能回复系统
- **定时发帖**: 支持在指定频道定时发布内容
- **评论任务**: 支持回复特定消息或在频道发消息
- **多账号支持**: 同时管理多个 Discord 账号
- **图片发送**: 支持发送单张或多张图片
- **Thread 支持**: 支持在 Discord 论坛频道发帖
- **任务调度**: 智能的任务执行调度
- **反逆向保护**: 编译为机器码，防止逆向工程

## 📦 构建 Windows EXE

### 使用 GitHub Actions 自动构建

1. **推送标签触发构建**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **手动触发构建**:
   - 进入 GitHub 仓库的 "Actions" 标签页
   - 选择 "Build Advanced Protected Windows EXE" workflow
   - 点击 "Run workflow"

### 构建产物

构建完成后会生成以下文件：

- `DiscordAutoReply.exe` - 主可执行文件（推荐）
- `DiscordAutoReply-{version}-windows.zip` - 普通 ZIP 包
- `DiscordAutoReply-{version}-protected.7z` - 密码保护的 7z 包
- `checksums.txt` - SHA256 校验和

### 本地构建（可选）

如果需要本地构建：

```bash
# 安装依赖
pip install -r requirements.txt

# 使用 Nuitka 编译
python -m nuitka --standalone --onefile --windows-uac-admin run.py

# 压缩（可选）
upx --best DiscordAutoReply.exe
```

## 🔒 安全特性

### 反逆向保护

1. **机器码编译**: 使用 Nuitka 将 Python 代码编译为本地机器码
2. **代码混淆**: 自动变量名重命名和代码结构混淆
3. **UPX 压缩**: 高级压缩算法，破坏可执行文件结构
4. **调试信息剥离**: 移除所有调试符号和元数据
5. **单文件打包**: 所有依赖打包为单个 EXE 文件

### 运行时保护

- 敏感信息加密存储
- 运行时完整性检查
- 异常行为检测

## 📋 使用说明

### 基本使用

1. 下载并运行 `DiscordAutoReply.exe`
2. 添加 Discord 账号 Token
3. 配置自动回复规则
4. 设置定时发帖任务
5. 启动机器人

### 评论任务格式

支持多种输入格式：

- **频道ID**: `1457988558332624967` (直接在频道发消息)
- **完整链接**: `https://discord.com/channels/guild_id/channel_id` (同上)
- **回复消息**: `https://discord.com/channels/guild_id/channel_id/message_id`

### 图片上传

- 点击"浏览..."按钮选择图片文件
- 支持同时选择多张图片
- 图片会自动用分号分隔存储

## 🛠️ 开发说明

### 项目结构

```
├── src/
│   ├── discord_client.py    # Discord 客户端核心逻辑
│   ├── gui.py              # PySide6 图形界面
│   ├── config_manager.py   # 配置管理
│   └── main.py             # 程序入口
├── config/                 # 配置文件目录
├── requirements.txt        # Python 依赖
├── run.py                 # 启动脚本
└── .github/workflows/     # GitHub Actions 配置
```

### 本地开发

```bash
# 克隆项目
git clone <repository-url>
cd DiscordAutoReply

# 安装依赖
pip install -r requirements.txt

# 运行程序
python run.py
```

## 📄 许可证

本项目仅供学习和研究使用，请遵守 Discord 服务条款。

## ⚠️ 免责声明

- 请勿用于违反 Discord 服务条款的行为
- 请勿用于发送垃圾信息或骚扰其他用户
- 使用本工具产生的任何后果由使用者自行承担
- 建议仅在自己的服务器上测试使用

## 🆘 问题反馈

如果遇到问题，请：

1. 检查日志输出
2. 确认 Discord Token 有效性
3. 验证网络连接
4. 查看 GitHub Issues

---

**构建时间**: 自动生成
**版本**: 自动生成
