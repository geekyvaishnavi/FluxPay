from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.payments import router as payments_router
from app.api.recovery import router as recovery_router
from app.core.config import settings

app = FastAPI(
    title="FluxPay API",
    version="0.1.0",
    description="Foundation API for the FluxPay revenue recovery MVP.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(payments_router)
app.include_router(recovery_router)
app.include_router(dashboard_router)
