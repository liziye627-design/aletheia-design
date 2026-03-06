# Aletheia 故障排除指南

本指南帮助您解决前后端集成过程中可能遇到的常见问题。

## 🔍 快速诊断

### 检查服务状态

```bash
# 检查后端是否运行
curl http://localhost:8000/health

# 检查前端是否运行
curl http://localhost:5173
```

### 查看日志

```bash
# 查看后端日志
tail -f runtime/logs/backend.log

# 查看前端日志
tail -f runtime/logs/frontend.log
```

## ❌ 常见问题

### 1. 后端无法启动

#### 问题: "未安装 Python3"

**错误信息:**
```
❌ 错误: 未安装 Python3
```

**解决方案:**
1. 安装Python 3.10或更高版本
2. 验证安装: `python3 --version`
3. 确保Python在系统PATH中

**下载地址:**
- https://www.python.org/downloads/

---

#### 问题: "缺少 LLM API Key"

**错误信息:**
```
❌ 错误: 未配置任何 LLM API Key
```

**解决方案:**
1. 编辑 `aletheia-backend/.env`
2. 添加至少一个API Key:
   ```env
   SILICONFLOW_API_KEY=your_key_here
   # 或
   OPENAI_API_KEY=your_key_here
   # 或
   KIMI_API_KEY=your_key_here
   ```
3. 重新启动服务

**获取API Key:**
- SiliconFlow: https://siliconflow.cn/
- OpenAI: https://platform.openai.com/
- Kimi: https://platform.moonshot.cn/

---

#### 问题: "端口8000已被占用"

**错误信息:**
```
ERROR: [Errno 48] Address already in use
```

**解决方案:**

**方法1: 找到并停止占用端口的进程**
```bash
# Linux/Mac
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**方法2: 修改后端端口**
编辑 `scripts/start-dev.sh`，修改端口号：
```bash
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 9000
```

记得同时更新前端 `.env` 中的 `VITE_API_BASE_URL`！

---

#### 问题: "虚拟环境创建失败"

**错误信息:**
```
Error: Unable to create virtual environment
```

**解决方案:**
1. 确保安装了 `python3-venv`:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install python3-venv
   
   # macOS (使用Homebrew)
   brew install python3
   ```
2. 手动创建虚拟环境:
   ```bash
   cd aletheia-backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

---

### 2. 前端无法启动

#### 问题: "未安装 Node.js"

**错误信息:**
```
❌ 错误: 未安装 Node.js
```

**解决方案:**
1. 安装Node.js 18或更高版本
2. 验证安装: `node --version`
3. 确保npm也已安装: `npm --version`

**下载地址:**
- https://nodejs.org/

---

#### 问题: "端口5173已被占用"

**错误信息:**
```
Port 5173 is in use
```

**解决方案:**

**方法1: 停止占用端口的进程**
```bash
# Linux/Mac
lsof -i :5173
kill -9 <PID>

# Windows
netstat -ano | findstr :5173
taskkill /PID <PID> /F
```

**方法2: 修改前端端口**
编辑 `frontend/vite.config.ts`:
```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
  },
})
```

记得同时更新后端CORS配置！

---

#### 问题: "npm install 失败"

**错误信息:**
```
npm ERR! code EACCES
npm ERR! syscall access
```

**解决方案:**

**方法1: 修复npm权限**
```bash
sudo chown -R $USER:$GROUP ~/.npm
sudo chown -R $USER:$GROUP ~/.config
```

**方法2: 使用nvm管理Node.js**
```bash
# 安装nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# 安装Node.js
nvm install 18
nvm use 18
```

**方法3: 清理缓存重试**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

---

### 3. CORS错误

#### 问题: "CORS policy blocked"

**错误信息（浏览器控制台）:**
```
Access to fetch at 'http://localhost:8000/api/v1/...' from origin 'http://localhost:5173' 
has been blocked by CORS policy
```

**解决方案:**

1. **检查后端CORS配置**
   
   编辑 `aletheia-backend/core/config.py`，确保包含前端端口:
   ```python
   BACKEND_CORS_ORIGINS: list[str] = [
       "http://localhost:3000",
       "http://localhost:5173",
       "http://127.0.0.1:3000",
       "http://127.0.0.1:5173",
   ]
   ```

2. **重启后端服务**
   ```bash
   ./scripts/stop-dev.sh
   ./scripts/start-dev.sh
   ```

3. **清除浏览器缓存**
   - 按 Ctrl+Shift+Delete (Windows/Linux) 或 Cmd+Shift+Delete (Mac)
   - 清除缓存和Cookie
   - 刷新页面

---

### 4. API请求失败

#### 问题: "网络请求失败"

**错误信息（前端）:**
```
网络请求失败（fetch failed）。请确认后端已启动：http://localhost:8000/api/v1
```

**解决方案:**

1. **确认后端正在运行**
   ```bash
   curl http://localhost:8000/health
   ```
   
   如果失败，启动后端:
   ```bash
   ./scripts/start-dev.sh
   ```

2. **检查API_BASE_URL配置**
   
   编辑 `frontend/.env`:
   ```env
   VITE_API_BASE_URL=http://localhost:8000/api/v1
   ```

3. **检查防火墙设置**
   
   确保防火墙允许本地端口8000和5173的连接

---

#### 问题: "404 Not Found"

**错误信息:**
```
状态码不匹配: 期望 200, 实际 404
```

**解决方案:**

1. **验证API端点**
   
   运行端点验证工具:
   ```bash
   cd scripts
   npx ts-node verify-api-endpoints.ts
   ```

2. **检查API路由**
   
   查看 `aletheia-backend/api/v1/router.py` 确认路由已注册

3. **查看API文档**
   
   访问 http://localhost:8000/docs 查看所有可用端点

---

#### 问题: "422 Unprocessable Entity"

**错误信息:**
```
请求参数格式错误
```

**解决方案:**

1. **检查请求payload**
   
   确保请求数据符合后端schema定义

2. **查看API文档**
   
   访问 http://localhost:8000/docs 查看端点的请求格式

3. **查看后端日志**
   ```bash
   tail -f runtime/logs/backend.log
   ```
   
   查找详细的验证错误信息

---

### 5. 环境配置问题

#### 问题: ".env 文件不存在"

**错误信息:**
```
❌ 错误: 前端 .env 文件不存在
```

**解决方案:**

运行环境配置脚本:
```bash
./scripts/setup-env.sh
```

或手动创建:
```bash
# 前端
cp frontend/.env.example frontend/.env

# 后端
cp aletheia-backend/.env.example aletheia-backend/.env
```

---

#### 问题: "环境变量未生效"

**症状:**
- 修改了 `.env` 文件但没有效果
- 应用仍使用旧的配置值

**解决方案:**

1. **重启服务**
   ```bash
   ./scripts/stop-dev.sh
   ./scripts/start-dev.sh
   ```

2. **清除缓存**
   ```bash
   # 前端
   cd frontend
   rm -rf node_modules/.vite
   
   # 后端
   cd aletheia-backend
   rm -rf __pycache__
   ```

3. **验证环境变量**
   
   前端（在浏览器控制台）:
   ```javascript
   console.log(import.meta.env.VITE_API_BASE_URL)
   ```
   
   后端（在代码中）:
   ```python
   from core.config import settings
   print(settings.BACKEND_CORS_ORIGINS)
   ```

---

### 6. 依赖安装问题

#### 问题: "Python包安装失败"

**错误信息:**
```
ERROR: Could not install packages due to an OSError
```

**解决方案:**

1. **升级pip**
   ```bash
   python3 -m pip install --upgrade pip
   ```

2. **使用国内镜像**
   ```bash
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

3. **逐个安装依赖**
   ```bash
   pip install fastapi
   pip install uvicorn
   # ... 其他依赖
   ```

---

#### 问题: "TypeScript编译错误"

**错误信息:**
```
error TS2307: Cannot find module
```

**解决方案:**

1. **重新安装依赖**
   ```bash
   cd frontend
   rm -rf node_modules package-lock.json
   npm install
   ```

2. **检查TypeScript版本**
   ```bash
   npx tsc --version
   ```
   
   确保版本 >= 5.0

3. **清理构建缓存**
   ```bash
   npm run build -- --force
   ```

---

## 🔧 高级故障排除

### 完全重置

如果所有方法都失败，尝试完全重置：

```bash
# 1. 停止所有服务
./scripts/stop-dev.sh

# 2. 清理前端
cd frontend
rm -rf node_modules .vite dist
npm cache clean --force

# 3. 清理后端
cd ../aletheia-backend
rm -rf venv __pycache__ .pytest_cache
find . -type d -name "__pycache__" -exec rm -rf {} +

# 4. 清理日志和PID文件
cd ..
rm -f runtime/logs/backend.log runtime/logs/frontend.log runtime/pids/backend.pid runtime/pids/frontend.pid

# 5. 重新配置和启动
./scripts/setup-env.sh
./scripts/start-dev.sh
```

### 启用调试模式

#### 后端调试模式

编辑 `aletheia-backend/.env`:
```env
DEBUG=True
LOG_LEVEL=DEBUG
```

#### 前端调试模式

在浏览器控制台启用详细日志:
```javascript
localStorage.setItem('debug', '*')
```

### 收集诊断信息

如果问题仍未解决，收集以下信息寻求帮助：

```bash
# 系统信息
uname -a
node --version
python3 --version
npm --version

# 服务状态
curl -v http://localhost:8000/health
curl -v http://localhost:5173

# 日志
tail -n 100 runtime/logs/backend.log
tail -n 100 runtime/logs/frontend.log

# 进程信息
ps aux | grep uvicorn
ps aux | grep node
```

## 📞 获取帮助

如果本指南无法解决您的问题：

1. 查看项目问题清单: `changes/CHANGELOG.md`
2. 查看API文档: http://localhost:8000/docs
3. 阅读设计文档: `archive/.kiro/specs/backend-frontend-integration/design.md`
4. 联系开发团队

## 💡 预防性维护

### 定期更新依赖

```bash
# 前端
cd frontend
npm update

# 后端
cd aletheia-backend
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

### 定期清理

```bash
# 清理旧日志
rm -f runtime/logs/backend.log.* runtime/logs/frontend.log.*

# 清理缓存
cd frontend && rm -rf .vite
cd aletheia-backend && find . -type d -name "__pycache__" -exec rm -rf {} +
```

### 备份配置

```bash
# 备份环境配置
cp frontend/.env frontend/.env.backup
cp aletheia-backend/.env aletheia-backend/.env.backup
```

---

**希望这个指南能帮助您解决问题！** 🛠️
