# 🔑 快速凭证获取指南

本指南提供两种方式获取所有平台凭证：
1. **自动化脚本** (推荐)
2. **手动获取** (备选)

---

## 方式1: 自动化脚本 (推荐) 🤖

### 安装依赖

```bash
cd aletheia-backend
pip install selenium webdriver-manager
```

### 运行脚本

```bash
python get_all_credentials.py
```

### 脚本功能

✅ **自动打开浏览器**  
✅ **逐个平台引导登录**  
✅ **自动提取cookies**  
✅ **自动保存到 `.env` 文件**  
✅ **生成备份JSON**

### 工作流程

1. 脚本会自动打开Chrome浏览器
2. 依次导航到各个平台登录页
3. 你在浏览器中完成登录（扫码或密码）
4. 登录成功后按回车，脚本自动提取cookies
5. 重复步骤2-4，直到所有平台完成
6. 最后自动保存到 `docker/.env`

---

## 方式2: 手动获取 📝

如果自动化脚本遇到问题，可以手动获取凭证。

### 准备工作

1. 打开Chrome浏览器
2. 按 `F12` 打开开发者工具
3. 切换到 **Application** 标签 → **Cookies**

---

## 📱 社交媒体平台 (需要Cookies)

### 1. 微博 (Weibo)

**步骤**:
```
1. 访问: https://weibo.com
2. 登录 (扫码或密码)
3. F12 → Application → Cookies → https://weibo.com
4. 复制所有cookies (Ctrl+A → Ctrl+C)
5. 转换为字符串格式: "SUB=xxx; SUBP=yyy; _T_WM=zzz"
```

**重要字段**: `SUB`, `SUBP`, `_T_WM`

---

### 2. 小红书 (Xiaohongshu)

**步骤**:
```
1. 访问: https://www.xiaohongshu.com
2. 登录 (微信/手机号)
3. F12 → Application → Cookies
4. 重点复制: web_session, a1
```

---

### 3. 抖音 (Douyin)

**步骤**:
```
1. 访问: https://www.douyin.com
2. 扫码登录
3. F12 → Application → Cookies
4. 重点复制: sessionid, odin_tt
```

---

### 4. 知乎 (Zhihu)

**步骤**:
```
1. 访问: https://www.zhihu.com
2. 登录
3. F12 → Application → Cookies
4. 重点复制: z_c0, _zap
```

---

### 5. B站 (Bilibili)

**步骤**:
```
1. 访问: https://www.bilibili.com
2. 扫码登录
3. F12 → Application → Cookies
4. 重点复制: SESSDATA, bili_jct, DedeUserID
```

---

### 6. 快手 (Kuaishou)

**步骤**:
```
1. 访问: https://www.kuaishou.com
2. 登录
3. F12 → Application → Cookies
```

---

### 7. 豆瓣 (Douban)

**步骤**:
```
1. 访问: https://www.douban.com
2. 登录
3. F12 → Application → Cookies
4. 重点复制: dbcl2, bid
```

---

## 🔐 API凭证 (需要开发者申请)

### 8. Twitter/X Bearer Token

**步骤**:
```
1. 访问: https://developer.twitter.com/en/portal/dashboard
2. 登录Twitter账号
3. 创建App (如果没有)
4. 进入 Keys and Tokens 标签
5. 点击 "Generate" 获取 Bearer Token
6. 复制: AAAAAAAAAAAAAAAAAAAAAxxxxxxxxx
```

**速率限制**: 
- 基础: 300 请求/15分钟
- 高级: 900 请求/15分钟

---

### 9. Reddit API

**步骤**:
```
1. 访问: https://www.reddit.com/prefs/apps
2. 点击 "Create App"
3. 填写:
   - Name: Aletheia Crawler
   - App type: script
   - Redirect URI: http://localhost:8080
4. 记录:
   - Client ID (14位字符)
   - Client Secret (27位字符)
```

---

### 10. GitHub Personal Access Token

**步骤**:
```
1. 访问: GitHub 账号令牌管理页（settings/tokens）
2. 点击 "Generate new token (classic)"
3. 填写:
   - Note: Aletheia Crawler
   - Expiration: 90 days (或更长)
   - Scopes: 勾选 public_repo
4. 点击 "Generate token"
5. 复制: your_github_token_here
```

**速率限制**:
- 无token: 60 请求/小时
- 有token: 5000 请求/小时

---

### 11. Stack Overflow API Key (可选)

**步骤**:
```
1. 访问: https://stackapps.com/apps/oauth/register
2. 填写:
   - Application Name: Aletheia Crawler
   - OAuth Domain: localhost
3. 提交后获得 API Key
```

**注意**: Stack Overflow API即使没有key也可以使用，但有速率限制。

---

### 12. OpenAlex 邮箱 (强烈建议)

**步骤**:
```
直接提供你的邮箱即可，无需注册！
例如: your.email@example.com
```

**速率限制**:
- 无邮箱: 10 请求/秒
- 有邮箱: 100 请求/秒

---

## 💾 保存凭证

### 方式A: 使用自动化脚本

自动化脚本会自动保存，无需手动操作。

### 方式B: 手动创建 .env 文件

创建或编辑 `aletheia-backend/docker/.env`:

```bash
# ==================== 社交媒体平台 ====================
WEIBO_COOKIES="SUB=_2A25xxx; SUBP=xxx; _T_WM=xxx"
TWITTER_BEARER_TOKEN="AAAAAAAAAAAAAAAAAAAAAxxxxxxxxx"
XHS_COOKIES="web_session=xxx; a1=xxx"
DOUYIN_COOKIES="sessionid=xxx; odin_tt=xxx"
ZHIHU_COOKIES="z_c0=xxx; _zap=xxx"
BILIBILI_COOKIES="SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx"
KUAISHOU_COOKIES="kuaishou.login.token=xxx"
DOUBAN_COOKIES="dbcl2=xxx; bid=xxx"

# ==================== Reddit ====================
REDDIT_CLIENT_ID="xxxxxxxxxxxx"
REDDIT_CLIENT_SECRET="yyyyyyyyyyyyyyyyyyyy"

# ==================== 社区论坛 ====================
GITHUB_TOKEN="your_github_token_here"
STACKOVERFLOW_API_KEY="xxxxxxxxxxxxxxxx"

# ==================== 学术数据集 ====================
OPENALEX_EMAIL="your.email@example.com"
```

---

## ⚡ 快捷提取Cookies方法

### Chrome浏览器

**方法1: 使用开发者工具**
```
1. F12 → Application → Cookies
2. 全选 → 复制
3. 格式化为: "name1=value1; name2=value2"
```

**方法2: 使用扩展 (更方便)**

安装扩展: **EditThisCookie** 或 **Cookie-Editor**

```
1. 登录目标网站
2. 点击扩展图标
3. 点击 "Export" → 复制
```

### Firefox浏览器

```
1. F12 → Storage → Cookies
2. 复制需要的cookies
```

---

## 🔒 安全注意事项

### ⚠️ 重要提醒

1. **永远不要分享你的cookies/tokens**
2. **不要提交 `.env` 文件到Git**
3. **定期更新cookies** (大部分有效期30-90天)
4. **使用环境变量**，不要硬编码

### 确保 .gitignore 包含

```
# 确保这些在 .gitignore 中
.env
*.env
credentials_backup.json
```

---

## 🧪 验证凭证

创建测试脚本 `test_credentials.py`:

```python
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv("docker/.env")

# 检查所有凭证
credentials = {
    "WEIBO_COOKIES": os.getenv("WEIBO_COOKIES"),
    "TWITTER_BEARER_TOKEN": os.getenv("TWITTER_BEARER_TOKEN"),
    "XHS_COOKIES": os.getenv("XHS_COOKIES"),
    "DOUYIN_COOKIES": os.getenv("DOUYIN_COOKIES"),
    "ZHIHU_COOKIES": os.getenv("ZHIHU_COOKIES"),
    "BILIBILI_COOKIES": os.getenv("BILIBILI_COOKIES"),
    "KUAISHOU_COOKIES": os.getenv("KUAISHOU_COOKIES"),
    "DOUBAN_COOKIES": os.getenv("DOUBAN_COOKIES"),
    "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
    "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
    "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN"),
    "STACKOVERFLOW_API_KEY": os.getenv("STACKOVERFLOW_API_KEY"),
    "OPENALEX_EMAIL": os.getenv("OPENALEX_EMAIL"),
}

print("🔍 凭证检查结果:\n")
for key, value in credentials.items():
    status = "✅" if value else "❌"
    preview = f"{value[:50]}..." if value else "未设置"
    print(f"{status} {key:30} {preview}")

total = len(credentials)
set_count = sum(1 for v in credentials.values() if v)
print(f"\n📊 总计: {set_count}/{total} 个凭证已配置")
```

运行验证:

```bash
python test_credentials.py
```

---

## 🚀 使用凭证

凭证配置完成后，运行:

```bash
# 测试爬虫系统
cd aletheia-backend
python test_crawler_integration.py
```

---

## ❓ 常见问题

### Q1: Cookies多久会过期？

**A**: 
- 微博/知乎/B站: 约30-90天
- 小红书/抖音: 约7-30天
- 豆瓣: 较长，约1年

建议每月更新一次。

### Q2: 如何知道cookies失效了？

**A**: 爬虫会返回401 Unauthorized或重定向到登录页。此时需要重新登录获取新cookies。

### Q3: API Key和Bearer Token的区别？

**A**:
- **API Key**: 通常用于标识应用身份（如Stack Overflow）
- **Bearer Token**: 用于OAuth 2.0认证（如Twitter）
- **Personal Access Token**: 用于代替密码的长期凭证（如GitHub）

### Q4: 为什么需要这么多凭证？

**A**: 不同平台有不同的认证机制：
- **国内平台**: 主要使用cookies认证（简单但需登录）
- **国际平台**: 主要使用API tokens（更安全，速率限制更高）

---

## 📞 获取帮助

如遇到问题:

1. 查看 `MCP_COOKIES_GUIDE.md` (完整MCP工具指南)
2. 运行 `python get_all_credentials.py` (自动化脚本)
3. 参考本文档的手动步骤
4. 检查浏览器控制台错误

---

**最后更新**: 2026-02-03  
**维护者**: Aletheia团队

🎉 **祝你成功获取所有凭证！**
