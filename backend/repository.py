import copy
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from db import get_db, get_db_type


def _normalize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Converts ObjectId fields to strings and ensures consistent id field."""
    if doc is None:
        return None
    d = copy.deepcopy(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
        if "id" not in d:
            d["id"] = d["_id"]
    return d


def _normalize_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_normalize_doc(doc) for doc in docs if doc is not None]


def _build_id_query(identifier: str) -> Dict[str, Any]:
    """Builds MongoDB query matching either string or ObjectId."""
    try:
        oid = ObjectId(identifier)
        return {"$or": [{"_id": oid}, {"_id": identifier}, {"id": identifier}]}
    except (InvalidId, TypeError, ValueError):
        return {"$or": [{"_id": identifier}, {"id": identifier}]}


# --- JOBS REPOSITORY ---

def save_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """Saves a new job to the jobs collection."""
    db = get_db()
    data = copy.deepcopy(job_data)
    if "created_at" not in data:
        data["created_at"] = datetime.now(timezone.utc).isoformat()
    if "status" not in data:
        data["status"] = "pending"

    result = db.jobs.insert_one(data)
    inserted_id = str(result.inserted_id)
    data["_id"] = inserted_id
    data["id"] = inserted_id
    return data


def list_jobs(limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    """Lists jobs sorted by created_at descending."""
    db = get_db()
    cursor = db.jobs.find({}, sort=[("created_at", -1)], limit=limit, skip=skip)
    return _normalize_docs(list(cursor))


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single job by its ID."""
    db = get_db()
    db_type = get_db_type()
    if db_type == "mongodb":
        query = _build_id_query(job_id)
    else:
        query = {"_id": job_id}
    doc = db.jobs.find_one(query)
    return _normalize_doc(doc)


# --- SCHEDULES REPOSITORY ---

def save_schedule(schedule_data: Dict[str, Any]) -> Dict[str, Any]:
    """Saves a schedule recommendation to the schedules collection."""
    db = get_db()
    data = copy.deepcopy(schedule_data)
    if "created_at" not in data:
        data["created_at"] = datetime.now(timezone.utc).isoformat()

    result = db.schedules.insert_one(data)
    inserted_id = str(result.inserted_id)
    data["_id"] = inserted_id
    data["id"] = inserted_id
    return data


def get_schedule_by_job_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves schedule for a given job_id."""
    db = get_db()
    doc = db.schedules.find_one({"job_id": job_id})
    return _normalize_doc(doc)


# --- CARBON CACHE REPOSITORY ---

def save_carbon_cache(region_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Saves latest carbon intensity data for a region with timestamp."""
    db = get_db()
    cache_entry = {
        "region_id": region_id,
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    db.carbon_cache.update_one(
        {"region_id": region_id},
        {"$set": cache_entry},
        upsert=True
    )
    return cache_entry


def get_carbon_cache(region_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached carbon data for a given region."""
    db = get_db()
    doc = db.carbon_cache.find_one({"region_id": region_id})
    return _normalize_doc(doc)


# --- IMPACT STATS REPOSITORY ---

def get_impact_stats() -> Dict[str, Any]:
    """Aggregates impact statistics across scheduled workloads."""
    db = get_db()
    all_jobs = list(db.jobs.find({}))
    all_schedules = list(db.schedules.find({}))

    total_jobs = len(all_jobs)
    total_schedules = len(all_schedules)

    total_baseline_co2_kg = 0.0
    total_optimized_co2_kg = 0.0
    strategy_counts = {
        "time_shift": 0,
        "geo_shift": 0,
        "pause_resume": 0
    }
    regions_used = set()

    for s in all_schedules:
        base = float(s.get("baseline_co2_kg", 0.0) or 0.0)
        opt = float(s.get("optimized_co2_kg", 0.0) or 0.0)
        total_baseline_co2_kg += base
        total_optimized_co2_kg += opt

        # Strategy breakdown
        strat = s.get("strategy")
        if strat in strategy_counts:
            strategy_counts[strat] += 1

        reg = s.get("recommended_region")
        if reg:
            regions_used.add(reg)

    total_co2_saved_kg = max(0.0, total_baseline_co2_kg - total_optimized_co2_kg)
    if total_baseline_co2_kg > 0:
        avg_carbon_reduction_pct = round((total_co2_saved_kg / total_baseline_co2_kg) * 100, 1)
    else:
        avg_carbon_reduction_pct = 0.0

    # Trees equivalent: approx 21 kg CO2 absorbed per tree per year
    trees_equivalent = round(total_co2_saved_kg / 21.0, 2)

    return {
        "total_jobs": total_jobs,
        "total_schedules": total_schedules,
        "total_co2_saved_kg": round(total_co2_saved_kg, 2),
        "total_baseline_co2_kg": round(total_baseline_co2_kg, 2),
        "total_optimized_co2_kg": round(total_optimized_co2_kg, 2),
        "avg_carbon_reduction_pct": avg_carbon_reduction_pct,
        "trees_equivalent_annual": trees_equivalent,
        "active_green_regions_count": len(regions_used),
        "strategy_breakdown": strategy_counts
    }


# --- DEMO DATA MANAGEMENT ---

def seed_demo_data() -> Dict[str, Any]:
    """Seeds realistic sample AI jobs and carbon-optimized schedules."""
    clear_demo_data()

    sample_jobs = [
        {
            "name": "LLaMA-3-8B Fine-Tuning",
            "gpu_type": "NVIDIA H100",
            "gpu_count": 8,
            "duration_hours": 12,
            "deadline_hours": 36,
            "flexibility": "flexible",
            "checkpointable": True,
            "submitted_region": "in-west",
            "status": "scheduled",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "name": "Stable Diffusion LoRA Training",
            "gpu_type": "NVIDIA A100",
            "gpu_count": 4,
            "duration_hours": 6,
            "deadline_hours": 24,
            "flexibility": "moderately_flexible",
            "checkpointable": True,
            "submitted_region": "us-va",
            "status": "scheduled",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "name": "Multi-Modal Embedding Batch",
            "gpu_type": "NVIDIA L40S",
            "gpu_count": 2,
            "duration_hours": 4,
            "deadline_hours": 12,
            "flexibility": "strict",
            "checkpointable": False,
            "submitted_region": "de",
            "status": "scheduled",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "name": "Genomics Foundation Model Pre-train",
            "gpu_type": "NVIDIA H100",
            "gpu_count": 16,
            "duration_hours": 24,
            "deadline_hours": 72,
            "flexibility": "flexible",
            "checkpointable": True,
            "submitted_region": "za",
            "status": "scheduled",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]

    saved_jobs = []
    saved_schedules = []

    # Corresponding schedules
    sample_schedules = [
        {
            "mode": "Greenest",
            "strategy": "geo_shift",
            "recommended_region": "se",
            "recommended_region_name": "Sweden",
            "start_time_offset_hours": 2,
            "baseline_co2_kg": 249.6,
            "optimized_co2_kg": 15.4,
            "co2_saved_kg": 234.2,
            "reduction_pct": 93.8,
            "transfer_penalty_kg": 0.45,
            "notes": "Geo-shifted from India-West to Sweden hydro/nuclear grid. 93.8% carbon reduction."
        },
        {
            "mode": "Balanced",
            "strategy": "time_shift",
            "recommended_region": "ca-qc",
            "recommended_region_name": "Canada-Quebec",
            "start_time_offset_hours": 4,
            "baseline_co2_kg": 50.4,
            "optimized_co2_kg": 4.3,
            "co2_saved_kg": 46.1,
            "reduction_pct": 91.5,
            "transfer_penalty_kg": 0.12,
            "notes": "Shifted to Quebec hydro grid during off-peak window."
        },
        {
            "mode": "Fastest",
            "strategy": "time_shift",
            "recommended_region": "fr",
            "recommended_region_name": "France",
            "start_time_offset_hours": 0,
            "baseline_co2_kg": 21.0,
            "optimized_co2_kg": 3.6,
            "co2_saved_kg": 17.4,
            "reduction_pct": 82.9,
            "transfer_penalty_kg": 0.08,
            "notes": "Immediate execution on ultra-clean French nuclear grid."
        },
        {
            "mode": "Greenest",
            "strategy": "pause_resume",
            "recommended_region": "se",
            "recommended_region_name": "Sweden",
            "start_time_offset_hours": 1,
            "baseline_co2_kg": 1152.0,
            "optimized_co2_kg": 61.4,
            "co2_saved_kg": 1090.6,
            "reduction_pct": 94.7,
            "transfer_penalty_kg": 1.20,
            "notes": "Checkpointable workload distributed across peak wind windows."
        }
    ]

    for job_info, sched_info in zip(sample_jobs, sample_schedules):
        j = save_job(job_info)
        saved_jobs.append(j)

        sched = copy.deepcopy(sched_info)
        sched["job_id"] = j["id"]
        s = save_schedule(sched)
        saved_schedules.append(s)

    return {
        "status": "success",
        "jobs_seeded": len(saved_jobs),
        "schedules_seeded": len(saved_schedules),
        "total_co2_saved_kg": sum(s["co2_saved_kg"] for s in sample_schedules)
    }


def clear_demo_data() -> Dict[str, Any]:
    """Clears jobs and schedules collections."""
    db = get_db()
    del_jobs = db.jobs.delete_many({})
    del_sched = db.schedules.delete_many({})
    return {
        "status": "cleared",
        "deleted_jobs": del_jobs.deleted_count,
        "deleted_schedules": del_sched.deleted_count
    }

