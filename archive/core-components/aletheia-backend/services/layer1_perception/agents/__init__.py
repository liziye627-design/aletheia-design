"""
Agents模块 - 智能浏览器Agent

提供基于浏览器自动化的智能数据采集能力,
无需cookies或API keys,完全模拟真实用户行为。

可用Agents:
- BrowserAgent: 浏览器基础Agent
- BilibiliAgent: B站专用Agent
- DouyinAgent: 抖音专用Agent
- XiaohongshuAgent: 小红书专用Agent
- ZhihuAgent: 知乎专用Agent
- ConcurrentAgentManager: 并发Agent管理器
"""

from .browser_agent import BrowserAgent
from .bilibili_agent import BilibiliAgent
from .douyin_agent import DouyinAgent
from .xiaohongshu_agent import XiaohongshuAgent
from .zhihu_agent import ZhihuAgent
from .concurrent_manager import ConcurrentAgentManager, concurrent_search_all_platforms

__all__ = [
    "BrowserAgent",
    "BilibiliAgent",
    "DouyinAgent",
    "XiaohongshuAgent",
    "ZhihuAgent",
    "ConcurrentAgentManager",
    "concurrent_search_all_platforms",
]
