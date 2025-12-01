from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import httpx
import asyncio
import random
from typing import Dict, List

app = FastAPI()

# Thread-safe storage using asyncio
storage: Dict[str, str] = {}
storage_lock = asyncio.Lock()

# Configuration
IS_LEADER = os.getenv('IS_LEADER', 'false').lower() == 'true'
FOLLOWERS = os.getenv('FOLLOWERS', '').split(',') if os.getenv('FOLLOWERS') else []
WRITE_QUORUM = int(os.getenv('WRITE_QUORUM', '1'))
MIN_DELAY = int(os.getenv('MIN_DELAY', '0'))
MAX_DELAY = int(os.getenv('MAX_DELAY', '1000'))


class WriteRequest(BaseModel):
    key: str
    value: str


class ReplicateRequest(BaseModel):
    key: str
    value: str


async def replicate_to_follower(follower_url: str, key: str, value: str) -> bool:
    """Replicate a key-value pair to a single follower with random delay"""
    # Simulate network lag
    delay = random.randint(MIN_DELAY, MAX_DELAY) / 1000.0
    await asyncio.sleep(delay)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f'http://{follower_url}/replicate',
                json={'key': key, 'value': value}
            )
            return response.status_code == 200
    except Exception as e:
        print(f"Failed to replicate to {follower_url}: {e}")
        return False


async def replicate_to_followers(key: str, value: str) -> bool:
    """Replicate to all followers concurrently and wait for quorum"""
    if not FOLLOWERS:
        return True

    # Create tasks for all followers concurrently
    tasks = [replicate_to_follower(follower, key, value) for follower in FOLLOWERS]

    confirmations = 0
    # Process results as they complete
    for coro in asyncio.as_completed(tasks):
        try:
            success = await coro
            if success:
                confirmations += 1
                # Early exit if quorum reached
                if confirmations >= WRITE_QUORUM:
                    return True
        except Exception as e:
            print(f"Exception during replication: {e}")

    return confirmations >= WRITE_QUORUM


@app.post("/write")
async def write(request: WriteRequest):
    """Write endpoint - only leader accepts writes"""
    if not IS_LEADER:
        raise HTTPException(status_code=403, detail="Only leader accepts writes")

    # Write to leader storage (thread-safe)
    async with storage_lock:
        storage[request.key] = request.value

    # Replicate to followers with semi-synchronous replication
    quorum_reached = await replicate_to_followers(request.key, request.value)

    if quorum_reached:
        return {"status": "success", "key": request.key, "value": request.value}
    else:
        raise HTTPException(status_code=500, detail="Quorum not reached")


@app.get("/read")
async def read(key: str):
    async with storage_lock:
        value = storage.get(key)

    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")

    return {"key": key, "value": value}


@app.post("/replicate")
async def replicate(request: ReplicateRequest):
    if IS_LEADER:
        raise HTTPException(status_code=403, detail="Leader does not accept replication")

    # Write to follower storage (thread-safe)
    async with storage_lock:
        storage[request.key] = request.value

    return {"status": "success"}


@app.get("/dump")
async def dump():
    async with storage_lock:
        return dict(storage)


@app.get("/health")
async def health():
    return {"status": "healthy", "is_leader": IS_LEADER}


if __name__ == '__main__':
    import uvicorn

    port = int(os.getenv('PORT', '5000'))
    uvicorn.run(app, host='0.0.0.0', port=port)