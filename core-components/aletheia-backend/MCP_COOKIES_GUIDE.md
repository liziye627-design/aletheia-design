# MCP工具 - Cookies/Tokens 获取完整指南

本文档说明如何使用 **MCP (Model Context Protocol) 工具** 获取所有爬虫所需的 cookies、tokens 和 API keys。

---

## 目录

- [浏览器MCP工具基础](#浏览器mcp工具基础)
- [社交媒体平台](#社交媒体平台)
  - [微博 (Weibo)](#微博-weibo)
  - [Twitter/X](#twitterx)
  - [小红书 (Xiaohongshu)](#小红书-xiaohongshu)
  - [抖音 (Douyin)](#抖音-douyin)
  - [知乎 (Zhihu)](#知乎-zhihu)
  - [B站 (Bilibili)](#b站-bilibili)
  - [快手 (Kuaishou)](#快手-kuaishou)
  - [豆瓣 (Douban)](#豆瓣-douban)
  - [Reddit](#reddit)
- [社区论坛](#社区论坛)
  - [GitHub](#github)
  - [Stack Overflow](#stack-overflow)
- [学术数据集](#学术数据集)
  - [OpenAlex](#openalex)

---

## 浏览器MCP工具基础

### 可用的MCP工具

1. **Playwright Browser MCP** (推荐)
   - 支持自动化浏览器操作
   - 可提取cookies、LocalStorage、SessionStorage
   - 支持JavaScript执行

2. **Puppeteer MCP**
   - 类似Playwright，基于Chrome DevTools Protocol
   - 提供类似功能

### 通用获取流程

```python
# 使用Playwright MCP示例
from mcp import playwright_browser_navigate, playwright_browser_evaluate

# 1. 导航到登录页面
await playwright_browser_navigate("https://example.com/login")

# 2. 手动登录或自动填充
# (可通过浏览器手动操作，或使用fill_form工具)

# 3. 提取cookies
cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="获取cookies"
)

# 4. 提取LocalStorage (如果需要)
local_storage = await playwright_browser_evaluate(
    function="() => JSON.stringify(localStorage)",
    element="获取LocalStorage"
)
```

---

## 社交媒体平台

### 微博 (Weibo)

**所需凭证**: `weibo_cookies`

**获取步骤**:

```python
# 1. 导航到微博登录页
await playwright_browser_navigate("https://weibo.com/login.php")

# 2. 手动登录 (扫码或账号密码)
# 等待登录完成...

# 3. 提取cookies
weibo_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="微博cookies"
)

# 4. 保存到环境变量
# WEIBO_COOKIES="{weibo_cookies}"
```

**重要Cookies字段**:
- `SUB`: 用户身份令牌 (最重要)
- `SUBP`: 权限令牌
- `_T_WM`: 移动端令牌

---

### Twitter/X

**所需凭证**: `twitter_bearer_token`

**方法1: 使用Twitter Developer Portal (推荐)**

```bash
# 1. 访问 https://developer.twitter.com/en/portal/dashboard
# 2. 创建App → Keys and Tokens → 生成 Bearer Token
# 3. 复制 Bearer Token

# TWITTER_BEARER_TOKEN="AAAAAAAAAAAAAAAAAAAAAxxxxxxxxx..."
```

**方法2: 从浏览器提取 (高级用户)**

```python
# 1. 登录 https://twitter.com
await playwright_browser_navigate("https://twitter.com")

# 2. 打开DevTools Network标签，查找API请求
# 找到 Authorization Header 中的 Bearer Token

# 3. 使用MCP执行JS提取
bearer_token = await playwright_browser_evaluate(
    function="""() => {
        // 从网络请求中提取Authorization header
        // 注意: 这需要在有API请求时执行
        return 'Bearer Token提取需查看Network请求';
    }""",
    element="Twitter Bearer Token"
)
```

---

### 小红书 (Xiaohongshu)

**所需凭证**: `xhs_cookies`

**获取步骤**:

```python
# 1. 导航到小红书
await playwright_browser_navigate("https://www.xiaohongshu.com")

# 2. 手动登录 (微信/手机号)

# 3. 提取cookies
xhs_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="小红书cookies"
)

# XHS_COOKIES="{xhs_cookies}"
```

**重要Cookies字段**:
- `web_session`: 会话令牌
- `a1`: 设备识别

---

### 抖音 (Douyin)

**所需凭证**: `douyin_cookies`

**获取步骤**:

```python
# 1. 导航到抖音网页版
await playwright_browser_navigate("https://www.douyin.com")

# 2. 扫码登录

# 3. 提取cookies
douyin_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="抖音cookies"
)

# DOUYIN_COOKIES="{douyin_cookies}"
```

**重要Cookies字段**:
- `sessionid`: 会话ID
- `odin_tt`: 设备指纹

---

### 知乎 (Zhihu)

**所需凭证**: `zhihu_cookies`

**获取步骤**:

```python
# 1. 导航到知乎
await playwright_browser_navigate("https://www.zhihu.com")

# 2. 登录

# 3. 提取cookies
zhihu_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="知乎cookies"
)

# ZHIHU_COOKIES="{zhihu_cookies}"
```

**重要Cookies字段**:
- `z_c0`: 用户令牌 (最重要)
- `_zap`: 分析令牌

---

### B站 (Bilibili)

**所需凭证**: `bilibili_cookies`

**获取步骤**:

```python
# 1. 导航到B站
await playwright_browser_navigate("https://www.bilibili.com")

# 2. 扫码登录

# 3. 提取cookies
bilibili_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="B站cookies"
)

# BILIBILI_COOKIES="{bilibili_cookies}"
```

**重要Cookies字段**:
- `SESSDATA`: 会话数据 (最重要)
- `bili_jct`: CSRF令牌
- `DedeUserID`: 用户ID

---

### 快手 (Kuaishou)

**所需凭证**: `kuaishou_cookies`

**获取步骤**:

```python
# 1. 导航到快手网页版
await playwright_browser_navigate("https://www.kuaishou.com")

# 2. 登录

# 3. 提取cookies
kuaishou_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="快手cookies"
)

# KUAISHOU_COOKIES="{kuaishou_cookies}"
```

---

### 豆瓣 (Douban)

**所需凭证**: `douban_cookies`

**获取步骤**:

```python
# 1. 导航到豆瓣
await playwright_browser_navigate("https://www.douban.com")

# 2. 登录

# 3. 提取cookies
douban_cookies = await playwright_browser_evaluate(
    function="() => document.cookie",
    element="豆瓣cookies"
)

# DOUBAN_COOKIES="{douban_cookies}"
```

**重要Cookies字段**:
- `dbcl2`: 登录凭证
- `bid`: 浏览器ID

---

### Reddit

**所需凭证**: `reddit_client_id`, `reddit_client_secret`

**方法: 使用Reddit App申请**

```bash
# 1. 访问 https://www.reddit.com/prefs/apps
# 2. 点击 "Create App" 或 "Create Another App"
# 3. 填写信息:
#    - Name: Aletheia Crawler
#    - App type: script
#    - Redirect URI: http://localhost:8080
# 4. 点击 "Create app"
# 5. 记录:
#    - Client ID (在app名称下方)
#    - Client Secret (点击显示)

# REDDIT_CLIENT_ID="xxxxxxxxxxxx"
# REDDIT_CLIENT_SECRET="yyyyyyyyyyyyyyyyyyyy"
```

---

## 社区论坛

### GitHub

**所需凭证**: `github_token` (可选，但建议提供以提高速率限制)

**方法: 生成Personal Access Token**

```bash
# 1. 访问 GitHub 账号令牌管理页（settings/tokens）
# 2. 点击 "Generate new token" → "Generate new token (classic)"
# 3. 填写信息:
#    - Note: Aletheia Crawler
#    - Expiration: 选择有效期
#    - Scopes: 勾选 public_repo (仅需公开仓库访问权限)
# 4. 点击 "Generate token"
# 5. 复制token (只显示一次!)

# GITHUB_TOKEN="your_github_token_here"
```

**速率限制对比**:
- 无token: 60 请求/小时
- 有token: 5000 请求/小时

---

### Stack Overflow

**所需凭证**: `stackoverflow_api_key` (可选)

**方法: 注册Stack Apps**

```bash
# 1. 访问 https://stackapps.com/apps/oauth/register
# 2. 填写信息:
#    - Application Name: Aletheia Crawler
#    - OAuth Domain: localhost
# 3. 提交后获得 API Key

# STACKOVERFLOW_API_KEY="xxxxxxxxxxxxxxxx"
```

**注意**: Stack Overflow API有每日配额限制，建议注册key以提高限制。

---

## 学术数据集

### OpenAlex

**所需凭证**: `openalex_email` (可选，但强烈建议提供)

**方法: 提供邮箱**

```bash
# OpenAlex是完全免费的API，不需要注册
# 但建议在请求中提供邮箱，以获得更高速率限制

# OPENALEX_EMAIL="your.email@example.com"
```

**速率限制对比**:
- 无邮箱: 10 请求/秒
- 有邮箱 (在User-Agent中): 100 请求/秒

**使用示例**:
```bash
# 爬虫会自动在User-Agent中添加邮箱:
# User-Agent: Aletheia/1.0 (mailto:your.email@example.com)
```

---

## 环境变量配置示例

创建 `.env` 文件 (位于 `aletheia-backend/docker/.env`):

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

## 使用MCP工具的完整示例

### 示例1: 自动获取微博Cookies

```python
from mcp import (
    playwright_browser_navigate,
    playwright_browser_snapshot,
    playwright_browser_fill_form,
    playwright_browser_evaluate,
)

async def get_weibo_cookies():
    """使用MCP自动获取微博cookies"""
    
    # 1. 导航到微博登录页
    await playwright_browser_navigate("https://weibo.com/login.php")
    
    # 2. 等待页面加载
    await playwright_browser_snapshot()
    
    # 3. 这里可以手动登录，或使用fill_form自动填充
    # (扫码登录需要手动操作)
    
    # 4. 登录成功后，提取cookies
    cookies = await playwright_browser_evaluate(
        function="() => document.cookie",
        element="微博cookies"
    )
    
    print(f"获得Cookies: {cookies}")
    return cookies
```

### 示例2: 批量获取多平台Cookies

```python
async def batch_get_cookies():
    """批量获取多个平台的cookies"""
    
    platforms = [
        ("weibo", "https://weibo.com/login.php"),
        ("zhihu", "https://www.zhihu.com"),
        ("bilibili", "https://www.bilibili.com"),
    ]
    
    cookies_dict = {}
    
    for platform, url in platforms:
        print(f"正在获取 {platform} cookies...")
        
        # 导航
        await playwright_browser_navigate(url)
        
        # 等待手动登录
        input(f"请在浏览器中登录{platform}，完成后按回车...")
        
        # 提取cookies
        cookies = await playwright_browser_evaluate(
            function="() => document.cookie",
            element=f"{platform} cookies"
        )
        
        cookies_dict[platform] = cookies
        print(f"✅ {platform} cookies获取成功\n")
    
    return cookies_dict
```

---

## 安全注意事项

### ⚠️ Cookies安全

1. **永远不要提交cookies到版本控制**
   ```bash
   # 确保.env在.gitignore中
   echo ".env" >> .gitignore
   ```

2. **定期更新cookies** (大部分cookies有有效期)

3. **使用环境变量** 而不是硬编码

4. **限制cookies权限** (如使用只读账号)

### 🔐 API Keys安全

1. **使用密钥管理服务** (如AWS Secrets Manager, HashiCorp Vault)

2. **设置IP白名单** (如GitHub token可限制IP)

3. **最小权限原则** (只申请必需的权限)

---

## 故障排查

### Cookies失效

**症状**: 返回401 Unauthorized或登录页面

**解决方案**:
1. 重新登录并提取新cookies
2. 检查cookies是否被URL编码
3. 确保包含所有必需字段 (见上文"重要Cookies字段")

### 速率限制

**症状**: 返回429 Too Many Requests

**解决方案**:
1. 提供API Key/Token以提高限制
2. 使用爬虫内置的速率限制器 (已在EnhancedBaseCrawler中实现)
3. 降低爬取频率

### MCP工具无法提取Cookies

**解决方案**:
1. 确保已登录成功 (检查浏览器状态)
2. 尝试手动复制 (F12 → Application → Cookies)
3. 使用浏览器扩展 (如EditThisCookie)

---

## 联系支持

如果遇到任何问题，请:

1. 查看 [爬虫优化指南](./CRAWLER_OPTIMIZATION_GUIDE.md)
2. 检查日志输出 (爬虫会记录详细错误信息)
3. 提交Issue到项目仓库

---

**最后更新**: 2026-02-03  
**维护者**: Aletheia团队
