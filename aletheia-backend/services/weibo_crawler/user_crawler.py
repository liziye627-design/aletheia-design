# -*- coding: utf-8 -*-
"""
Weibo User Crawler
微博用户信息爬虫

参考: stay-leave/weibo-public-opinion-analysis

核心功能:
- 爬取用户基本信息（uid、昵称、性别、地区、生日、粉丝数、关注数）
- 支持批量爬取
- 用于水军检测特征提取
"""

import re
import time
import random
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from dateutil.parser import parse as parse_date
import aiohttp
from loguru import logger


@dataclass
class WeiboUser:
    """微博用户数据结构"""
    user_id: str = ""
    nickname: str = ""
    gender: str = ""  # 男/女/未知
    region: str = ""  # 地区
    birthday: str = ""  # 生日
    verify_type: int = 0  # 认证类型
    verify_info: str = ""  # 认证信息
    description: str = ""  # 简介
    followers_count: int = 0  # 粉丝数
    friends_count: int = 0  # 关注数
    statuses_count: int = 0  # 微博数
    register_time: Optional[datetime] = None  # 注册时间
    is_verified: bool = False  # 是否认证
    credit_level: int = 0  # 信用等级
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def calculate_bot_risk_features(self) -> Dict[str, Any]:
        """
        计算水军风险特征

        Returns:
            特征字典，可用于水军检测
        """
        features = {}

        # 粉丝关注比
        if self.friends_count > 0:
            features["follower_following_ratio"] = self.followers_count / self.friends_count
        else:
            features["follower_following_ratio"] = float(self.followers_count) if self.followers_count > 0 else 0.0

        # 账号年龄
        if self.register_time:
            age_days = (datetime.now() - self.register_time).days
            features["account_age_days"] = age_days
            features["is_new_account"] = age_days < 30
        else:
            features["account_age_days"] = None
            features["is_new_account"] = None

        # 发帖频率 (如果有账号年龄)
        if features.get("account_age_days") and features["account_age_days"] > 0:
            features["posting_frequency"] = self.statuses_count / features["account_age_days"]
        else:
            features["posting_frequency"] = None

        # 认证状态
        features["is_verified"] = self.is_verified

        # 个人资料完整度
        filled_fields = sum([
            bool(self.nickname),
            bool(self.description),
            bool(self.region),
            bool(self.gender),
        ])
        features["profile_completeness"] = filled_fields / 4.0

        return features


class WeiboUserCrawler:
    """
    微博用户信息爬虫

    使用移动端网页接口爬取用户信息
    URL格式: https://weibo.cn/{uid}/info
    """

    # 移动端用户信息页面URL
    USER_INFO_URL = "https://weibo.cn/{uid}/info"

    # 移动端用户主页URL
    USER_HOME_URL = "https://weibo.cn/u/{uid}"

    # 请求头
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(
        self,
        cookies: Optional[List[str]] = None,
        request_delay: float = 2.0,
        timeout: int = 30
    ):
        """初始化爬虫"""
        self.cookies = cookies or []
        self.request_delay = request_delay
        self.timeout = timeout
        self._cookie_index = 0
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info("WeiboUserCrawler initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self.HEADERS.copy(),
            )
        return self._session

    def _get_cookie(self) -> Optional[str]:
        """从Cookie池获取Cookie"""
        if not self.cookies:
            return None
        cookie = self.cookies[self._cookie_index]
        self._cookie_index = (self._cookie_index + 1) % len(self.cookies)
        return cookie

    async def _fetch_page(self, url: str) -> Optional[str]:
        """
        获取页面内容

        Args:
            url: 页面URL

        Returns:
            页面HTML或None
        """
        session = await self._get_session()
        headers = self.HEADERS.copy()

        cookie = self._get_cookie()
        if cookie:
            headers["Cookie"] = cookie

        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Fetch failed with status {response.status}: {url}")
        except Exception as e:
            logger.error(f"Fetch error: {e}")

        return None

    def _parse_user_info(self, html: str, user_id: str) -> WeiboUser:
        """
        解析用户信息页面

        Args:
            html: HTML文本
            user_id: 用户ID

        Returns:
            用户对象
        """
        user = WeiboUser(user_id=user_id)

        try:
            # 提取昵称
            name_match = re.search(r'昵称:(.*?)<br/>', html)
            if name_match:
                user.nickname = name_match.group(1).strip()

            # 提取性别
            gender_match = re.search(r'性别:(.*?)<br/>', html)
            if gender_match:
                gender = gender_match.group(1).strip()
                user.gender = "男" if "男" in gender else ("女" if "女" in gender else "未知")

            # 提取地区
            region_match = re.search(r'地区:(.*?)<br/>', html)
            if region_match:
                user.region = region_match.group(1).strip()

            # 提取生日
            birthday_match = re.search(r'生日:(\d{4}-\d{1,2}-\d{1,2})<br/>', html)
            if birthday_match:
                user.birthday = birthday_match.group(1)
                # 尝试计算注册时间 (假设18岁注册)
                try:
                    birth_date = datetime.strptime(user.birthday, "%Y-%m-%d")
                    # 使用生日作为注册时间估算
                    user.register_time = birth_date.replace(year=birth_date.year + 18)
                except:
                    pass

            # 提取认证信息
            verify_match = re.search(r'认证:(.*?)<br/>', html)
            if verify_match:
                user.verify_info = verify_match.group(1).strip()
                user.is_verified = bool(user.verify_info)

            # 提取简介
            desc_match = re.search(r'简介:(.*?)<br/>', html)
            if desc_match:
                user.description = desc_match.group(1).strip()

            # 提取信用等级
            credit_match = re.search(r'信用等级:(\d+)', html)
            if credit_match:
                user.credit_level = int(credit_match.group(1))

        except Exception as e:
            logger.error(f"Parse user info error: {e}")

        return user

    def _parse_user_home(self, html: str, user: WeiboUser) -> WeiboUser:
        """
        解析用户主页补充信息

        Args:
            html: HTML文本
            user: 用户对象

        Returns:
            更新后的用户对象
        """
        try:
            # 提取粉丝数
            fans_match = re.search(r'粉丝\[(\d+)\]', html)
            if fans_match:
                user.followers_count = int(fans_match.group(1))

            # 提取关注数
            follow_match = re.search(r'关注\[(\d+)\]', html)
            if follow_match:
                user.friends_count = int(follow_match.group(1))

            # 提取微博数
            weibo_match = re.search(r'微博\[(\d+)\]', html)
            if weibo_match:
                user.statuses_count = int(weibo_match.group(1))

        except Exception as e:
            logger.error(f"Parse user home error: {e}")

        return user

    async def crawl_user(self, user_id: str) -> Optional[WeiboUser]:
        """
        爬取单个用户信息

        Args:
            user_id: 用户ID

        Returns:
            用户对象或None
        """
        logger.info(f"Crawling user info for {user_id}")

        # 获取用户信息页
        info_url = self.USER_INFO_URL.format(uid=user_id)
        info_html = await self._fetch_page(info_url)

        if not info_html:
            logger.warning(f"Failed to fetch user info page for {user_id}")
            return None

        user = self._parse_user_info(info_html, user_id)

        # 延迟后获取主页补充信息
        await asyncio.sleep(self.request_delay + random.uniform(0, 1))

        home_url = self.USER_HOME_URL.format(uid=user_id)
        home_html = await self._fetch_page(home_url)

        if home_html:
            user = self._parse_user_home(home_html, user)

        logger.info(f"Successfully crawled user {user_id}: {user.nickname}")
        return user

    async def crawl_users_batch(
        self,
        user_ids: List[str]
    ) -> Dict[str, WeiboUser]:
        """
        批量爬取用户信息

        Args:
            user_ids: 用户ID列表

        Returns:
            用户ID到用户对象的映射
        """
        results = {}

        for i, user_id in enumerate(user_ids):
            # 随机延迟
            delay = self.request_delay + random.uniform(0, 1)
            if i > 0:
                await asyncio.sleep(delay)

            user = await self.crawl_user(user_id)
            if user:
                results[user_id] = user

        logger.info(f"Crawled {len(results)}/{len(user_ids)} users")
        return results

    def to_dict(self, user: WeiboUser) -> Dict[str, Any]:
        """将用户对象转换为字典"""
        return {
            "user_id": user.user_id,
            "nickname": user.nickname,
            "gender": user.gender,
            "region": user.region,
            "birthday": user.birthday,
            "verify_type": user.verify_type,
            "verify_info": user.verify_info,
            "description": user.description,
            "followers_count": user.followers_count,
            "friends_count": user.friends_count,
            "statuses_count": user.statuses_count,
            "register_time": user.register_time.isoformat() if user.register_time else None,
            "is_verified": user.is_verified,
            "credit_level": user.credit_level,
            "bot_risk_features": user.calculate_bot_risk_features(),
        }

    def to_dict_list(self, users: List[WeiboUser]) -> List[Dict[str, Any]]:
        """将用户列表转换为字典列表"""
        return [self.to_dict(u) for u in users]

    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 同步包装函数
def crawl_weibo_user_sync(
    user_id: str,
    cookies: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    同步爬取微博用户信息

    Args:
        user_id: 用户ID
        cookies: Cookie列表

    Returns:
        用户信息字典或None
    """
    async def _crawl():
        async with WeiboUserCrawler(cookies=cookies) as crawler:
            user = await crawler.crawl_user(user_id)
            return crawler.to_dict(user) if user else None

    return asyncio.run(_crawl())