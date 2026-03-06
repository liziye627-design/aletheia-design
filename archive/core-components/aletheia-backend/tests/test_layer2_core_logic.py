from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.layer2_memory.anomaly_detector import AnomalyDetector
from services.layer2_memory.baseline import BaselineManager


def _intel(created_at: datetime, followers=None):
    return SimpleNamespace(
        created_at=created_at, meta={"author_follower_count": followers}
    )


def test_daily_mentions_include_zero_days_in_window():
    manager = BaselineManager(db=None)
    intels = [
        _intel(datetime(2026, 1, 1, 10, 0), 100),
        _intel(datetime(2026, 1, 1, 11, 0), 200),
        _intel(datetime(2026, 1, 3, 9, 0), 300),
    ]

    stats = manager._calculate_daily_mentions(intels, time_window_days=4)

    expected_counts = [1, 0, 2, 0]
    assert stats["avg"] == pytest.approx(np.mean(expected_counts))
    assert stats["std"] == pytest.approx(np.std(expected_counts))


def test_current_state_handles_non_numeric_or_missing_followers():
    detector = AnomalyDetector(db=None)
    intels = [
        _intel(datetime(2026, 1, 3, 9, 0), None),
        _intel(datetime(2026, 1, 3, 10, 0), "25000"),
        _intel(datetime(2026, 1, 3, 11, 0), "not-a-number"),
    ]

    state = detector._calculate_current_state(intels, time_window_hours=24)

    assert state["mentions_today"] == pytest.approx(3.0)
    assert state["verified_media_ratio"] == pytest.approx(0.0)
    assert state["influencer_ratio"] == pytest.approx(1 / 3)
    assert state["ordinary_ratio"] == pytest.approx(2 / 3)


def test_current_state_rejects_non_positive_time_window():
    detector = AnomalyDetector(db=None)

    with pytest.raises(ValueError):
        detector._calculate_current_state([], time_window_hours=0)


def _baseline(avg: float, std: float, verified: float, ordinary: float):
    return SimpleNamespace(
        daily_mention_avg=avg,
        daily_mention_std=std,
        account_type_distribution={
            "verified_media": verified,
            "ordinary_users": ordinary,
        },
    )


def test_volume_spike_threshold_behavior_at_boundaries():
    detector = AnomalyDetector(db=None)
    entity_name = "测试实体"

    # z = 3.0（阈值边界）不应触发 VOLUME_SPIKE（规则是 > 3）
    baseline = _baseline(avg=10, std=2, verified=0.1, ordinary=0.9)
    current = {
        "mentions_today": 16,
        "verified_media_ratio": 0.1,
        "ordinary_ratio": 0.9,
    }
    anomalies = detector._compare_with_baseline(current, baseline, entity_name)
    assert all(item["type"] != "VOLUME_SPIKE" for item in anomalies)

    # z = 3.1 -> MEDIUM
    current_medium = {
        "mentions_today": 16.2,
        "verified_media_ratio": 0.1,
        "ordinary_ratio": 0.9,
    }
    anomalies_medium = detector._compare_with_baseline(
        current_medium, baseline, entity_name
    )
    volume_medium = [a for a in anomalies_medium if a["type"] == "VOLUME_SPIKE"]
    assert len(volume_medium) == 1
    assert volume_medium[0]["severity"] == "MEDIUM"

    # z = 5.1 -> HIGH
    current_high = {
        "mentions_today": 20.2,
        "verified_media_ratio": 0.1,
        "ordinary_ratio": 0.9,
    }
    anomalies_high = detector._compare_with_baseline(
        current_high, baseline, entity_name
    )
    volume_high = [a for a in anomalies_high if a["type"] == "VOLUME_SPIKE"]
    assert len(volume_high) == 1
    assert volume_high[0]["severity"] == "HIGH"
    assert 0 <= volume_high[0]["confidence"] <= 1
