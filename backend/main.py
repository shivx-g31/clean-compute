import os
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load env variables
load_dotenv()
backend_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(backend_env_path):
    load_dotenv(backend_env_path)

from db import get_db_type, db_manager
import repository

logger = logging.getLogger("cleancompute.api")

app = FastAPI(
    title="CleanCompute",
    description="Same AI. Less carbon. - Carbon-aware AI Workload Scheduler",
    version="1.0.0"
)

# Configure CORS
# Enabled for localhost:5173, 127.0.0.1:5173 and deployed frontend URL from env
cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]

frontend_url = os.getenv("FRONTEND_URL") or os.getenv("DEPLOYED_FRONTEND_URL")
if frontend_url:
    cleaned_url = frontend_url.strip().rstrip("/")
    if cleaned_url and cleaned_url not in cors_origins:
        cors_origins.append(cleaned_url)

extra_origins = os.getenv("CORS_ORIGINS", "")
if extra_origins:
    for origin in extra_origins.split(","):
        o = origin.strip().rstrip("/")
        if o and o not in cors_origins:
            cors_origins.append(o)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Startup event
@app.on_event("startup")
def startup_event():
    # Initialize DB connection on startup
    db_manager.initialize()
    logger.info("Database initialized. Mode: %s", get_db_type())


# Root info
@app.get("/")
def read_root():
    return {
        "app": "CleanCompute",
        "tagline": "Same AI. Less carbon.",
        "status": "online",
        "database": get_db_type()
    }


# Health check reporting database in use (mongodb or memory)
@app.get("/api/health")
def health_check():
    current_db = get_db_type()
    return {
        "status": "healthy",
        "service": "CleanCompute",
        "tagline": "Same AI. Less carbon.",
        "database": current_db
    }


# --- Pydantic Schemas for validation ---

class JobCreate(BaseModel):
    name: Optional[str] = "AI Workload"
    gpu_type: str = Field(..., description="GPU architecture e.g. NVIDIA H100, A100")
    gpu_count: int = Field(default=1, ge=1)
    duration_hours: float = Field(..., gt=0)
    deadline_hours: float = Field(..., gt=0)
    flexibility: Optional[str] = "flexible"
    checkpointable: Optional[bool] = True
    submitted_region: Optional[str] = "in-west"
    notes: Optional[str] = None


class ScheduleCreate(BaseModel):
    job_id: str
    mode: str = "Greenest"
    strategy: str = "time_shift"
    recommended_region: str
    recommended_region_name: Optional[str] = None
    start_time_offset_hours: float = 0.0
    baseline_co2_kg: float
    optimized_co2_kg: float
    co2_saved_kg: float
    reduction_pct: float
    transfer_penalty_kg: Optional[float] = 0.0
    notes: Optional[str] = None


# --- Jobs Endpoints ---

@app.post("/api/jobs")
def create_job(job: JobCreate):
    saved = repository.save_job(job.dict())
    return saved


@app.get("/api/jobs")
def get_jobs(limit: int = Query(default=50, ge=1, le=100), skip: int = Query(default=0, ge=0)):
    return repository.list_jobs(limit=limit, skip=skip)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# --- Schedules Endpoints ---

@app.post("/api/schedules")
def create_schedule(schedule: ScheduleCreate):
    saved = repository.save_schedule(schedule.dict())
    return saved


@app.get("/api/schedules/{job_id}")
def get_schedule(job_id: str):
    sched = repository.get_schedule_by_job_id(job_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found for this job")
    return sched


# --- Impact Stats Endpoint ---

@app.get("/api/impact")
def get_impact():
    return repository.get_impact_stats()


# --- Demo Data Seed & Clear ---

@app.post("/api/demo/seed")
def seed_demo():
    return repository.seed_demo_data()


@app.post("/api/demo/clear")
def clear_demo():
    return repository.clear_demo_data()
