"""
基准线建立模块 - 为实体建立"正常状态"基准
"""

import uuid
from typing import Dict, Any, List, Optional, Sequence
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from models.database.intel import Intel, Baseline
from utils.logging import logger


class BaselineManager:
    """基准线管理器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def establish_baseline(
        self,
        entity_id: str,
        entity_name: str,
        entity_type: str = "brand",
        time_window_days: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        为实体建立基准线

        Args:
            entity_id: 实体ID
            entity_name: 实体名称
            entity_type: 实体类型(brand/person/event)
            time_window_days: 时间窗口(天)

        Returns:
            基准线数据
        """
        logger.info(
            f"📊 Establishing baseline for {entity_name} (window={time_window_days}days)"
        )

        # 1. 查询时间窗口内的所有相关数据
        cutoff_date = datetime.utcnow() - timedelta(days=time_window_days)

        query = select(Intel).where(
            Intel.content_text.contains(entity_name),
            Intel.created_at >= cutoff_date,
            Intel.is_archived == 0,
        )

        result = await self.db.execute(query)
        intels = result.scalars().all()

        if len(intels) < 10:  # 数据太少,无法建立有效基准
            logger.warning(f"⚠️ Not enough data for {entity_name} ({len(intels)} items)")
            return None

        # 2. 计算统计基准
        daily_mentions = self._calculate_daily_mentions(intels, time_window_days)

        # 3. 情感分布(这里简化,实际需要情感分析模型)
        sentiment_distribution = self._analyze_sentiment_distribution(intels)

        # 4. 账号类型分布
        account_distribution = self._analyze_account_types(intels)

        # 5. 地理分布(如果有GPS数据)
        geo_distribution = self._analyze_geographic_distribution(intels)

        # 6. 构建基准线对象
        baseline_data = {
            "id": f"baseline_{uuid.uuid4().hex[:12]}",
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "daily_mention_avg": daily_mentions["avg"],
            "daily_mention_std": daily_mentions["std"],
            "sentiment_distribution": sentiment_distribution,
            "account_type_distribution": account_distribution,
            "geographic_distribution": geo_distribution,
            "time_window_days": time_window_days,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # 7. 保存到数据库
        baseline = Baseline(**baseline_data)
        self.db.add(baseline)
        await self.db.commit()

        logger.info(
            f"✅ Baseline established for {entity_name}: avg={daily_mentions['avg']:.1f} mentions/day"
        )

        return baseline_data

    def _calculate_daily_mentions(
        self, intels: Sequence[Intel], time_window_days: int
    ) -> Dict[str, float]:
        """计算日均提及量"""
        # 在统计窗口内按天分组，缺失日期按0计入，避免均值/方差被高估
        mentions_by_day = {}

        for intel in intels:
            day = intel.created_at.date()
            mentions_by_day[day] = mentions_by_day.get(day, 0) + 1

        if not mentions_by_day:
            return {"avg": 0.0, "std": 0.0}

        latest_day = max(mentions_by_day)
        mention_counts = [
            mentions_by_day.get(latest_day - timedelta(days=offset), 0)
            for offset in range(time_window_days)
        ]

        if not mention_counts:
            return {"avg": 0.0, "std": 0.0}

        avg = np.mean(mention_counts)
        std = np.std(mention_counts)

        return {"avg": float(avg), "std": float(std)}

    def _analyze_sentiment_distribution(
        self, intels: Sequence[Intel]
    ) -> Dict[str, float]:
        """
        分析情感分布

        TODO: 接入真实的情感分析模型
        现在使用简化逻辑: 根据关键词判断
        """
        positive_keywords = ["好", "棒", "赞", "优秀", "成功", "喜欢"]
        negative_keywords = ["差", "烂", "垃圾", "失败", "讨厌", "问题"]

        positive_count = 0
        negative_count = 0
        neutral_count = 0

        for intel in intels:
            text = intel.content_text.lower()

            has_positive = any(kw in text for kw in positive_keywords)
            has_negative = any(kw in text for kw in negative_keywords)

            if has_positive and not has_negative:
                positive_count += 1
            elif has_negative and not has_positive:
                negative_count += 1
            else:
                neutral_count += 1

        total = len(intels) or 1

        return {
            "positive": round(positive_count / total, 3),
            "neutral": round(neutral_count / total, 3),
            "negative": round(negative_count / total, 3),
        }

    def _analyze_account_types(self, intels: Sequence[Intel]) -> Dict[str, float]:
        """分析账号类型分布"""
        verified_count = 0
        influencer_count = 0
        ordinary_count = 0

        for intel in intels:
            follower_count = intel.meta.get("author_follower_count", 0)

            # 简化逻辑判断账号类型
            if follower_count > 100000:
                verified_count += 1
            elif follower_count > 10000:
                influencer_count += 1
            else:
                ordinary_count += 1

        total = len(intels) or 1

        return {
            "verified_media": round(verified_count / total, 3),
            "influencers": round(influencer_count / total, 3),
            "ordinary_users": round(ordinary_count / total, 3),
        }

    def _analyze_geographic_distribution(
        self, intels: Sequence[Intel]
    ) -> Optional[Dict[str, float]]:
        """分析地理分布"""
        # 如果元数据中有地理位置信息
        location_counts = {}

        for intel in intels:
            location = intel.meta.get("ip_location")
            if location:
                location_counts[location] = location_counts.get(location, 0) + 1

        if not location_counts:
            return None

        total = sum(location_counts.values())

        return {loc: round(count / total, 3) for loc, count in location_counts.items()}

    async def get_baseline(self, entity_id: str) -> Optional[Baseline]:
        """获取实体的基准线"""
        query = select(Baseline).where(Baseline.entity_id == entity_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_baseline(
        self, entity_id: str, entity_name: str, time_window_days: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        更新基准线(重新计算)

        建议: 每周自动更新一次
        """
        logger.info(f"🔄 Updating baseline for {entity_name}")

        # 删除旧的基准线
        existing = await self.get_baseline(entity_id)
        if existing:
            await self.db.delete(existing)
            await self.db.commit()

        # 重新建立
        return await self.establish_baseline(
            entity_id=entity_id,
            entity_name=entity_name,
            time_window_days=time_window_days,
        )
