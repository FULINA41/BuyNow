"""
Integration tests for POST /api/v1/analyze/LLM (analyze_stock_llm).
Uses real Gemini API when GEMINI_API_KEY is set; skips real-call tests when not set.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
import pytest
from fastapi.testclient import TestClient

# Load backend/.env before checking API key (pytest may load this module before conftest)
# __file__ is backend/tests/integration/test_*.py -> parent.parent = backend
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
REQUIRES_API_KEY = not os.environ.get("GEMINI_API_KEY")


@pytest.mark.skipif(REQUIRES_API_KEY, reason="GEMINI_API_KEY not set; real API tests skipped")
def test_analyze_stock_llm_returns_stream(client: TestClient):
    """Real API: response is 200 and stream content-type."""
    response = client.post(
        "/api/v1/analyze/LLM",
        json={"ticker": "MSFT", "years": 5, "mode": "standard"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.skipif(REQUIRES_API_KEY, reason="GEMINI_API_KEY not set; real API tests skipped")
def test_analyze_stock_llm_stream_content(client: TestClient):
    """Real API: stream returns non-empty text."""
    response = client.post(
        "/api/v1/analyze/LLM",
        json={"ticker": "AAPL", "years": 10, "mode": "aggressive"},
    )
    assert response.status_code == 200
    body = b"".join(response.iter_bytes()).decode("utf-8", errors="replace")
    assert len(body.strip()) > 0


def test_analyze_stock_llm_validates_request(client: TestClient):
    """Invalid request body returns 422 (no API call)."""
    response = client.post(
        "/api/v1/analyze/LLM",
        json={"ticker": "T", "years": 1, "mode": "standard"},
    )
    assert response.status_code == 422
