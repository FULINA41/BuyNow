import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Ensure app package is importable when running tests from backend/
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Load .env so GEMINI_API_KEY etc. are available for integration tests
load_dotenv(backend_dir / ".env")

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)
