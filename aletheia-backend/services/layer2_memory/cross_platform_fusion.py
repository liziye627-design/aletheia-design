"""
跨平台数据融合服务 - 增强Layer 2基线建立和异常检测
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from services.layer1_perception.crawler_manager import get_crawler_manager
from utils.logging import logger


class CrossPlatformDataFusion:
    """跨平台数据融合服务"""

    def __init__(self):
        """初始化融合服务"""
        self.crawler_manager = get_crawler_manager()

    async def analyze_cross_platform_credibility(
        self,
        keyword: str,
        platforms: Optional[List[str]] = None,
        limit_per_platform: int = 50,
    ) -> Dict[str, Any]:
        """
        跨平台可信度分析（核心功能）

        Args:
            keyword: 关键词（待验证信息）
            platforms: 平台列表
            limit_per_platform: 每平台数据量

        Returns:
            综合可信度评估结果
        """
        logger.info(f"🔍 Cross-platform credibility analysis for: {keyword}")

        # 1. 跨平台数据采集
        aggregated_data = await self.crawler_manager.aggregate_cross_platform_data(
            keyword=keyword,
            platforms=platforms,
            limit_per_platform=limit_per_platform,
        )
        if not isinstance(aggregated_data, dict):
            aggregated_data = {}
        aggregated_data.setdefault("summary", {})
        aggregated_data.setdefault("platform_stats", {})
        aggregated_data.setdefault("top_entities", [])
        aggregated_data.setdefault("time_distribution", {})

        # 2. 建立多平台基线
        baseline_data = await self._establish_multi_platform_baseline(
            keyword=keyword, aggregated_data=aggregated_data
        )

        # 3. 检测跨平台异常
        anomalies = await self._detect_cross_platform_anomalies(
            keyword=keyword, aggregated_data=aggregated_data, baseline=baseline_data
        )

        # 4. 计算综合可信度分数
        credibility_score = self._calculate_credibility_score(
            aggregated_data=aggregated_data,
            baseline=baseline_data,
            anomalies=anomalies,
        )

        # 5. 生成风险标签
        risk_flags = self._generate_risk_flags(
            aggregated_data=aggregated_data, anomalies=anomalies
        )

        # 6. 生成证据链
        evidence_chain = self._generate_evidence_chain(
            keyword=keyword,
            aggregated_data=aggregated_data,
            baseline=baseline_data,
            anomalies=anomalies,
        )

        result = {
            "keyword": keyword,
            "timestamp": datetime.utcnow().isoformat(),
            "credibility_score": credibility_score,
            "credibility_level": self._get_credibility_level(credibility_score),
            "risk_flags": risk_flags,
            "summary": aggregated_data["summary"],
            "platform_stats": aggregated_data["platform_stats"],
            "baseline": baseline_data,
            "anomalies": anomalies,
            "evidence_chain": evidence_chain,
            "top_entities": aggregated_data["top_entities"],
            "time_distribution": aggregated_data["time_distribution"],
        }

        logger.info(
            f"✅ Cross-platform analysis completed - Credibility: {credibility_score:.2%}"
        )
        return result

    async def _establish_multi_platform_baseline(
        self, keyword: str, aggregated_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        建立多平台基线

        Args:
            keyword: 关键词
            aggregated_data: 聚合数据

        Returns:
            基线数据
        """
        logger.info(f"📊 Establishing multi-platform baseline for: {keyword}")

        # 计算历史基线（假设有历史数据，这里使用模拟）
        # 在实际应用中，应从数据库查询历史30天的数据

        platform_baselines = {}

        for platform, stats in aggregated_data.get("platform_stats", {}).items():
            if not isinstance(stats, dict):
                continue
            if int(stats.get("post_count", 0) or 0) == 0:
                continue

            # 模拟历史数据（实际应从数据库查询）
            historical_avg_posts = 50  # 平均每天50条相关帖子
            historical_std_posts = 15  # 标准差15

            historical_avg_engagement = 100  # 平均互动量
            historical_std_engagement = 30

            # 计算Z-score
            current_posts = int(stats.get("post_count", 0) or 0)
            z_score_posts = (
                (current_posts - historical_avg_posts) / historical_std_posts
                if historical_std_posts > 0
                else 0
            )

            current_engagement = float(stats.get("avg_engagement", 0) or 0)
            z_score_engagement = (
                (current_engagement - historical_avg_engagement)
                / historical_std_engagement
                if historical_std_engagement > 0
                else 0
            )

            platform_baselines[platform] = {
                "historical_avg_posts": historical_avg_posts,
                "historical_std_posts": historical_std_posts,
                "current_posts": current_posts,
                "z_score_posts": round(z_score_posts, 2),
                "historical_avg_engagement": historical_avg_engagement,
                "historical_std_engagement": historical_std_engagement,
                "current_engagement": current_engagement,
                "z_score_engagement": round(z_score_engagement, 2),
            }

        return {
            "keyword": keyword,
            "timestamp": datetime.utcnow().isoformat(),
            "platform_baselines": platform_baselines,
        }

    async def _detect_cross_platform_anomalies(
        self,
        keyword: str,
        aggregated_data: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        检测跨平台异常

        Args:
            keyword: 关键词
            aggregated_data: 聚合数据
            baseline: 基线数据

        Returns:
            异常列表
        """
        logger.info(f"🚨 Detecting cross-platform anomalies for: {keyword}")

        anomalies = []

        # 1. 检测发帖量异常
        for platform, baseline_data in baseline["platform_baselines"].items():
            z_score = baseline_data["z_score_posts"]

            if abs(z_score) > 3:  # 3倍标准差
                anomalies.append(
                    {
                        "type": "VOLUME_SPIKE" if z_score > 0 else "VOLUME_DROP",
                        "platform": platform,
                        "severity": "HIGH" if abs(z_score) > 5 else "MEDIUM",
                        "z_score": z_score,
                        "description": f"{platform} 发帖量异常: Z-score = {z_score:.2f}",
                        "current_value": baseline_data["current_posts"],
                        "baseline_avg": baseline_data["historical_avg_posts"],
                    }
                )

        # 2. 检测新账户比例异常
        new_account_ratio = aggregated_data["summary"].get("new_account_ratio", 0)
        if new_account_ratio > 0.3:  # 30%以上新账户
            anomalies.append(
                {
                    "type": "NEW_ACCOUNT_SURGE",
                    "platform": "all",
                    "severity": "HIGH" if new_account_ratio > 0.5 else "MEDIUM",
                    "ratio": new_account_ratio,
                    "description": f"新账户占比过高: {new_account_ratio:.2%}（正常<30%）",
                }
            )

        # 3. 检测时间分布异常
        time_dist = aggregated_data.get("time_distribution", {})
        if time_dist:
            hour_counts = list(time_dist.values())
            if hour_counts:
                avg_count = statistics.mean(hour_counts)
                max_count = max(hour_counts)

                # 如果某个时段的发帖量远超平均值（5倍以上）
                if max_count > avg_count * 5 and avg_count > 0:
                    peak_hour = max(time_dist, key=time_dist.get)
                    anomalies.append(
                        {
                            "type": "TIME_DISTRIBUTION_ANOMALY",
                            "platform": "all",
                            "severity": "MEDIUM",
                            "peak_hour": peak_hour,
                            "peak_count": max_count,
                            "avg_count": round(avg_count, 2),
                            "description": f"时间分布异常: {peak_hour}时有{max_count}条帖子（平均{avg_count:.0f}）",
                        }
                    )

        # 4. 检测跨平台一致性（如果多个平台都有数据）
        platform_count = int(aggregated_data.get("summary", {}).get("platform_count", 0) or 0)
        if platform_count >= 2:
            # 检查各平台的发帖时间是否过于一致（可能是协同水军）
            # TODO: 实现更复杂的一致性检测算法
            pass

        logger.info(f"✅ Detected {len(anomalies)} anomalies across platforms")
        return anomalies

    def _calculate_credibility_score(
        self,
        aggregated_data: Dict[str, Any],
        baseline: Dict[str, Any],
        anomalies: List[Dict[str, Any]],
    ) -> float:
        """
        计算综合可信度分数

        Args:
            aggregated_data: 聚合数据
            baseline: 基线数据
            anomalies: 异常列表

        Returns:
            可信度分数 (0.0-1.0)
        """
        summary = aggregated_data.get("summary", {}) if isinstance(aggregated_data, dict) else {}
        if not isinstance(summary, dict):
            summary = {}
        total_posts = int(summary.get("total_posts", 0) or 0)
        # 无数据时禁止给出偏高分，避免误导前端为“高可信”
        if total_posts == 0:
            return 0.45

        score = 0.5  # 基础分50%

        # 1. 异常扣分
        for anomaly in anomalies:
            if anomaly["type"] == "VOLUME_SPIKE":
                score -= 0.15  # 发帖量异常增加扣15%
            elif anomaly["type"] == "NEW_ACCOUNT_SURGE":
                score -= 0.20  # 新账户激增扣20%
            elif anomaly["type"] == "TIME_DISTRIBUTION_ANOMALY":
                score -= 0.10  # 时间分布异常扣10%

        # 2. 平台数量加分（多源印证）
        platform_stats = (
            aggregated_data.get("platform_stats", {})
            if isinstance(aggregated_data, dict)
            else {}
        )
        if not isinstance(platform_stats, dict):
            platform_stats = {}
        platforms_with_data = sum(
            1
            for stats in platform_stats.values()
            if isinstance(stats, dict) and int(stats.get("post_count", 0) or 0) > 0
        )
        if platforms_with_data >= 3:
            score += 0.15  # 3个以上平台加15%
        elif platforms_with_data >= 2:
            score += 0.10  # 2个平台加10%

        # 3. 互动质量加分
        avg_engagement = float(summary.get("avg_engagement", 0) or 0)
        if avg_engagement > 50:
            score += 0.10  # 高互动加10%
        elif avg_engagement > 20:
            score += 0.05  # 中等互动加5%

        # 4. 限制分数范围
        score = max(0.0, min(1.0, score))

        return round(score, 2)

    def _generate_risk_flags(
        self, aggregated_data: Dict[str, Any], anomalies: List[Dict[str, Any]]
    ) -> List[str]:
        """
        生成风险标签

        Args:
            aggregated_data: 聚合数据
            anomalies: 异常列表

        Returns:
            风险标签列表
        """
        flags = []

        # 基于异常生成标签
        for anomaly in anomalies:
            anomaly_type = anomaly["type"]

            if anomaly_type == "VOLUME_SPIKE":
                flags.append("ABNORMAL_VOLUME_SPIKE")
            elif anomaly_type == "NEW_ACCOUNT_SURGE":
                flags.append("COORDINATED_INAUTHENTIC_BEHAVIOR")
            elif anomaly_type == "TIME_DISTRIBUTION_ANOMALY":
                flags.append("BOT_LIKE_PATTERN")

        # 基于聚合数据生成标签
        new_account_ratio = aggregated_data["summary"].get("new_account_ratio", 0)
        if new_account_ratio > 0.5:
            flags.append("HIGH_NEW_ACCOUNT_RATIO")

        total_posts = aggregated_data["summary"].get("total_posts", 0)
        if total_posts < 5:
            flags.append("INSUFFICIENT_DATA")

        # 去重
        return list(set(flags))

    def _generate_evidence_chain(
        self,
        keyword: str,
        aggregated_data: Dict[str, Any],
        baseline: Dict[str, Any],
        anomalies: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """
        生成证据链

        Args:
            keyword: 关键词
            aggregated_data: 聚合数据
            baseline: 基线数据
            anomalies: 异常列表

        Returns:
            证据链
        """
        evidence = []

        # 1. 数据采集证据
        evidence.append(
            {
                "step": "数据采集",
                "description": (
                    "从"
                    f"{int(aggregated_data.get('summary', {}).get('platform_count', 0) or 0)}个平台"
                    "采集到"
                    f"{int(aggregated_data.get('summary', {}).get('total_posts', 0) or 0)}条相关帖子"
                ),
            }
        )

        # 2. 基线对比证据
        for platform, baseline_data in baseline["platform_baselines"].items():
            z_score = baseline_data["z_score_posts"]
            evidence.append(
                {
                    "step": f"{platform}基线对比",
                    "description": f"当前发帖量{baseline_data['current_posts']}条，历史平均{baseline_data['historical_avg_posts']}条，Z-score={z_score:.2f}",
                }
            )

        # 3. 异常检测证据
        for anomaly in anomalies:
            evidence.append(
                {
                    "step": "异常检测",
                    "description": anomaly["description"],
                    "severity": anomaly["severity"],
                }
            )

        # 4. 新账户分析证据
        new_account_ratio = aggregated_data["summary"].get("new_account_ratio", 0)
        evidence.append(
            {
                "step": "账户年龄分析",
                "description": f"新账户（<30天）占比: {new_account_ratio:.2%}",
            }
        )

        return evidence

    def _get_credibility_level(self, score: float) -> str:
        """
        根据分数获取可信度等级

        Args:
            score: 可信度分数

        Returns:
            等级标签
        """
        if score >= 0.8:
            return "VERY_HIGH"
        elif score >= 0.6:
            return "HIGH"
        elif score >= 0.4:
            return "MEDIUM"
        elif score >= 0.2:
            return "LOW"
        else:
            return "VERY_LOW"


# 单例模式
_fusion_service_instance: Optional[CrossPlatformDataFusion] = None


def get_fusion_service() -> CrossPlatformDataFusion:
    """获取跨平台融合服务单例"""
    global _fusion_service_instance

    if _fusion_service_instance is None:
        _fusion_service_instance = CrossPlatformDataFusion()

    return _fusion_service_instance
