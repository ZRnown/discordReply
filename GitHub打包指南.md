# GitHub Actions Windows打包指南

## 📋 前置要求

1. **GitHub账号**：确保有GitHub账号
2. **代码上传**：将项目代码上传到GitHub仓库
3. **文件完整**：确保包含以下文件：
   - `src/` 目录及所有Python文件
   - `requirements.txt`
   - `build.py`
   - `.github/workflows/build-windows.yml`
   - `Windows使用说明.md`

## 🚀 设置步骤

### 步骤1：创建GitHub仓库

1. 登录 [GitHub.com](https://github.com)
2. 点击右上角 **"+"** → **"New repository"**
3. 填写仓库信息：
   - **Repository name**: `discord-auto-reply` 或您喜欢的名称
   - **Description**: Discord自动回复工具
   - **Visibility**: Public（公开）或Private（私有）
4. 点击 **"Create repository"**

### 步骤2：上传代码

#### 方法1：Git命令行（推荐）
```bash
# 初始化本地仓库
git init
git add .
git commit -m "Initial commit"

# 添加远程仓库
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main
```

#### 方法2：GitHub网页上传
1. 在仓库页面点击 **"Add file"** → **"Upload files"**
2. 拖拽或选择所有项目文件
3. 点击 **"Commit changes"**

### 步骤3：触发自动构建

1. **推送代码**：上传代码后，GitHub Actions会自动开始构建
2. **查看进度**：
   - 点击仓库的 **"Actions"** 标签页
   - 看到 **"Build Windows Executable"** workflow正在运行
   - 等待构建完成（约5-10分钟）

### 步骤4：下载构建产物

1. **进入Actions页面**：点击 **"Actions"** 标签页
2. **选择workflow运行**：点击最新的 **"Build Windows Executable"**
3. **下载产物**：
   - 在页面下方找到 **"Artifacts"** 部分
   - 点击 **"DiscordAutoReply-Windows"** 下载

## 📦 下载内容

下载的ZIP文件包含：
- `DiscordAutoReply.exe` - Windows可执行程序（~50MB）
- `Windows使用说明.md` - 详细使用指南

## 🔧 故障排除

### 构建失败

**检查清单**：
1. ✅ 所有必需文件已上传
2. ✅ `requirements.txt` 包含正确依赖
3. ✅ `build.py` 有执行权限
4. ✅ Python语法正确

**常见问题**：
- **依赖安装失败**：检查 `requirements.txt` 格式
- **PyInstaller错误**：确保所有导入的模块都正确
- **文件路径错误**：检查相对路径是否正确

### 产物不存在

如果构建成功但没有产物：
1. 检查 `build.py` 是否正确生成了文件
2. 确认产物在 `dist/` 目录中
3. 检查workflow中的上传配置

### Token相关问题

构建产物不包含任何Token信息，Token需要在运行时手动配置。

## ⚙️ 高级配置

### 自定义构建

修改 `.github/workflows/build-windows.yml`：

```yaml
# 更改Python版本
python-version: '3.10'

# 添加构建参数
run: python build.py --target windows --no-clean
```

### 定时构建

添加定时触发：

```yaml
on:
  schedule:
    - cron: '0 0 * * 0'  # 每周日构建
```

### 多平台构建

添加macOS构建：

```yaml
jobs:
  build-windows:
    # Windows构建...

  build-macos:
    runs-on: macos-latest
    # macOS构建配置...
```

## 📊 构建统计

- **构建时间**：约5-10分钟
- **产物大小**：~50MB
- **免费额度**：每月2000分钟（足够多次构建）
- **存储时间**：产物保留30天

## 💡 最佳实践

1. **定期推送**：有代码更新时及时推送
2. **版本标记**：重要版本使用Git标签
3. **文档更新**：及时更新使用说明
4. **备份下载**：重要版本及时下载备份

## 📞 获取帮助

如果遇到问题：

1. **检查Actions日志**：查看详细的构建日志
2. **验证文件完整性**：确保所有必需文件已上传
3. **检查依赖版本**：确认Python和包版本兼容
4. **查看GitHub状态**：确认GitHub Actions服务正常

---

**🎉 现在您可以在macOS上轻松生成Windows可执行文件了！**
