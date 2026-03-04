# Docker Desktop WSL2 配置 - 即时操作指南

**当前时间**: 2026-02-03  
**预计耗时**: 5-10 分钟  
**难度**: ⭐⭐☆☆☆ (简单)

---

## 📋 第一步：检查 Docker Desktop 是否已安装

### 操作步骤

1. **按 Windows 键**，搜索 "Docker Desktop"
2. 查看是否能找到这个应用

### 🔍 检查结果

#### ✅ 如果找到了 Docker Desktop
→ 继续第二步

#### ❌ 如果没有找到 Docker Desktop
→ 需要先安装 Docker Desktop

**安装步骤**：
1. 访问：https://www.docker.com/products/docker-desktop/
2. 点击 "Download for Windows"
3. 下载完成后，双击安装文件
4. 安装过程中选择 "Use WSL 2 instead of Hyper-V"
5. 安装完成后重启计算机
6. 重启后继续本指南

---

## 🚀 第二步：启动 Docker Desktop

### 操作步骤

1. **按 Windows 键**，搜索 "Docker Desktop"
2. **点击打开** Docker Desktop 应用
3. **等待 Docker 引擎启动**（约 30-60 秒）

### 🔍 验证启动成功

查看 **Windows 任务栏右下角**：
- ✅ 应该看到 Docker 鲸鱼图标 🐋
- ✅ 图标应该是 **绿色** 或 **静止** 状态（不闪烁）

### ⚠️ 如果 Docker Desktop 启动失败

**常见错误 1**: "WSL 2 installation is incomplete"
```powershell
# 在 PowerShell (管理员) 中运行：
wsl --update
wsl --set-default-version 2
```

**常见错误 2**: "Docker Desktop requires Windows 10/11"
- 确保您的 Windows 版本至少是 Windows 10 版本 2004 或更高

**常见错误 3**: "Hyper-V is not enabled"
```powershell
# 在 PowerShell (管理员) 中运行：
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
```

重启后再试。

---

## ⚙️ 第三步：打开 Docker Desktop 设置

### 操作步骤

1. **确保 Docker Desktop 已打开** 并在前台显示
2. **点击右上角的齿轮图标** ⚙️（Settings 设置）

### 🖼️ 界面说明

```
┌─────────────────────────────────────────────┐
│  Docker Desktop                    ⚙️ 📋 🔔 │  ← 点击这个齿轮
├─────────────────────────────────────────────┤
│                                             │
│  Containers / Apps                          │
│  Images                                     │
│  Volumes                                    │
│                                             │
└─────────────────────────────────────────────┘
```

3. **弹出 Settings 窗口**

---

## 🔗 第四步：配置 WSL Integration（核心步骤）

### 操作步骤

在 Settings 窗口左侧菜单中：

1. **点击 "Resources"（资源）**
   ```
   Settings 左侧菜单：
   ├── General
   ├── Resources              ← 点击这里
   │   ├── Advanced
   │   ├── File Sharing
   │   └── WSL Integration    ← 然后点击这里
   ├── Docker Engine
   └── ...
   ```

2. **点击 "WSL Integration"**

### 🖼️ WSL Integration 配置界面

您将看到如下界面：

```
┌──────────────────────────────────────────────────┐
│ WSL Integration                                   │
├──────────────────────────────────────────────────┤
│                                                   │
│ ☑ Enable integration with my default WSL distro │
│                                                   │
│ Enable integration with additional distros:      │
│                                                   │
│   Ubuntu              [○] ← 点击这个开关变成 [●] │
│   Ubuntu-22.04        [○]                        │
│   Ubuntu-20.04        [○]                        │
│   Debian              [○]                        │
│                                                   │
│                                    [Apply & Restart] │
└──────────────────────────────────────────────────┘
```

### 🔧 配置选项

1. **确保第一个开关已开启**：
   ```
   ☑ Enable integration with my default WSL distro
   ```
   - 这个应该默认是开启的（有勾）
   - 如果没有勾，请点击打开

2. **找到您的 Ubuntu 发行版**：
   - 查找 "Ubuntu" 或 "Ubuntu-22.04" 或类似名称
   - 点击右侧的 **开关** 将其打开（从 [○] 变成 [●]）

3. **点击右下角 "Apply & Restart" 按钮**

### ⏳ 等待重启

- Docker Desktop 将重启（约 20-30 秒）
- 等待右下角 Docker 图标再次变为绿色

---

## ✅ 第五步：验证配置成功

### 操作步骤

1. **打开 Windows Terminal** 或 **Ubuntu 应用**
   - 按 `Win + X`，选择 "Windows Terminal"
   - 或者在开始菜单搜索 "Ubuntu"

2. **运行以下命令验证**：

```bash
# 验证 1：检查 Docker 版本
docker --version

# 预期输出：
# Docker version 24.0.x, build xxxxx
```

```bash
# 验证 2：运行测试容器
docker run hello-world

# 预期输出：
# Hello from Docker!
# This message shows that your installation appears to be working correctly.
```

```bash
# 验证 3：检查 Docker Compose
docker-compose --version

# 预期输出：
# Docker Compose version v2.x.x
```

### 🎉 全部成功！

如果以上 3 个命令都能正常运行，恭喜您！Docker WSL2 集成配置完成！

---

## 🚀 第六步：启动 Aletheia 项目

### 现在可以启动项目了！

```bash
# 1. 进入项目目录
cd /home/llwxy/aletheia/design/aletheia-backend

# 2. 检查配置（确认 API key 已设置）
cat docker/.env | grep SILICONFLOW_API_KEY

# 应该看到：
# SILICONFLOW_API_KEY=sk-your-siliconflow-api-key

# 3. 一键启动所有服务
./start.sh
```

### ⏳ 等待服务启动

启动过程约需 **3-5 分钟**，您将看到：

```
Starting Aletheia services...
[+] Running 8/8
 ✔ Network aletheia_default    Created
 ✔ Volume "aletheia_postgres"  Created
 ✔ Volume "aletheia_redis"     Created
 ✔ Container aletheia-postgres Started
 ✔ Container aletheia-redis    Started
 ✔ Container aletheia-kafka    Started
 ✔ Container aletheia-api      Started
 ✔ Container aletheia-worker   Started

Services are starting up...
API will be available at: http://localhost:8000
Grafana will be available at: http://localhost:3001
```

### 🌐 访问服务

启动完成后，打开浏览器访问：

- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **Grafana 监控**: http://localhost:3001 (用户名/密码: admin/admin)

---

## 🧪 第七步：运行自动化测试

```bash
# 进入项目目录
cd /home/llwxy/aletheia/design/aletheia-backend

# 运行测试脚本
./test_api.sh
```

### 📊 预期测试结果

```
╔═══════════════════════════════════════════╗
║   Aletheia API 自动化测试套件             ║
╚═══════════════════════════════════════════╝

>>> 等待 API 服务启动...
✓ API 服务已就绪

>>> 测试 1: 健康检查
✓ 健康检查通过

>>> 测试 2: 微博热搜榜
✓ 微博热搜获取成功

...

╔═══════════════════════════════════════════╗
║           测试结果汇总                    ║
╚═══════════════════════════════════════════╝

总测试数: 12
通过: 12
失败: 0

╔═══════════════════════════════════════════╗
║  🎉 所有测试通过！系统运行正常！         ║
╚═══════════════════════════════════════════╝
```

---

## 🎭 第八步：练习黑客松演示

```bash
# 运行演示脚本
cd /home/llwxy/aletheia/design/aletheia-backend
./demo_script.sh
```

这个脚本包含：
- 8 个演示章节
- 交互式演示流程
- 自动 API 调用展示
- 完整的商业故事线

---

## ❌ 常见问题排查

### 问题 1: "docker: command not found"

**原因**: WSL Integration 未生效

**解决方案**:
```bash
# 1. 在 WSL 中完全关闭 WSL
wsl --shutdown

# 2. 等待 10 秒

# 3. 重新打开 Ubuntu

# 4. 再次尝试
docker --version
```

如果还是不行：
- 回到 Docker Desktop
- Settings → Resources → WSL Integration
- 确认 Ubuntu 的开关是打开的（[●]）
- 再次点击 "Apply & Restart"

---

### 问题 2: "Cannot connect to the Docker daemon"

**原因**: Docker Desktop 未启动或正在启动

**解决方案**:
1. 检查任务栏 Docker 图标是否为绿色
2. 如果是灰色或闪烁，等待启动完成
3. 如果没有图标，启动 Docker Desktop 应用

---

### 问题 3: "permission denied while trying to connect"

**原因**: 用户权限问题（不常见）

**解决方案**:
```bash
# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录 shell
newgrp docker

# 再次尝试
docker ps
```

---

### 问题 4: WSL Integration 菜单中找不到 Ubuntu

**原因**: WSL 发行版版本为 WSL 1

**解决方案**:

在 **PowerShell (管理员)** 中运行：

```powershell
# 1. 查看当前 WSL 发行版
wsl --list --verbose

# 输出示例：
#   NAME            STATE           VERSION
# * Ubuntu          Running         1         ← 如果是 1，需要升级

# 2. 升级到 WSL 2
wsl --set-version Ubuntu 2

# 3. 等待转换完成（可能需要几分钟）

# 4. 重启 Docker Desktop
```

---

### 问题 5: Docker Desktop 无法启动

**错误信息**: "Docker Desktop starting..." 一直转圈

**解决方案**:

1. **完全退出 Docker Desktop**
   - 右键任务栏 Docker 图标 → Quit Docker Desktop

2. **重置 Docker Desktop** (最后手段)
   - 打开 Docker Desktop
   - Settings → Troubleshoot → Reset to factory defaults
   - 等待重置完成
   - 重新配置 WSL Integration

---

## 📞 需要帮助？

### 查看 Docker 日志

在 Docker Desktop 中：
- Settings → Troubleshoot → View Logs

### 查看 WSL 日志

```bash
# 在 Ubuntu 中运行
dmesg | tail -50
```

### 官方文档

- Docker Desktop WSL 2: https://docs.docker.com/desktop/wsl/
- WSL 官方文档: https://docs.microsoft.com/windows/wsl/

---

## ✅ 配置完成检查清单

完成后请确认：

- [ ] Docker Desktop 已安装并运行
- [ ] 任务栏 Docker 图标为绿色
- [ ] Settings → Resources → WSL Integration 已配置
- [ ] "Enable integration with my default WSL distro" 已勾选
- [ ] Ubuntu 发行版旁边的开关已打开
- [ ] 已点击 "Apply & Restart"
- [ ] WSL2 中 `docker --version` 成功
- [ ] WSL2 中 `docker run hello-world` 成功
- [ ] Aletheia 项目已启动 `./start.sh`
- [ ] 测试脚本运行成功 `./test_api.sh`
- [ ] 可以访问 http://localhost:8000/docs

---

## 🎯 下一步

配置完成后：

1. ✅ 测试 API 功能 → `./test_api.sh`
2. ✅ 练习演示脚本 → `./demo_script.sh`
3. ✅ 准备 PPT 演示内容
4. ✅ 准备黑客松提交材料

---

**祝您配置顺利！** 🚀

如果遇到任何问题，请参考 "常见问题排查" 部分，或查看完整文档：
- `/home/llwxy/aletheia/design/aletheia-backend/DOCKER_WSL2_SETUP.md`
