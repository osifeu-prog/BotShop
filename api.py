from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import config
from database import db

from user_routes import router as user_router
from asset_routes import router as asset_router
from payment_routes import router as payment_router
from admin_routes import router as admin_router
from webhook_routes import router as webhook_router, telegram_webhook

app = FastAPI(
    title="Digital Assets Ecosystem API",
    description="API for managing digital assets and marketing networks",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & templates for API (not GitHub Pages)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(user_router, prefix="/api/users", tags=["Users"])
app.include_router(asset_router, prefix="/api/assets", tags=["Assets"])
app.include_router(payment_router, prefix="/api/payments", tags=["Payments"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(webhook_router, prefix="/webhooks", tags=["Webhooks"])

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "digital-assets-ecosystem",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "db": db.health_check(),
    }

@app.get("/")
async def root():
    return {
        "message": "Welcome to Digital Assets Ecosystem API",
        "version": "2.0.0",
        "docs": "/api/docs",
        "landing_url": config.LANDING_URL,
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )

# compatibility with your existing WEBHOOK_URL=/webhook
@app.post("/webhook")
async def root_webhook(request: Request):
    return await telegram_webhook(request)
