"""
Fake News Detection Service

Provides ML-based fake news detection using a trained model.
"""

from __future__ import annotations

import re
import string
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
from loguru import logger

from core.config import settings


def wordopt(text: str) -> str:
    """
    Text preprocessing function for fake news detection.

    Performs:
    - Lowercase conversion
    - Removal of brackets, URLs, HTML tags, punctuation
    - Removal of words containing digits
    """
    text = text.lower()
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\W", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"<.*?>+", "", text)
    text = re.sub(r"[%s]" % re.escape(string.punctuation), "", text)
    text = re.sub(r"\w*\d\w*", "", text)
    return text


class FakeNewsDetector:
    """
    Fake News Detection Service.

    Loads a pre-trained model and provides prediction capabilities.
    """

    _instance: Optional["FakeNewsDetector"] = None

    def __new__(cls) -> "FakeNewsDetector":
        """Singleton pattern for model caching."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the detector."""
        if self._initialized:
            return

        self.model_path = Path(settings.FAKE_NEWS_MODEL_PATH)
        self.vectorizer = None
        self.model = None
        self.label_map = {0: "Fake News", 1: "Not A Fake News"}
        self.model_name = "unknown"
        self._initialized = True

    def load_model(self, model_path: Optional[Path] = None) -> bool:
        """
        Load the model from disk.

        Args:
            model_path: Optional custom path to model file

        Returns:
            True if model loaded successfully

        Raises:
            RuntimeError: If model file not found or loading fails
        """
        path = model_path or self.model_path

        if not path.exists():
            raise RuntimeError(
                f"Model file not found: {path}. "
                "Please train the model first using train_model.py"
            )

        try:
            bundle = joblib.load(path)
            self.vectorizer = bundle.get("vectorizer")
            self.model = bundle.get("model")
            self.label_map = bundle.get("label_map", {0: "Fake News", 1: "Not A Fake News"})
            self.model_name = bundle.get("model_name", "unknown")
            logger.info(f"Fake news model loaded: {self.model_name} from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise RuntimeError(f"Failed to load model: {e}")

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Predict whether the given text is fake news.

        Args:
            text: News text to classify

        Returns:
            Dictionary containing:
            - label: Human-readable label
            - prediction: Integer prediction (0=Fake, 1=Real)
            - confidence: Confidence score (0.0-1.0)
            - model_name: Name of the model used
        """
        # Lazy load model on first prediction
        if self.model is None or self.vectorizer is None:
            self.load_model()

        # Preprocess text
        cleaned = wordopt(text)

        # Vectorize
        vec = self.vectorizer.transform([cleaned])

        # Predict
        pred = int(self.model.predict(vec)[0])

        # Get confidence
        confidence = 0.5
        if hasattr(self.model, "predict_proba"):
            proba = self.model.predict_proba(vec)[0]
            confidence = float(max(proba))

        return {
            "label": self.label_map.get(pred, str(pred)),
            "prediction": pred,
            "confidence": confidence,
            "model_name": self.model_name,
        }

    def health_check(self) -> Dict[str, Any]:
        """
        Check model health status.

        Returns:
            Dictionary with health status information
        """
        loaded = self.model is not None and self.vectorizer is not None
        return {
            "status": "ok" if loaded else "not_loaded",
            "model": self.model_name,
            "loaded": loaded,
        }


# Global detector instance
_detector: Optional[FakeNewsDetector] = None


def get_fake_news_detector() -> FakeNewsDetector:
    """Get the global FakeNewsDetector instance."""
    global _detector
    if _detector is None:
        _detector = FakeNewsDetector()
    return _detector