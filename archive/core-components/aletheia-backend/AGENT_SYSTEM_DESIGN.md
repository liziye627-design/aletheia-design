# 🤖 Aletheia Agent-based 超级搜索系统设计文档

## 概述

**设计理念**: 让Agent拥有"手"、"眼"、"脑"，能够像人类一样浏览和理解网页。

### 核心能力

1. **👁️ 视觉感知** - 能"看懂"网页（截图、OCR、视觉理解）
2. **🧠 智能决策** - 能"思考"下一步做什么（LLM推理）
3. **🖐️ 自主操作** - 能"操作"浏览器（点击、输入、滚动）
4. **🎯 任务规划** - 能"规划"多步骤任务
5. **🔄 自我纠错** - 能"调整"策略应对异常

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Aletheia 混合采集系统                      │
└─────────────────────────────────────────────────────────────┘
           │                              │
           │                              │
    ┌──────▼──────┐              ┌────────▼────────┐
    │ API爬虫层   │              │  Agent采集层    │
    │ (现有系统)  │              │  (新增系统)     │
    └──────┬──────┘              └────────┬────────┘
           │                              │
  ┌────────┴────────┐          ┌──────────┴──────────┐
  │                 │          │                     │
  │ • 官方API       │          │ • BrowserAgent      │
  │ • RSS订阅       │          │ • VisionAgent       │
  │ • Cookies认证   │          │ • SearchAgent       │
  │                 │          │ • PlatformAgent     │
  └─────────────────┘          └─────────────────────┘
           │                              │
           │                              │
           └──────────┬───────────────────┘
                      │
              ┌───────▼────────┐
              │  统一数据输出   │
              │  (标准化格式)   │
              └────────────────┘
```

---

## 组件详解

### 1. BrowserAgent (浏览器Agent)

**职责**: 浏览器自动化控制的基础类

**能力**:
- ✅ 启动/关闭浏览器
- ✅ 导航到URL
- ✅ 执行JavaScript
- ✅ 获取页面快照
- ✅ 模拟人类行为（随机延迟、鼠标轨迹）

**技术栈**:
- Playwright (浏览器自动化)
- Chrome DevTools Protocol

**示例**:
```python
class BrowserAgent:
    async def navigate(self, url: str):
        """导航到URL"""
        await self.page.goto(url)
        await self.random_delay()  # 模拟人类
    
    async def screenshot(self) -> bytes:
        """截图当前页面"""
        return await self.page.screenshot()
```

---

### 2. VisionAgent (视觉Agent)

**职责**: 理解网页视觉内容

**能力**:
- ✅ 网页截图分析
- ✅ 元素识别（按钮、输入框、链接）
- ✅ OCR文字识别
- ✅ 布局理解
- ✅ 内容提取

**技术栈**:
- Claude Vision API (多模态LLM)
- GPT-4 Vision
- Tesseract OCR (备选)

**示例**:
```python
class VisionAgent(BrowserAgent):
    async def understand_page(self) -> Dict:
        """理解当前页面"""
        screenshot = await self.screenshot()
        
        # 使用Claude Vision分析
        analysis = await self.llm.analyze_image(
            image=screenshot,
            prompt="""
            分析这个网页截图:
            1. 识别所有可交互元素（按钮、输入框、链接）
            2. 提取主要内容
            3. 判断页面类型（搜索页/列表页/详情页）
            4. 建议下一步操作
            """
        )
        
        return analysis
```

---

### 3. SearchAgent (搜索Agent)

**职责**: 智能网页搜索与信息提取

**能力**:
- ✅ 自动找到搜索框
- ✅ 输入搜索关键词
- ✅ 处理搜索结果
- ✅ 翻页获取更多结果
- ✅ 智能过滤无关信息

**工作流程**:
```
1. 进入目标网站
2. 视觉识别搜索框位置
3. 输入关键词
4. 等待结果加载
5. 提取结果列表
6. 判断是否需要翻页
7. 标准化输出
```

**示例**:
```python
class SearchAgent(VisionAgent):
    async def search(self, website: str, keyword: str) -> List[Dict]:
        """在任意网站搜索"""
        
        # 1. 导航到网站
        await self.navigate(website)
        
        # 2. 使用视觉识别找到搜索框
        search_box = await self.find_search_box()
        
        # 3. 输入关键词
        await search_box.type(keyword)
        await search_box.press("Enter")
        
        # 4. 等待结果加载
        await self.wait_for_content()
        
        # 5. 提取结果
        results = await self.extract_results()
        
        return results
    
    async def find_search_box(self):
        """智能找到搜索框"""
        # 方法1: 视觉识别
        screenshot = await self.screenshot()
        elements = await self.vision_llm.find_elements(
            screenshot, 
            "搜索框或搜索按钮"
        )
        
        # 方法2: DOM分析
        candidates = await self.page.query_selector_all(
            'input[type="text"], input[type="search"]'
        )
        
        # 方法3: LLM决策选择最佳候选
        best_element = await self.llm.select_best(
            candidates, 
            "最可能是搜索框的元素"
        )
        
        return best_element
```

---

### 4. PlatformAgent (平台专用Agent)

**职责**: 针对特定平台优化的Agent

**平台**:
- BilibiliAgent (B站)
- DouyinAgent (抖音)
- XiaohongshuAgent (小红书)
- ZhihuAgent (知乎)

**特点**:
- 了解平台特定布局
- 处理平台特殊交互（下拉加载、无限滚动）
- 绕过反爬虫（模拟真实用户行为）

**示例 - BilibiliAgent**:
```python
class BilibiliAgent(SearchAgent):
    """B站专用Agent"""
    
    SEARCH_URL = "https://search.bilibili.com/all"
    
    async def search_videos(self, keyword: str, limit: int = 20):
        """搜索B站视频"""
        
        # 1. 导航到搜索页
        await self.navigate(f"{self.SEARCH_URL}?keyword={keyword}")
        
        # 2. 等待视频卡片加载
        await self.page.wait_for_selector('.video-list')
        
        # 3. 模拟滚动加载更多
        results = []
        while len(results) < limit:
            # 滚动一屏
            await self.scroll_one_page()
            await self.random_delay(1, 3)
            
            # 提取新视频
            new_videos = await self.extract_video_cards()
            results.extend(new_videos)
        
        return results[:limit]
    
    async def extract_video_cards(self):
        """提取视频卡片信息"""
        cards = await self.page.query_selector_all('.video-item')
        
        videos = []
        for card in cards:
            video = {
                "title": await card.query_selector('.title').inner_text(),
                "author": await card.query_selector('.up-name').inner_text(),
                "views": await card.query_selector('.view').inner_text(),
                "url": await card.query_selector('a').get_attribute('href'),
            }
            videos.append(video)
        
        return videos
```

---

## 核心优势

### vs 传统爬虫

| 特性 | 传统爬虫 | Agent-based |
|------|---------|-------------|
| **需要API/Cookies** | ✅ 是 | ❌ 否 |
| **处理动态内容** | ⚠️ 困难 | ✅ 轻松 |
| **适应页面变化** | ❌ 需要更新代码 | ✅ 自动适应 |
| **处理验证码** | ❌ 无法处理 | ✅ 可请求人工 |
| **模拟真人行为** | ⚠️ 有限 | ✅ 完全模拟 |
| **开发速度** | ⚠️ 每个平台单独开发 | ✅ 通用框架 |

---

## 技术实现

### 关键技术

1. **Playwright** - 浏览器自动化
   - 支持Chrome、Firefox、WebKit
   - 完整的浏览器功能
   - 反检测能力

2. **Claude Vision / GPT-4V** - 视觉理解
   - 多模态输入（文本+图像）
   - 上下文理解
   - 行动建议

3. **LangChain** - Agent框架
   - 工具调用
   - 记忆管理
   - 任务规划

4. **BeautifulSoup + Playwright** - 混合解析
   - DOM解析
   - 动态内容处理

---

## 工作流示例

### 场景: 在B站搜索"人工智能"

```python
# 1. 初始化Agent
agent = BilibiliAgent(
    llm=Claude(),
    vision_model=ClaudeVision()
)

# 2. 执行搜索任务
results = await agent.execute_task(
    task="在B站搜索'人工智能'相关视频，获取前20个结果",
    steps=[
        "导航到B站",
        "找到搜索框",
        "输入关键词",
        "等待结果加载",
        "滚动获取更多结果",
        "提取视频信息",
        "标准化输出"
    ]
)

# 3. Agent自主执行
# - 视觉识别搜索框位置
# - LLM决策最佳操作
# - 模拟真人行为（随机延迟、鼠标轨迹）
# - 自动处理异常（加载失败、元素变化）
# - 提取并标准化数据

# 4. 输出结果
for video in results:
    print(f"{video['title']} - {video['author']}")
```

---

## 混合模式架构

### 智能路由

```python
class HybridCrawlerManager:
    """混合爬虫管理器"""
    
    def __init__(self):
        # 传统爬虫
        self.api_crawlers = CrawlerManager()
        
        # Agent爬虫
        self.agents = {
            "bilibili": BilibiliAgent(),
            "douyin": DouyinAgent(),
            "xiaohongshu": XiaohongshuAgent(),
        }
    
    async def fetch(self, platform: str, **kwargs):
        """智能选择采集方式"""
        
        # 优先使用API（速度快、稳定）
        if platform in self.api_crawlers.crawlers:
            try:
                return await self.api_crawlers.crawlers[platform].fetch(**kwargs)
            except AuthError:
                # API失败，降级到Agent
                pass
        
        # 使用Agent（无需认证、适应性强）
        if platform in self.agents:
            return await self.agents[platform].search(**kwargs)
        
        # 通用Agent（兜底）
        return await self.generic_agent.search(
            website=PLATFORM_URLS[platform],
            **kwargs
        )
```

---

## 反检测策略

### 人类行为模拟

```python
class HumanBehaviorMixin:
    """人类行为模拟"""
    
    async def random_delay(self, min_sec=0.5, max_sec=2.0):
        """随机延迟"""
        await asyncio.sleep(random.uniform(min_sec, max_sec))
    
    async def human_mouse_move(self, x, y):
        """人类鼠标轨迹"""
        # 贝塞尔曲线移动
        path = self.generate_bezier_curve(
            current_pos, 
            target_pos=(x, y)
        )
        
        for point in path:
            await self.page.mouse.move(point.x, point.y)
            await self.random_delay(0.01, 0.05)
    
    async def human_scroll(self, distance):
        """人类滚动模式"""
        # 分段滚动，模拟阅读
        segments = self.split_scroll(distance)
        
        for segment in segments:
            await self.page.mouse.wheel(0, segment)
            await self.random_delay(0.3, 1.0)  # 阅读停顿
```

---

## 开发计划

### Phase 1: 基础框架 (1周)
- [x] BrowserAgent基础类
- [ ] VisionAgent视觉能力
- [ ] LLM决策引擎
- [ ] 基础工具函数

### Phase 2: 搜索能力 (1周)
- [ ] SearchAgent通用搜索
- [ ] 智能元素识别
- [ ] 结果提取标准化
- [ ] 翻页处理

### Phase 3: 平台Agent (2周)
- [ ] BilibiliAgent
- [ ] DouyinAgent
- [ ] XiaohongshuAgent
- [ ] ZhihuAgent

### Phase 4: 混合集成 (1周)
- [ ] HybridCrawlerManager
- [ ] 智能路由
- [ ] 统一API接口
- [ ] 性能优化

---

## 成本分析

### LLM调用成本

| 操作 | 频率 | Token消耗 | 成本/次 |
|------|------|-----------|---------|
| **视觉理解** | 每页1次 | ~1000 tokens | $0.01 |
| **决策规划** | 每步1次 | ~500 tokens | $0.005 |
| **元素识别** | 按需 | ~300 tokens | $0.003 |

**单次搜索成本**: ~$0.05 (获取20条结果)  
**对比API成本**: 免费 (无需API key)

### 性能对比

| 指标 | API爬虫 | Agent爬虫 |
|------|---------|-----------|
| **速度** | ⚡ 快 (1-2秒) | ⏱️ 中等 (5-10秒) |
| **成功率** | 依赖认证 | 95%+ |
| **适应性** | 低 | 高 |
| **维护成本** | 高 | 低 |

---

## 安全与合规

### 合规性

✅ **完全合法** - Agent模拟真实用户浏览  
✅ **尊重robots.txt** - 可配置遵守规则  
✅ **速率限制** - 内置延迟，避免过载  
✅ **用户协议** - 仅用于公开信息

### 使用限制

⚠️ **不用于**:
- 绕过付费墙
- 批量注册账号
- DDoS攻击
- 窃取私密信息

---

## 下一步

1. **实现BrowserAgent基础类**
2. **集成Claude Vision**
3. **开发BilibiliAgent原型**
4. **测试反检测能力**
5. **集成到现有系统**

---

**设计者**: Aletheia Team  
**版本**: 1.0  
**日期**: 2026-02-03
