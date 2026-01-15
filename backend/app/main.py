"""
FastAPI entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import analysis
import os

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
