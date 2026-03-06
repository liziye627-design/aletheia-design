# Docker Desktop WSL2 配置图文指南

## 📋 配置概览

本指南帮助您在 Windows 11 上配置 Docker Desktop 的 WSL2 集成，以便在 WSL2 Ubuntu 中运行 Aletheia 项目。

**预计时间**: 5-10 分钟  
**难度**: ⭐⭐☆☆☆ (简单)

---

## 🎯 第一步：启动 Docker Desktop

### 操作步骤

1. 在 Windows 开始菜单中搜索 "Docker Desktop"
2. 点击打开 Docker Desktop 应用
3. 等待 Docker 引擎启动（右下角状态栏显示绿色图标）

### 预期结果
- 任务栏出现 Docker 鲸鱼图标
- 图标状态为绿色（运行中）

### 如果遇到问题
- **Docker Desktop 无法启动**：
  - 检查 Windows Hyper-V 是否已启用
  - 检查 WSL2 是否已安装（运行 `wsl --version`）
  - 重启计算机后再试

---

## ⚙️ 第二步：打开 Docker Desktop 设置

### 操作步骤

1. **点击右上角齿轮图标** 📝
   - 位置：Docker Desktop 窗口右上角
   - 图标样式：⚙️ 齿轮/设置图标

2. **进入设置界面**
   - 弹出 "Settings" 窗口

### 预期结果
- 出现 Docker Desktop Settings 窗口
- 左侧显示多个配置选项卡

---

## 🔗 第三步：配置 WSL Integration

### 操作步骤

1. **点击左侧 "Resources" (资源)**
   ```
   Settings 窗口左侧菜单：
   ├── General
   ├── Resources          ← 点击这里
   │   ├── Advanced
   │   ├── File Sharing
   │   └── WSL Integration  ← 然后点击这里
   ├── Docker Engine
   └── ...
   ```

2. **点击 "WSL Integration" 子菜单**

3. **配置 WSL 集成**
   - 找到 "Enable integration with my default WSL distro" 开关
   - **确保此开关已开启**（蓝色/打勾状态）

4. **启用特定发行版**
   - 在下方 "Enable integration with additional distros:" 部分
   - 找到 **Ubuntu** 或 **Ubuntu-22.04** (取决于您的发行版名称)
   - **打开该发行版旁边的开关**

### 界面示例
```
┌─────────────────────────────────────────────┐
│ WSL Integration                              │
├─────────────────────────────────────────────┤
│                                              │
│ ☑ Enable integration with my default WSL    │
│   distro                                     │
│                                              │
│ Enable integration with additional distros: │
│                                              │
│   Ubuntu              [●○○] ← 打开这个开关   │
│   Ubuntu-20.04        [○○○]                 │
│   Debian              [○○○]                 │
│                                              │
└─────────────────────────────────────────────┘
```

5. **点击右下角 "Apply & Restart" 按钮**
   - Docker Desktop 将重启（约 10-30 秒）

### 预期结果
- Docker Desktop 重启完成
- WSL2 集成配置已生效

---

## ✅ 第四步：验证配置

### 操作步骤

1. **打开 Windows Terminal 或 WSL2 Ubuntu**
   - 按 `Win + X`，选择 "Windows Terminal"
   - 或者在开始菜单搜索 "Ubuntu"

2. **切换到 Ubuntu 环境**（如果已在 Ubuntu 则跳过）
   ```bash
   wsl -d Ubuntu
   ```

3. **运行验证命令**
   ```bash
   docker --version
   ```

### 预期输出
```
Docker version 24.0.6, build ed223bc
```

### 如果遇到问题

#### 问题 1: "docker: command not found"
**原因**: WSL Integration 未生效

**解决方案**:
```bash
# 1. 完全退出 Docker Desktop
# 2. 在 WSL 中运行
wsl --shutdown

# 3. 等待 10 秒后重新打开 Docker Desktop
# 4. 再次尝试 docker --version
```

#### 问题 2: "Cannot connect to the Docker daemon"
**原因**: Docker 引擎未启动

**解决方案**:
- 检查 Docker Desktop 是否正在运行
- 查看任务栏 Docker 图标是否为绿色
- 等待 Docker 完全启动后再试

---

## 🚀 第五步：测试 Docker 功能

### 快速测试命令

```bash
# 1. 测试 Docker 是否可以运行容器
docker run hello-world

# 预期输出：
# Hello from Docker!
# This message shows that your installation appears to be working correctly.

# 2. 测试 Docker Compose（Aletheia 项目需要）
docker-compose --version

# 预期输出：
# Docker Compose version v2.21.0

# 3. 查看 Docker 系统信息
docker info | grep -E "Server Version|Operating System|OSType"

# 预期输出：
# Server Version: 24.0.6
# Operating System: Docker Desktop
# OSType: linux
```

### 全部成功！
如果以上命令都能正常运行，恭喜您！Docker WSL2 集成配置完成 🎉

---

## 📂 下一步：启动 Aletheia 项目

### 现在您可以运行 Aletheia 项目了

```bash
# 1. 进入项目目录
cd /home/llwxy/aletheia/design/aletheia-backend

# 2. 检查配置
cat docker/.env | grep SILICONFLOW_API_KEY
# 应该看到您的 API key (已配置)

# 3. 一键启动所有服务
./start.sh

# 等待 3-5 分钟，所有服务将自动启动
```

### 服务启动后访问

- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **Grafana 监控**: http://localhost:3001 (admin/admin)

---

## 🔍 常见问题排查

### 问题 1: Docker Desktop 显示 "WSL 2 installation is incomplete"

**解决方案**:
```powershell
# 在 PowerShell (管理员) 中运行
wsl --update
wsl --set-default-version 2
```

### 问题 2: 权限被拒绝 (Permission Denied)

**解决方案**:
```bash
# 将当前用户添加到 docker 组（不推荐，因为 WSL2 集成会自动处理）
# 如果还是遇到权限问题：
sudo usermod -aG docker $USER
newgrp docker
```

### 问题 3: WSL Integration 菜单中找不到 Ubuntu

**解决方案**:
```bash
# 1. 检查已安装的 WSL 发行版
wsl -l -v

# 输出示例：
#   NAME            STATE           VERSION
# * Ubuntu          Running         2
#   Ubuntu-20.04    Stopped         2

# 2. 如果 VERSION 显示为 1，需要升级到 WSL2
wsl --set-version Ubuntu 2

# 3. 等待转换完成后，重启 Docker Desktop
```

### 问题 4: Docker 容器无法访问网络

**解决方案**:
```bash
# 1. 检查 Docker 网络配置
docker network ls

# 2. 重置 Docker 网络（谨慎使用）
docker network prune

# 3. 如果是防火墙/VPN 问题，临时关闭后测试
```

---

## 📝 配置检查清单

完成后请确认：

- [ ] Docker Desktop 已安装并运行
- [ ] Docker Desktop Settings → Resources → WSL Integration 已配置
- [ ] "Enable integration with my default WSL distro" 已开启
- [ ] Ubuntu 发行版旁边的开关已打开
- [ ] 已点击 "Apply & Restart"
- [ ] WSL2 中运行 `docker --version` 成功
- [ ] WSL2 中运行 `docker run hello-world` 成功
- [ ] SiliconFlow API key 已配置到 `.env` 文件
- [ ] 准备好启动 Aletheia 项目

---

## 🆘 需要帮助？

如果遇到以上未涵盖的问题：

1. **查看 Docker Desktop 日志**
   - Settings → Troubleshoot → View Logs

2. **检查 WSL2 日志**
   ```bash
   dmesg | tail -50
   ```

3. **重置 Docker Desktop**（最后手段）
   - Settings → Troubleshoot → Reset to factory defaults
   - 注意：这将删除所有容器和镜像

4. **官方文档**
   - https://docs.docker.com/desktop/wsl/

---

## ✅ 配置完成后的验证命令

```bash
# 一键验证脚本 (复制粘贴运行)
echo "=== Docker 版本 ==="
docker --version
echo ""

echo "=== Docker Compose 版本 ==="
docker-compose --version
echo ""

echo "=== Docker 运行测试 ==="
docker run --rm hello-world
echo ""

echo "=== WSL 集成状态 ==="
docker context ls
echo ""

echo "=== 项目配置检查 ==="
cd /home/llwxy/aletheia/design/aletheia-backend
cat docker/.env | grep -E "SILICONFLOW_API_KEY|POSTGRES"
echo ""

echo "✅ 所有检查完成！现在可以运行 ./start.sh 启动项目"
```

**预期所有检查都应该成功通过！** 🎉
