from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.routers import sensor, optimization, summary


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("Veritabani hazir.")
    yield
    print("Uygulama kapatiliyor.")


app = FastAPI(
    title="Akilli Sinif Otomasyon API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensor.router)
app.include_router(optimization.router)
app.include_router(summary.router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "running",
        "docs": "/docs",
        "endpoints": ["/api/data", "/api/scenarios", "/api/summary"],
    }