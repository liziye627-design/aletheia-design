# Aletheia 快速启动指南

## 🚀 三步启动

### 1. 配置环境

```bash
./scripts/setup-env.sh
```

编辑 `aletheia-backend/.env`，添加至少一个LLM API Key：
```env
SILICONFLOW_API_KEY=your_key_here
```

### 2. 启动服务

```bash
./scripts/start-dev.sh
```

### 3. 访问应用

- **前端**: http://localhost:5173
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

## 🛑 停止服务

```bash
./scripts/stop-dev.sh
```

## 📚 完整文档

- [集成指南](INTEGRATION_GUIDE.md) - 详细的配置和使用说明
- [故障排除](TROUBLESHOOTING.md) - 常见问题解决方案

## 🔍 验证集成

```bash
# 测试API连通性
cd scripts
npx ts-node test-api-connectivity.ts

# 验证API端点
npx ts-node verify-api-endpoints.ts
```

## 💡 常见问题

**Q: 后端启动失败？**
A: 确保已配置LLM API Key，查看 `runtime/logs/backend.log`

**Q: 前端无法连接后端？**
A: 检查CORS配置，确认后端在8000端口运行

**Q: 端口被占用？**
A: 修改 `scripts/start-dev.sh` 中的端口配置

---

**需要帮助？** 查看 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
