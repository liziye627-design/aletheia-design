"""
Fake News Detection API Endpoints
"""

from fastapi import APIRouter, HTTPException

from services.fake_news_detection import FakeNewsDetector, PredictRequest, PredictResponse
from services.fake_news_detection.schemas import HealthResponse
from services.fake_news_detection.service import get_fake_news_detector

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for fake news detection service.

    Returns the current status of the model.
    """
    detector = get_fake_news_detector()
    status = detector.health_check()
    return HealthResponse(
        status=status["status"],
        model=status["model"],
        loaded=status["loaded"],
    )


@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """
    Predict whether the given news text is fake or real.

    Args:
        request: PredictRequest with text field (min 20 chars)

    Returns:
        PredictResponse with label, prediction, confidence, and model_name

    Raises:
        HTTPException: If prediction fails
    """
    detector = get_fake_news_detector()

    try:
        result = detector.predict(request.text)
        return PredictResponse(
            label=result["label"],
            prediction=result["prediction"],
            confidence=result["confidence"],
            model_name=result["model_name"],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")