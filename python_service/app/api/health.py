"""
Health check endpoints
"""
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter
import psutil
import os

router = APIRouter()


def check_database() -> Dict[str, Any]:
    """Check SQLite database health"""
    try:
        from ..db.database import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return {"status": "healthy", "message": "Database connection OK"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def check_llm_gateway() -> Dict[str, Any]:
    """Check LLM gateway configuration"""
    try:
        
        providers = []
        if os.getenv("GEMINI_API_KEY"):
            providers.append("gemini")
        if os.getenv("DEEPSEEK_API_KEY"):
            providers.append("deepseek")
        
        if providers:
            return {"status": "healthy", "providers": providers}
        else:
            return {"status": "degraded", "message": "No LLM API keys configured"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def check_memory() -> Dict[str, Any]:
    """Check memory usage"""
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        system_memory = psutil.virtual_memory()
        
        return {
            "status": "healthy" if memory_mb < 1000 else "warning",
            "process_mb": round(memory_mb, 2),
            "system_percent": system_memory.percent
        }
    except Exception as e:
        return {"status": "unknown", "message": str(e)}


def check_disk() -> Dict[str, Any]:
    """Check disk usage"""
    try:
        disk = psutil.disk_usage('/')
        return {
            "status": "healthy" if disk.percent < 90 else "warning",
            "percent_used": disk.percent,
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"status": "unknown", "message": str(e)}


@router.get("/health")
async def health_check():
    """
    Health check endpoint returning status of all components.
    """
    checks = {
        "database": check_database(),
        "llm_gateway": check_llm_gateway(),
        "memory": check_memory(),
        "disk": check_disk(),
    }
    
    # Overall status
    statuses = [c.get("status") for c in checks.values()]
    if all(s == "healthy" for s in statuses):
        overall_status = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "checks": checks
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness probe - indicates if service is ready to accept traffic.
    """
    db_status = check_database()
    
    if db_status["status"] == "unhealthy":
        return {"status": "not_ready", "reason": "Database unavailable"}
    
    return {"status": "ready"}


@router.get("/health/live")
async def liveness_check():
    """
    Liveness probe - indicates if service is alive.
    """
    return {"status": "alive"}
