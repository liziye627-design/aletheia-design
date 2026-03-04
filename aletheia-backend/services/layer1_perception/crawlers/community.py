"""
社区/论坛爬虫
支持: GitHub Events, Stack Overflow, Quora(limited)
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .enhanced_base import EnhancedBaseCrawler
from utils.logging import logger


class GitHubEventsCrawler(EnhancedBaseCrawler):
    """GitHub公开事件爬虫"""

    def __init__(self, access_token: Optional[str] = None):
        """
        初始化GitHub Events爬虫

        Args:
            access_token: GitHub Personal Access Token (可选,提升限额)
        """
        super().__init__(
            platform_name="github_events",
            rate_limit=5,  # GitHub API限制较严
            max_retries=3,
        )
        self.access_token = access_token
        self.api_base = "https://api.github.com"

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取GitHub公开事件

        Args:
            limit: 返回数量限制

        Returns:
            标准化事件列表
        """
        try:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            response = await self._make_request(
                url=f"{self.api_base}/events",
                headers=headers,
            )

            results = []
            for event in response[:limit] if isinstance(response, list) else []:
                raw_data = {
                    "url": event.get("repo", {}).get("url", ""),
                    "text": self._format_event(event),
                    "created_at": event.get(
                        "created_at", datetime.utcnow().isoformat()
                    ),
                    "author_name": event.get("actor", {}).get("login", ""),
                    "author_id": str(event.get("actor", {}).get("id", "")),
                    "followers": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "entities": [event.get("type", "")],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["source_type"] = "community"
                standardized["metadata"]["event_type"] = event.get("type")
                results.append(standardized)

            logger.info(f"✅ GitHub Events: fetched {len(results)} events")
            return results

        except Exception as e:
            logger.error(f"❌ GitHub Events fetch error: {e}")
            return []

    def _format_event(self, event: Dict[str, Any]) -> str:
        """格式化GitHub事件为文本"""
        event_type = event.get("type", "")
        actor = event.get("actor", {}).get("login", "")
        repo = event.get("repo", {}).get("name", "")

        if event_type == "PushEvent":
            commits = len(event.get("payload", {}).get("commits", []))
            return f"{actor} pushed {commits} commits to {repo}"
        elif event_type == "IssuesEvent":
            action = event.get("payload", {}).get("action", "")
            title = event.get("payload", {}).get("issue", {}).get("title", "")
            return f"{actor} {action} issue in {repo}: {title}"
        elif event_type == "PullRequestEvent":
            action = event.get("payload", {}).get("action", "")
            title = event.get("payload", {}).get("pull_request", {}).get("title", "")
            return f"{actor} {action} pull request in {repo}: {title}"
        else:
            return f"{actor} {event_type} in {repo}"

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """抓取用户公开事件"""
        try:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            response = await self._make_request(
                url=f"{self.api_base}/users/{user_id}/events/public",
                headers=headers,
            )

            results = []
            for event in response[:limit] if isinstance(response, list) else []:
                raw_data = {
                    "url": event.get("repo", {}).get("url", ""),
                    "text": self._format_event(event),
                    "created_at": event.get(
                        "created_at", datetime.utcnow().isoformat()
                    ),
                    "author_name": user_id,
                    "author_id": user_id,
                    "followers": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "entities": [event.get("type", "")],
                }
                results.append(self.standardize_item(raw_data))

            logger.info(
                f"✅ GitHub User Events: fetched {len(results)} events for {user_id}"
            )
            return results

        except Exception as e:
            logger.error(f"❌ GitHub User Events fetch error: {e}")
            return []

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """GitHub不直接支持通过事件ID获取评论"""
        logger.warning("GitHub Events does not support comments by event ID")
        return []


class StackOverflowCrawler(EnhancedBaseCrawler):
    """Stack Overflow公开数据爬虫"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化Stack Overflow爬虫

        Args:
            api_key: Stack Exchange API Key (可选,提升限额)
        """
        super().__init__(
            platform_name="stackoverflow",
            rate_limit=5,  # Stack Exchange API限制
            max_retries=3,
        )
        self.api_key = api_key
        self.api_base = "https://api.stackexchange.com/2.3"

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取Stack Overflow热门问题

        Args:
            limit: 返回数量限制

        Returns:
            标准化问题列表
        """
        try:
            params = {
                "order": "desc",
                "sort": "hot",
                "site": "stackoverflow",
                "pagesize": min(limit, 100),
            }
            if self.api_key:
                params["key"] = self.api_key

            response = await self._make_request(
                url=f"{self.api_base}/questions",
                params=params,
            )

            results = []
            for question in response.get("items", []):
                raw_data = {
                    "url": question.get("link", ""),
                    "text": f"{question.get('title', '')}\n{question.get('body_markdown', '')}",
                    "created_at": datetime.fromtimestamp(
                        question.get("creation_date", 0)
                    ).isoformat(),
                    "author_name": question.get("owner", {}).get("display_name", ""),
                    "author_id": str(question.get("owner", {}).get("user_id", "")),
                    "followers": question.get("owner", {}).get("reputation", 0),
                    "likes": question.get("score", 0),
                    "comments": question.get("answer_count", 0),
                    "shares": question.get("view_count", 0),
                    "entities": question.get("tags", []),
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["source_type"] = "qa_community"
                standardized["metadata"]["is_answered"] = question.get(
                    "is_answered", False
                )
                results.append(standardized)

            logger.info(f"✅ Stack Overflow: fetched {len(results)} questions")
            return results

        except Exception as e:
            logger.error(f"❌ Stack Overflow fetch error: {e}")
            return []

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """抓取用户问题"""
        try:
            params = {
                "order": "desc",
                "sort": "activity",
                "site": "stackoverflow",
                "pagesize": min(limit, 100),
            }
            if self.api_key:
                params["key"] = self.api_key

            response = await self._make_request(
                url=f"{self.api_base}/users/{user_id}/questions",
                params=params,
            )

            results = []
            for question in response.get("items", []):
                raw_data = {
                    "url": question.get("link", ""),
                    "text": question.get("title", ""),
                    "created_at": datetime.fromtimestamp(
                        question.get("creation_date", 0)
                    ).isoformat(),
                    "author_name": user_id,
                    "author_id": user_id,
                    "followers": 0,
                    "likes": question.get("score", 0),
                    "comments": question.get("answer_count", 0),
                    "shares": question.get("view_count", 0),
                    "entities": question.get("tags", []),
                }
                results.append(self.standardize_item(raw_data))

            logger.info(
                f"✅ Stack Overflow User: fetched {len(results)} questions for {user_id}"
            )
            return results

        except Exception as e:
            logger.error(f"❌ Stack Overflow User fetch error: {e}")
            return []

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """抓取问题评论/回答"""
        try:
            params = {
                "order": "desc",
                "sort": "votes",
                "site": "stackoverflow",
                "pagesize": min(limit, 100),
            }
            if self.api_key:
                params["key"] = self.api_key

            response = await self._make_request(
                url=f"{self.api_base}/questions/{post_id}/answers",
                params=params,
            )

            results = []
            for answer in response.get("items", []):
                raw_data = {
                    "url": f"https://stackoverflow.com/a/{answer.get('answer_id')}",
                    "text": answer.get("body_markdown", ""),
                    "created_at": datetime.fromtimestamp(
                        answer.get("creation_date", 0)
                    ).isoformat(),
                    "author_name": answer.get("owner", {}).get("display_name", ""),
                    "author_id": str(answer.get("owner", {}).get("user_id", "")),
                    "followers": 0,
                    "likes": answer.get("score", 0),
                    "comments": 0,
                    "shares": 0,
                    "entities": [],
                }
                results.append(self.standardize_item(raw_data))

            logger.info(
                f"✅ Stack Overflow Answers: fetched {len(results)} answers for {post_id}"
            )
            return results

        except Exception as e:
            logger.error(f"❌ Stack Overflow Answers fetch error: {e}")
            return []


class QuoraCrawler(EnhancedBaseCrawler):
    """Quora爬虫(有限支持,官方API受限)"""

    def __init__(self):
        """初始化Quora爬虫"""
        super().__init__(
            platform_name="quora",
            rate_limit=2,  # 保守限频
            max_retries=2,
        )
        logger.warning(
            "⚠️ Quora official API is very limited. This is a placeholder implementation."
        )

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Quora官方API非常受限,暂不支持"""
        logger.warning("Quora does not provide public API for hot topics")
        return []

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Quora官方API非常受限,暂不支持"""
        logger.warning("Quora does not provide public API for user posts")
        return []

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Quora官方API非常受限,暂不支持"""
        logger.warning("Quora does not provide public API for comments")
        return []
