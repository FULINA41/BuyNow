"""
FastAPI entry point
"""
from loguru import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import analysis
import os
from dotenv import load_dotenv

# logging
from .core.logging_config import setup_logging
# initialize logging
setup_logging()

# Load environment variables from .env if present
load_dotenv()

logger.info("Starting BuyNow API")
app = FastAPI(
    title="Engineer Alpha API",
    description="Stock risk analysis and buy zone API",
    version="1.0.0"
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


@app.get("/")
async def root():
    """Health check"""
    return {"message": "Engineer Alpha API", "status": "healthy"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}
