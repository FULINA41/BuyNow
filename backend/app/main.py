"""
FastAPI entry point
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .api.endpoints import analysis, portfolio, predict
from .core.logging_config import setup_logging

setup_logging()
load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
TRAIN_DIR = Path(os.getenv("MODEL_ARTIFACTS_DIR", str(BACKEND_DIR / "train")))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models into the singleton ModelManager at startup."""
    from .ml.model import ModelManager

    mgr = ModelManager()
    vocab_path = TRAIN_DIR / "ticker_vocab.json"

    alphanet_weights = TRAIN_DIR / "global_alpha.pth"
    norm_path = TRAIN_DIR / "feat_norm.pt"
    if alphanet_weights.exists() and norm_path.exists() and vocab_path.exists():
        logger.info("Loading AlphaNet …")
        mgr.load_alphanet(
            weights_path=alphanet_weights,
            vocab_path=vocab_path,
            norm_path=norm_path,
            device="cpu",
        )
        logger.info("AlphaNet loaded")

    lgbm_path = TRAIN_DIR / "lgbm_5d_return.txt"
    if lgbm_path.exists():
        logger.info("Loading LightGBM …")
        mgr.load_lgbm(model_path=lgbm_path, vocab_path=vocab_path)
        logger.info("LightGBM loaded")

    logger.info(f"Models ready: {mgr.available_models}")
    yield


logger.info("Starting BuyNow API")
app = FastAPI(
    title="Engineer Alpha API",
    description="Stock risk analysis and buy zone API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(analysis.router)
app.include_router(portfolio.router)
app.include_router(predict.router)


@app.get("/")
async def root():
    """Health check"""
    return {"message": "Engineer Alpha API", "status": "healthy"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}
