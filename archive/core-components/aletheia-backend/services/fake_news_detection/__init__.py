"""
Fake News Detection Service Module
"""

from services.fake_news_detection.service import FakeNewsDetector
from services.fake_news_detection.schemas import PredictRequest, PredictResponse

__all__ = ["FakeNewsDetector", "PredictRequest", "PredictResponse"]