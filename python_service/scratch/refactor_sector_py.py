import re

filepath = "/home/ubuntu/work/alsa/python_service/app/api/sector.py"
with open(filepath, "r") as f:
    content = f.read()

# 1. Add Redis import
if "from ..db.redis_client import RedisManager" not in content:
    content = content.replace("from ..utils.responses import success_response, error_response", 
                              "from ..utils.responses import success_response, error_response\nfrom ..db.redis_client import RedisManager")

# 2. Add Redis Helper for scan jobs
redis_helper = """
async def _update_scan_job_redis(job_id: str, **kwargs):
    redis = await RedisManager.get_client()
    key = f"scan_job:{job_id}"
    data = await redis.get(key)
    job = json.loads(data) if data else {}
    job.update(kwargs)
    await redis.set(key, json.dumps(job), ex=86400)

async def _get_scan_job_redis(job_id: str):
    redis = await RedisManager.get_client()
    data = await redis.get(f"scan_job:{job_id}")
    return json.loads(data) if data else None

"""
if "_update_scan_job_redis" not in content:
    # Insert helper right after _scan_jobs definition
    content = content.replace("_scan_tasks: Dict[str, asyncio.Task] = {}", 
                              "_scan_tasks: Dict[str, asyncio.Task] = {}\n" + redis_helper)

# 3. Replace direct dictionary access in _run_scan and start endpoints
content = re.sub(r'_scan_jobs\[job_id\]\["progress"\] = (.*?)\n', r'asyncio.create_task(_update_scan_job_redis(job_id, progress=\1))\n', content)
content = re.sub(r'_scan_jobs\[job_id\]\["status"\] = (.*?)\n', r'asyncio.create_task(_update_scan_job_redis(job_id, status=\1))\n', content)
content = re.sub(r'_scan_jobs\[job_id\]\["error"\] = (.*?)\n', r'asyncio.create_task(_update_scan_job_redis(job_id, error=\1))\n', content)
content = re.sub(r'_scan_jobs\[job_id\]\["content_count"\] = (.*?)\n', r'asyncio.create_task(_update_scan_job_redis(job_id, content_count=\1))\n', content)
content = re.sub(r'_scan_jobs\[job_id\]\["result"\] = (.*?)\n', r'asyncio.create_task(_update_scan_job_redis(job_id, result=\1))\n', content)
content = re.sub(r'_scan_jobs\[job_id\]\["sectors"\] = (.*?)\n', r'asyncio.create_task(_update_scan_job_redis(job_id, sectors=\1))\n', content)

# 4. Refactor initial creation of scan_job
old_init = """    _scan_jobs[job_id] = {
        "status": "running",
        "progress": "正在扫描A股市场板块轮动...",
        "result": None,
        "sectors": [],
        "error": None,
        "created_at": datetime.now().isoformat(),
    }"""
new_init = """    asyncio.create_task(_update_scan_job_redis(job_id, 
        status="running",
        progress="正在扫描A股市场板块轮动...",
        result=None,
        sectors=[],
        error=None,
        created_at=datetime.now().isoformat()
    ))"""
content = content.replace(old_init, new_init)

# 5. Refactor polling get_scan_status
old_poll = """    job = _scan_jobs.get(job_id)
    if not job:"""
new_poll = """    job = await _get_scan_job_redis(job_id)
    if not job:"""
content = content.replace(old_poll, new_poll)

with open(filepath, "w") as f:
    f.write(content)
print("Refactored successfully")
