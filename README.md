# Auto Reply Tool

一个强大的自动回复工具，支持多账号、定时任务、图片发送等功能。

## 🚀 功能特性

- **自动回复**: 基于关键词的智能回复系统
- **定时发帖**: 支持在指定频道定时发布内容
- **评论任务**: 支持回复特定消息或在频道发消息
- **多账号支持**: 同时管理多个账号
- **图片发送**: 支持发送单张或多张图片
- **Thread 支持**: 支持在论坛频道发帖
- **任务调度**: 智能的任务执行调度

## 📦 构建 Windows EXE

### 使用 GitHub Actions 自动构建

1. **推送标签触发构建**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **手动触发构建**:
   - 进入 GitHub 仓库的 "Actions" 标签页
   - 选择 "Build Windows EXE" workflow
   - 点击 "Run workflow"

### 构建产物

构建完成后会生成以下文件：
- `AutoReply.exe` - 主可执行文件
- `AutoReply-{version}-windows.zip` - ZIP 归档

### 本地构建

```bash
# 确保在 Windows 环境中运行
python build_exe.py
```

本地构建需要：
- Python 3.8+
- 所有项目依赖 (自动安装)
- UPX (可选，用于压缩)

## 📋 使用说明

### 基本使用

1. 下载并运行 `AutoReply.exe`
2. 添加账号 Token
3. 配置自动回复规则
4. 设置定时发帖任务
5. 启动账号

### 评论任务格式

支持多种输入格式：

- **频道ID**: `1457988558332624967` (直接在频道发消息)
- **完整链接**: `https://discord.com/channels/guild_id/channel_id` (同上)

### 图片上传

- 点击"浏览..."按钮选择图片文件
- 支持同时选择多张图片
- 图片会自动用分号分隔存储

## 🔐 许可证配置

### 许可证服务器设置

如果遇到许可证激活失败（HTTP 403错误），可能需要配置正确的服务器认证信息：

1. **运行程序**：`python run.py`
2. **进入状态监控标签页**
3. **点击"配置服务器"按钮**
4. **输入正确的用户名和密码**
5. **测试连接**后保存配置

### 测试许可证

使用测试脚本验证许可证：

```bash
# 基本测试（使用默认配置）
python test_license.py 09c4661532162b8ad4a4b04bbb1f80e2

# 自定义服务器配置测试
python test_license.py 09c4661532162b8ad4a4b04bbb1f80e2 admin password https://your-license-server.com /api/v1
```

### GUI中激活许可证

**重要：软件现在要求强制激活许可证！未激活的许可证无法使用软件。**

1. **首次运行软件**：
   - 运行：`python run.py`
   - 如果没有配置许可证，会弹出许可证输入对话框

2. **激活许可证**：
   - 在许可证输入对话框中输入许可证密钥
   - 点击"测试"验证许可证是否有效（显示为"许可证有效（未激活）"）
   - 点击"验证"激活并绑定到当前机器
   - 激活成功后软件才能正常使用

**激活失败的常见原因：**
- 网络错误：检查网络连接是否正常
- 许可证已被其他机器激活：联系管理员获取新的许可证
- 许可证不存在：确认许可证密钥是否正确

### 创建和管理许可证

#### 1. 创建许可证
```bash
# 使用默认机器指纹作为ID
python create_license.py https://license.thy1cc.top admin password

# 使用自定义许可证ID
python create_license.py https://license.thy1cc.top admin password 09c4661532162b8ad4a4b04bbb1f80e2
```

#### 2. 管理许可证
```bash
# 激活许可证（绑定到当前机器）
python manage_license.py activate https://license.thy1cc.top admin password 09c4661532162b8ad4a4b04bbb1f80e2

# 验证许可证状态
python manage_license.py validate https://license.thy1cc.top client password 09c4661532162b8ad4a4b04bbb1f80e2

# 更新许可证字段（需要管理员权限）
python manage_license.py update https://license.thy1cc.top admin password 09c4661532162b8ad4a4b04bbb1f80e2 machine-node YOUR_MACHINE_ID

# 列出所有许可证
python manage_license.py list https://license.thy1cc.top admin password
```

#### 3. 批量创建许可证
```bash
# 创建10个许可证（默认）
python batch_create_licenses.py https://license.thy1cc.top admin password

# 创建指定数量的许可证
python batch_create_licenses.py https://license.thy1cc.top admin password 50

# 创建带前缀的许可证
python batch_create_licenses.py https://license.thy1cc.top admin password 20 VIP

# 脚本会自动保存创建的许可证ID到文件中
```

#### 4. 重置许可证状态
```bash
# 重置所有许可证状态为未激活（慎用！）
python reset_licenses.py <服务器URL> <管理员用户名> <管理员密码>

# 此操作会将所有许可证的machine-node重置为NOT_ACTIVATED
# 用户需要重新激活他们的许可证
```

#### 5. 许可证绑定说明
- 创建许可证时，`machine-node` 字段设置为 `"NOT_ACTIVATED"`
- 用户首次激活时，系统会自动将 `machine-node` 设置为用户的机器指纹
- 此后该许可证只能在此机器上使用，确保一个许可证只能被一台机器使用

## 🛠️ 开发说明

### 项目结构

```
├── src/
│   ├── discord_client.py    # 客户端核心逻辑
│   ├── gui.py              # PySide6 图形界面
│   ├── config_manager.py   # 配置管理
│   └── main.py             # 程序入口
├── config/                 # 配置文件目录
├── build_exe.py           # Windows EXE 构建脚本
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

本项目仅供学习和研究使用，请遵守相关服务条款。

## ⚠️ 免责声明

- 请勿用于违反服务条款的行为
- 请勿用于发送垃圾信息或骚扰其他用户
- 使用本工具产生的任何后果由使用者自行承担
- 建议仅在自己的服务器上测试使用