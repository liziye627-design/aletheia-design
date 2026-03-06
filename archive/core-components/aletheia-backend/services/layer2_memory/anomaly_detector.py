"""
异常检测模块 - 检测舆情异常信号
"""

from typing import Dict, Any, List, Optional, Sequence
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from models.database.intel import Intel, Baseline
from services.layer2_memory.baseline import BaselineManager
from utils.logging import logger


class AnomalyDetector:
    """异常检测器"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.baseline_manager = BaselineManager(db)

    async def detect_anomaly(
        self, entity_id: str, entity_name: str, time_window_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """
        检测实体的异常信号

        Args:
            entity_id: 实体ID
            entity_name: 实体名称
            time_window_hours: 检测时间窗口(小时)

        Returns:
            异常检测结果
        """
        logger.info(f"🔍 Detecting anomalies for {entity_name}")

        # 1. 获取基准线
        baseline = await self.baseline_manager.get_baseline(entity_id)

        if not baseline:
            logger.warning(f"⚠️ No baseline found for {entity_name}, creating one...")
            await self.baseline_manager.establish_baseline(
                entity_id=entity_id, entity_name=entity_name
            )
            return None  # 首次建立基准,暂无历史对比

        # 2. 获取当前时间窗口的数据
        cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)

        query = select(Intel).where(
            Intel.content_text.contains(entity_name),
            Intel.created_at >= cutoff_time,
            Intel.is_archived == 0,
        )

        result = await self.db.execute(query)
        current_intels = result.scalars().all()

        if not current_intels:
            logger.info(f"ℹ️ No recent data for {entity_name}")
            return None

        # 3. 计算当前状态
        current_state = self._calculate_current_state(current_intels, time_window_hours)

        # 4. 与基准线对比,识别异常
        anomalies = self._compare_with_baseline(
            current_state=current_state, baseline=baseline, entity_name=entity_name
        )

        if anomalies:
            logger.warning(
                f"🚨 Anomalies detected for {entity_name}: {len(anomalies)} signals"
            )
        else:
            logger.info(f"✅ No anomalies detected for {entity_name}")

        return {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "detected_at": datetime.utcnow().isoformat(),
            "current_state": current_state,
            "baseline": {
                "daily_mention_avg": baseline.daily_mention_avg,
                "daily_mention_std": baseline.daily_mention_std,
            },
            "anomalies": anomalies,
            "has_anomaly": len(anomalies) > 0,
        }

    def _calculate_current_state(
        self, intels: Sequence[Intel], time_window_hours: int
    ) -> Dict[str, Any]:
        """计算当前状态"""
        if time_window_hours <= 0:
            raise ValueError("time_window_hours must be greater than 0")

        # 提及量
        mentions_count = len(intels)

        # 归一化到日均(如果窗口是24小时,直接就是日均)
        daily_rate = mentions_count / (time_window_hours / 24.0)

        # 账号类型分布
        verified_count = 0
        influencer_count = 0
        ordinary_count = 0

        for intel in intels:
            meta = intel.meta if isinstance(intel.meta, dict) else {}
            followers = meta.get("author_follower_count", 0)
            try:
                followers = int(followers or 0)
            except (TypeError, ValueError):
                followers = 0

            if followers > 100000:
                verified_count += 1
            elif followers > 10000:
                influencer_count += 1
            else:
                ordinary_count += 1

        total = len(intels) or 1

        return {
            "mentions_today": daily_rate,
            "verified_media_ratio": verified_count / total,
            "influencer_ratio": influencer_count / total,
            "ordinary_ratio": ordinary_count / total,
            "total_intels": len(intels),
        }

    def _compare_with_baseline(
        self, current_state: Dict[str, Any], baseline: Baseline, entity_name: str
    ) -> List[Dict[str, Any]]:
        """与基准线对比,识别异常"""
        anomalies = []

        # 1. 提及量异常检测(Z-score检验)
        current_mentions = current_state["mentions_today"]
        baseline_avg = float(baseline.daily_mention_avg)
        baseline_std = float(baseline.daily_mention_std)

        if baseline_std > 0:
            z_score = abs((current_mentions - baseline_avg) / baseline_std)

            if z_score > 3:  # 3个标准差外
                severity = "HIGH" if z_score > 5 else "MEDIUM"

                anomalies.append(
                    {
                        "type": "VOLUME_SPIKE",
                        "severity": severity,
                        "confidence": min(z_score / 5, 1.0),
                        "description": f"{entity_name}的提及量异常增加",
                        "details": {
                            "current_mentions": current_mentions,
                            "baseline_avg": baseline_avg,
                            "z_score": round(z_score, 2),
                            "increase_rate": round(
                                (current_mentions / baseline_avg - 1) * 100, 1
                            ),
                        },
                    }
                )

        # 2. 账号类型分布异常
        baseline_dist = baseline.account_type_distribution or {}
        current_verified_ratio = current_state["verified_media_ratio"]
        baseline_verified_ratio = baseline_dist.get("verified_media", 0)

        verified_diff = abs(current_verified_ratio - baseline_verified_ratio)

        if verified_diff > 0.3:  # 偏差超过30%
            anomalies.append(
                {
                    "type": "ACCOUNT_TYPE_DISTRIBUTION",
                    "severity": "MEDIUM",
                    "confidence": 0.85,
                    "description": f"{entity_name}的发布账号类型分布异常",
                    "details": {
                        "current_verified_ratio": round(current_verified_ratio, 3),
                        "baseline_verified_ratio": round(baseline_verified_ratio, 3),
                        "difference": round(verified_diff, 3),
                    },
                }
            )

        # 3. 新账号占比异常(如果普通账号占比突然增加)
        current_ordinary_ratio = current_state["ordinary_ratio"]
        baseline_ordinary_ratio = baseline_dist.get("ordinary_users", 0)

        ordinary_diff = current_ordinary_ratio - baseline_ordinary_ratio

        if ordinary_diff > 0.4:  # 新增40%以上普通账号
            anomalies.append(
                {
                    "type": "NEW_ACCOUNT_SURGE",
                    "severity": "HIGH",
                    "confidence": 0.9,
                    "description": f"{entity_name}相关讨论中新账号/普通账号占比异常增加,疑似人工操纵",
                    "details": {
                        "current_ordinary_ratio": round(current_ordinary_ratio, 3),
                        "baseline_ordinary_ratio": round(baseline_ordinary_ratio, 3),
                        "increase": round(ordinary_diff, 3),
                    },
                }
            )

        return anomalies

    async def batch_detect(
        self, entity_list: List[Dict[str, str]], time_window_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        批量检测多个实体的异常

        Args:
            entity_list: [{"entity_id": "...", "entity_name": "..."}, ...]
            time_window_hours: 时间窗口

        Returns:
            异常检测结果列表
        """
        results = []

        for entity in entity_list:
            try:
                result = await self.detect_anomaly(
                    entity_id=entity["entity_id"],
                    entity_name=entity["entity_name"],
                    time_window_hours=time_window_hours,
                )

                if result and result.get("has_anomaly"):
                    results.append(result)

            except Exception as e:
                logger.error(
                    f"❌ Error detecting anomaly for {entity['entity_name']}: {e}"
                )
                continue

        logger.info(
            f"📊 Batch detection completed: {len(results)}/{len(entity_list)} entities have anomalies"
        )

        return results
