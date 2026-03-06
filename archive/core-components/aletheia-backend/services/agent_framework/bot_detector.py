"""
Aletheia Bot Detection
======================

水军/僵尸粉检测工具

检测维度：
1. 账号画像特征（注册时间、粉丝关注比）
2. 行为模式（发布频率、互动模式）
3. 内容特征（重复度、模板化）
4. 社交图谱异常
"""

import re
import math
import hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import Counter
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Import core data models
from models.dataclasses import Account, Post, BotScore, BotFeatures, Platform


@dataclass
class AccountProfile:
    """账号画像"""

    user_id: str
    nickname: str = ""
    platform: str = ""

    # 账号信息
    register_time: Optional[datetime] = None
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0

    # 认证信息
    is_verified: bool = False
    verify_type: str = ""  # personal, enterprise, official

    # 额外元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentItem:
    """内容项"""

    content_id: str
    user_id: str
    text: str = ""
    publish_time: Optional[datetime] = None

    # 互动数据
    likes: int = 0
    comments: int = 0
    shares: int = 0

    # 媒体
    has_image: bool = False
    has_video: bool = False


@dataclass
class BotDetectionResult:
    """水军检测结果"""

    user_id: str
    is_suspicious: bool = False
    risk_score: float = 0.0  # 0-1
    risk_level: str = "low"  # low, medium, high

    # 各维度评分
    profile_score: float = 0.0
    behavior_score: float = 0.0
    content_score: float = 0.0
    social_score: float = 0.0

    # 检测到的特征
    detected_features: List[str] = field(default_factory=list)

    # 建议
    recommendation: str = ""


class BotDetector:
    """
    水军检测器

    基于多维度特征识别可疑账号
    """

    # 风险阈值
    RISK_THRESHOLDS = {"low": 0.3, "medium": 0.6, "high": 0.8}

    def __init__(self):
        """初始化检测器"""
        logger.info("BotDetector 已初始化")
    
    def analyze_account(
        self,
        account: Account,
        posts: Optional[List[Post]] = None
    ) -> BotScore:
        """
        Analyze an account and return bot probability score with feature breakdown.
        
        This is the primary method for bot detection that works with core data models.
        
        Args:
            account: Account object from core data models
            posts: Optional list of Post objects from the account
            
        Returns:
            BotScore object with bot probability (0-1) and feature breakdown
        """
        posts = posts or []
        
        # Convert Account to AccountProfile for internal processing
        profile = AccountProfile(
            user_id=account.account_id,
            nickname=account.username,
            platform=account.platform.value if isinstance(account.platform, Platform) else account.platform,
            register_time=account.created_at,
            follower_count=account.follower_count,
            following_count=account.following_count,
            post_count=account.post_count,
            is_verified=account.verified,
            verify_type="verified" if account.verified else "",
            metadata={
                "bio": account.bio,
                "location": account.location,
                "profile_image_url": account.profile_image_url,
                **account.metadata
            }
        )
        
        # Convert Posts to ContentItems for internal processing
        contents = []
        for post in posts:
            content = ContentItem(
                content_id=post.post_id,
                user_id=account.account_id,
                text=post.content,
                publish_time=post.created_at,
                likes=post.like_count,
                comments=post.comment_count,
                shares=post.share_count,
                has_image=len(post.media_urls) > 0,
                has_video=False  # Could be enhanced with content_type check
            )
            contents.append(content)
        
        # Calculate all features
        features_dict = self.calculate_features(profile, contents)
        
        # Create BotFeatures object
        bot_features = BotFeatures(
            account_age_days=features_dict["account_age_days"],
            posting_frequency=features_dict["posting_frequency"],
            interaction_ratio=features_dict["interaction_ratio"],
            content_similarity=features_dict["content_similarity"],
            profile_completeness=features_dict["profile_completeness"],
            temporal_entropy=features_dict["temporal_entropy"],
            follower_following_ratio=features_dict["follower_following_ratio"],
            verified_status=features_dict["verified_status"]
        )
        
        # Calculate bot probability using the existing detect method
        detection_result = self.detect(profile, contents)
        
        # Determine confidence based on data availability
        confidence = "HIGH"
        if len(posts) < 5:
            confidence = "LOW"
        elif len(posts) < 20:
            confidence = "MEDIUM"
        
        # Create and return BotScore
        bot_score = BotScore(
            account_id=account.account_id,
            platform=account.platform if isinstance(account.platform, Platform) else Platform(account.platform),
            bot_probability=detection_result.risk_score,
            features=bot_features,
            confidence=confidence,
            detected_at=datetime.utcnow(),
            model_version="1.0",
            metadata={
                "risk_level": detection_result.risk_level,
                "detected_features": detection_result.detected_features,
                "recommendation": detection_result.recommendation
            }
        )
        
        return bot_score
    
    def calculate_features(
        self,
        profile: AccountProfile,
        contents: List[ContentItem] = None
    ) -> Dict[str, Any]:
        """
        Calculate bot detection features for an account.
        
        Args:
            profile: Account profile data
            contents: List of content items posted by the account
            
        Returns:
            Dictionary containing all calculated features:
            - account_age_days: Age of account in days
            - posting_frequency: Posts per day
            - interaction_ratio: (likes + comments) / posts
            - content_similarity: Average similarity between posts (0-1)
            - profile_completeness: How complete the profile is (0-1)
            - temporal_entropy: Entropy of posting time distribution
            - follower_following_ratio: Follower to following ratio
            - verified_status: Whether account is verified
        """
        contents = contents or []
        
        # 1. Account age in days
        account_age_days = 0.0
        if profile.register_time:
            account_age_days = (datetime.now() - profile.register_time).days
            # Ensure non-negative
            account_age_days = max(0.0, account_age_days)
        
        # 2. Posting frequency (posts per day)
        posting_frequency = 0.0
        if account_age_days > 0:
            posting_frequency = profile.post_count / account_age_days
        elif profile.post_count > 0:
            # If no register time but has posts, assume 1 day
            posting_frequency = float(profile.post_count)
        
        # 3. Interaction ratio
        interaction_ratio = 0.0
        if len(contents) > 0:
            total_interactions = sum(c.likes + c.comments for c in contents)
            interaction_ratio = total_interactions / len(contents)
        
        # 4. Content similarity using TF-IDF
        content_similarity = self._calculate_content_similarity(contents)
        
        # 5. Profile completeness
        profile_completeness = self._calculate_profile_completeness(profile)
        
        # 6. Temporal pattern entropy
        temporal_entropy = self._calculate_temporal_entropy(contents)
        
        # 7. Follower/following ratio
        follower_following_ratio = 0.0
        if profile.following_count > 0:
            follower_following_ratio = profile.follower_count / profile.following_count
        elif profile.follower_count > 0:
            # If following is 0 but has followers, set to a high value
            follower_following_ratio = float(profile.follower_count)
        
        # 8. Verified status
        verified_status = profile.is_verified
        
        return {
            "account_age_days": account_age_days,
            "posting_frequency": posting_frequency,
            "interaction_ratio": interaction_ratio,
            "content_similarity": content_similarity,
            "profile_completeness": profile_completeness,
            "temporal_entropy": temporal_entropy,
            "follower_following_ratio": follower_following_ratio,
            "verified_status": verified_status
        }
    
    def _calculate_content_similarity(self, contents: List[ContentItem]) -> float:
        """
        Calculate average content similarity using TF-IDF and cosine similarity.
        
        Args:
            contents: List of content items
            
        Returns:
            Average pairwise similarity score (0-1)
        """
        if len(contents) < 2:
            return 0.0
        
        # Extract text content
        texts = [c.text for c in contents if c.text and len(c.text.strip()) > 0]
        
        if len(texts) < 2:
            return 0.0
        
        try:
            # Create a new vectorizer for each call to avoid state issues
            vectorizer = TfidfVectorizer(
                max_features=100,
                ngram_range=(1, 2),
                min_df=1,  # Minimum document frequency
                max_df=1.0,  # Maximum document frequency (allow all)
                lowercase=True,
                strip_accents='unicode'
            )
            
            # Calculate TF-IDF vectors
            tfidf_matrix = vectorizer.fit_transform(texts)
            
            # Calculate pairwise cosine similarities
            similarities = cosine_similarity(tfidf_matrix)
            
            # Get upper triangle (excluding diagonal) to avoid counting same pairs twice
            n = len(texts)
            similarity_sum = 0.0
            pair_count = 0
            
            for i in range(n):
                for j in range(i + 1, n):
                    similarity_sum += similarities[i][j]
                    pair_count += 1
            
            if pair_count > 0:
                avg_similarity = similarity_sum / pair_count
                # Ensure result is in [0, 1]
                return max(0.0, min(1.0, float(avg_similarity)))
            
            return 0.0
            
        except Exception as e:
            logger.warning(f"Error calculating content similarity: {e}")
            return 0.0
    
    def _calculate_profile_completeness(self, profile: AccountProfile) -> float:
        """
        Calculate how complete the profile is (0-1).
        
        Args:
            profile: Account profile
            
        Returns:
            Completeness score (0-1)
        """
        # Check which fields are filled
        fields_to_check = [
            profile.nickname,
            profile.verify_type,
            profile.metadata.get("bio"),
            profile.metadata.get("location"),
            profile.metadata.get("profile_image_url"),
        ]
        
        filled_count = sum(1 for field in fields_to_check if field)
        total_fields = len(fields_to_check)
        
        if total_fields == 0:
            return 0.0
        
        return filled_count / total_fields
    
    def _calculate_temporal_entropy(self, contents: List[ContentItem]) -> float:
        """
        Calculate entropy of posting time distribution.
        Higher entropy indicates more random/natural posting patterns.
        Lower entropy indicates mechanical/scheduled posting.
        
        Args:
            contents: List of content items
            
        Returns:
            Entropy value (0 to ~4.58 for 24 hours)
        """
        if len(contents) < 2:
            return 0.0
        
        # Extract posting hours
        posting_hours = []
        for content in contents:
            if content.publish_time:
                posting_hours.append(content.publish_time.hour)
        
        if len(posting_hours) < 2:
            return 0.0
        
        # Count frequency of each hour
        hour_counts = Counter(posting_hours)
        total_posts = len(posting_hours)
        
        # Calculate entropy: -sum(p * log2(p))
        entropy = 0.0
        for count in hour_counts.values():
            if count > 0:
                probability = count / total_posts
                entropy -= probability * math.log2(probability)
        
        # Ensure non-negative
        return max(0.0, entropy)

    def detect(
        self,
        profile: AccountProfile,
        contents: List[ContentItem] = None,
        related_accounts: List[AccountProfile] = None,
    ) -> BotDetectionResult:
        """
        检测账号是否为水军

        Args:
            profile: 账号画像
            contents: 发布内容列表
            related_accounts: 相关账号列表（用于社交图谱分析）

        Returns:
            检测结果
        """
        contents = contents or []
        
        # Calculate all features using the new method
        features = self.calculate_features(profile, contents)

        # 各维度检测
        profile_result = self._check_profile(profile)
        behavior_result = self._check_behavior(profile, contents)
        content_result = self._check_content(contents)
        social_result = self._check_social(profile, related_accounts or [])

        # 计算综合风险分
        weights = {"profile": 0.3, "behavior": 0.3, "content": 0.25, "social": 0.15}

        total_score = (
            profile_result["score"] * weights["profile"]
            + behavior_result["score"] * weights["behavior"]
            + content_result["score"] * weights["content"]
            + social_result["score"] * weights["social"]
        )
        
        # Ensure total_score is within [0, 1] range
        total_score = max(0.0, min(1.0, total_score))

        # 确定风险等级
        risk_level = "low"
        if total_score >= self.RISK_THRESHOLDS["high"]:
            risk_level = "high"
        elif total_score >= self.RISK_THRESHOLDS["medium"]:
            risk_level = "medium"

        # 合并特征
        all_features = (
            profile_result["features"]
            + behavior_result["features"]
            + content_result["features"]
            + social_result["features"]
        )

        # 生成建议
        recommendation = self._generate_recommendation(
            total_score, risk_level, all_features
        )

        return BotDetectionResult(
            user_id=profile.user_id,
            is_suspicious=total_score >= self.RISK_THRESHOLDS["medium"],
            risk_score=round(total_score, 4),
            risk_level=risk_level,
            profile_score=round(profile_result["score"], 4),
            behavior_score=round(behavior_result["score"], 4),
            content_score=round(content_result["score"], 4),
            social_score=round(social_result["score"], 4),
            detected_features=all_features,
            recommendation=recommendation,
        )

    def batch_detect(
        self, accounts_data: List[Dict[str, Any]]
    ) -> List[BotDetectionResult]:
        """
        批量检测

        Args:
            accounts_data: 账号数据列表

        Returns:
            检测结果列表
        """
        results = []

        for data in accounts_data:
            # 构建账号画像
            profile = AccountProfile(
                user_id=data.get("user_id", ""),
                nickname=data.get("nickname", ""),
                platform=data.get("platform", ""),
                follower_count=data.get("follower_count", 0),
                following_count=data.get("following_count", 0),
                post_count=data.get("post_count", 0),
                is_verified=data.get("is_verified", False),
                verify_type=data.get("verify_type", ""),
                metadata=data.get("metadata", {}),
            )

            # 解析注册时间
            if "register_time" in data:
                try:
                    profile.register_time = datetime.fromisoformat(
                        data["register_time"].replace("Z", "+00:00")
                    )
                except:
                    pass

            # 构建内容列表
            contents = []
            for content_data in data.get("contents", []):
                content = ContentItem(
                    content_id=content_data.get("content_id", ""),
                    user_id=profile.user_id,
                    text=content_data.get("text", ""),
                    likes=content_data.get("likes", 0),
                    comments=content_data.get("comments", 0),
                    shares=content_data.get("shares", 0),
                    has_image=content_data.get("has_image", False),
                    has_video=content_data.get("has_video", False),
                )

                if "publish_time" in content_data:
                    try:
                        content.publish_time = datetime.fromisoformat(
                            content_data["publish_time"].replace("Z", "+00:00")
                        )
                    except:
                        pass

                contents.append(content)

            result = self.detect(profile, contents)
            results.append(result)

        return results

    def _check_profile(self, profile: AccountProfile) -> Dict:
        """检测账号画像特征"""
        score = 0.0
        features = []

        # 1. 检查粉丝关注比
        if profile.following_count > 0:
            ratio = profile.follower_count / profile.following_count
            if ratio < 0.1:  # 关注多，粉丝少
                score += 0.3
                features.append("粉丝关注比异常低 (< 0.1)")
            elif ratio > 10:  # 粉丝多，关注少（可能是大V）
                score -= 0.1

        # 2. 检查是否认证
        if not profile.is_verified:
            score += 0.1
            features.append("未认证账号")

        # 3. 检查注册时间
        if profile.register_time:
            account_age_days = (datetime.now() - profile.register_time).days
            if account_age_days < 30:  # 新账号
                score += 0.25
                features.append("新注册账号 (< 30天)")
            elif account_age_days > 365 * 2:  # 老账号
                score -= 0.1

        # 4. 检查发帖量
        if profile.post_count == 0:
            score += 0.2
            features.append("从未发帖")
        elif profile.post_count > 1000:  # 发帖过多
            score += 0.15
            features.append("发帖量异常 (> 1000)")

        return {"score": max(0.0, min(score, 1.0)), "features": features}

    def _check_behavior(
        self, profile: AccountProfile, contents: List[ContentItem]
    ) -> Dict:
        """检测行为模式"""
        score = 0.0
        features = []

        if not contents:
            return {"score": 0.0, "features": []}

        # 1. 检查发布频率
        if len(contents) >= 2:
            publish_times = [c.publish_time for c in contents if c.publish_time]
            publish_times.sort()

            if len(publish_times) >= 2:
                # 计算平均发布间隔
                intervals = []
                for i in range(1, len(publish_times)):
                    interval = (publish_times[i] - publish_times[i - 1]).total_seconds()
                    intervals.append(interval)

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)

                    # 如果平均间隔太短（小于5分钟），可能是机器发帖
                    if avg_interval < 300:  # 5分钟
                        score += 0.35
                        features.append("发帖频率异常高 (平均 < 5分钟)")
                    elif avg_interval < 900:  # 15分钟
                        score += 0.2
                        features.append("发帖频率较高 (平均 < 15分钟)")

        # 2. 检查互动模式
        total_likes = sum(c.likes for c in contents)
        total_comments = sum(c.comments for c in contents)

        if len(contents) > 0:
            avg_likes = total_likes / len(contents)
            avg_comments = total_comments / len(contents)

            # 如果发帖多但互动少
            if len(contents) > 10 and avg_likes < 1:
                score += 0.25
                features.append("发帖多但无互动")

        # 3. 检查发布时间规律性（机器账号常在固定时间发帖）
        if len(contents) >= 3:
            publish_hours = [c.publish_time.hour for c in contents if c.publish_time]
            if publish_hours:
                hour_counter = Counter(publish_hours)
                most_common_hour, count = hour_counter.most_common(1)[0]

                # 如果大部分帖子在同一小时发布
                if count / len(publish_hours) > 0.7:
                    score += 0.2
                    features.append("发帖时间高度集中")

        return {"score": max(0.0, min(score, 1.0)), "features": features}

    def _check_content(self, contents: List[ContentItem]) -> Dict:
        """检测内容特征"""
        score = 0.0
        features = []

        if not contents:
            return {"score": 0.0, "features": []}

        texts = [c.text for c in contents if c.text]
        if not texts:
            return {"score": 0.0, "features": []}

        # 1. 检查内容重复度
        unique_texts = set(texts)
        if len(texts) > 1:
            duplication_rate = 1 - (len(unique_texts) / len(texts))
            if duplication_rate > 0.5:  # 超过50%重复
                score += 0.4
                features.append(f"内容重复度极高 ({duplication_rate:.0%})")
            elif duplication_rate > 0.3:
                score += 0.2
                features.append(f"内容重复度较高 ({duplication_rate:.0%})")

        # 2. 检查模板化内容
        template_patterns = [
            r"^【.+】",  # 【标题】开头
            r"#\w+",  # 过多话题标签
            r"https?://\S+",  # 大量链接
        ]

        template_count = 0
        for text in texts:
            for pattern in template_patterns:
                if re.search(pattern, text):
                    template_count += 1
                    break

        if len(texts) > 0:
            template_rate = template_count / len(texts)
            if template_rate > 0.8:
                score += 0.25
                features.append("内容高度模板化")

        # 3. 检查内容长度
        short_count = sum(1 for t in texts if len(t) < 20)
        if len(texts) > 0:
            short_rate = short_count / len(texts)
            if short_rate > 0.7:
                score += 0.15
                features.append("大量短内容")

        return {"score": max(0.0, min(score, 1.0)), "features": features}

    def _check_social(
        self, profile: AccountProfile, related_accounts: List[AccountProfile]
    ) -> Dict:
        """检测社交图谱特征"""
        score = 0.0
        features = []

        # 这里可以实现更复杂的社交图谱分析
        # 例如：检测互相关注集群、粉丝来源集中度等

        # 简单检查：如果关注列表中有很多可疑账号
        # 实际实现需要更多数据

        return {"score": max(0.0, min(score, 1.0)), "features": features}

    def _generate_recommendation(
        self, score: float, level: str, features: List[str]
    ) -> str:
        """生成检测建议"""
        if level == "high":
            return "该账号存在多项水军特征，建议：1) 标记为可疑账号；2) 降低其内容权重；3) 进一步人工审核。"
        elif level == "medium":
            return "该账号存在部分可疑特征，建议：1) 加强监控；2) 分析其互动内容质量；3) 观察后续行为。"
        else:
            return "该账号暂无明显水军特征，建议正常处理。"

    def analyze_content_quality(self, contents: List[ContentItem]) -> Dict[str, Any]:
        """
        分析内容质量

        用于评估账号发布内容的真实价值
        """
        if not contents:
            return {
                "total_content": 0,
                "avg_length": 0,
                "originality_score": 0.0,
                "engagement_score": 0.0,
                "quality_label": "unknown",
            }

        texts = [c.text for c in contents if c.text]

        # 平均长度
        avg_length = sum(len(t) for t in texts) / len(texts) if texts else 0

        # 原创度（简单计算：不重复内容占比）
        unique_ratio = len(set(texts)) / len(texts) if texts else 0

        # 互动分
        total_engagement = sum(
            c.likes + c.comments * 2 + c.shares * 3 for c in contents
        )
        engagement_score = min(total_engagement / (len(contents) * 10), 1.0)

        # 质量标签
        if unique_ratio > 0.8 and avg_length > 50:
            quality_label = "high"
        elif unique_ratio > 0.5 and avg_length > 20:
            quality_label = "medium"
        else:
            quality_label = "low"

        return {
            "total_content": len(contents),
            "avg_length": round(avg_length, 1),
            "originality_score": round(unique_ratio, 2),
            "engagement_score": round(engagement_score, 2),
            "quality_label": quality_label,
        }


# 便捷函数
def detect_bot(
    user_id: str,
    follower_count: int = 0,
    following_count: int = 0,
    post_count: int = 0,
    is_verified: bool = False,
    contents: List[Dict] = None,
) -> BotDetectionResult:
    """
    便捷函数：检测单个账号

    Args:
        user_id: 用户ID
        follower_count: 粉丝数
        following_count: 关注数
        post_count: 发帖数
        is_verified: 是否认证
        contents: 内容列表

    Returns:
        检测结果
    """
    detector = BotDetector()

    profile = AccountProfile(
        user_id=user_id,
        follower_count=follower_count,
        following_count=following_count,
        post_count=post_count,
        is_verified=is_verified,
    )

    content_items = []
    if contents:
        for c in contents:
            content_items.append(
                ContentItem(
                    content_id=c.get("id", ""),
                    user_id=user_id,
                    text=c.get("text", ""),
                    likes=c.get("likes", 0),
                    comments=c.get("comments", 0),
                    shares=c.get("shares", 0),
                )
            )

    return detector.detect(profile, content_items)


def batch_detect_bots(accounts: List[Dict]) -> List[BotDetectionResult]:
    """
    便捷函数：批量检测

    Args:
        accounts: 账号数据列表

    Returns:
        检测结果列表
    """
    detector = BotDetector()
    return detector.batch_detect(accounts)
