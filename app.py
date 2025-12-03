from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import httpx
import asyncio
import random
from typing import Dict, List

app = FastAPI()

# Thread-safe to prevent race conditions
storage: Dict[str, str] = {}
storage_lock = asyncio.Lock()

# Configuration from dcoker-compose file
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


# dtypes to not check rep
async def replicate_to_follower(follower_url: str, key: str, value: str) -> bool:
    # Simulate network lag from min to max
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
    if not FOLLOWERS:
        return True

    # Create tasks for all followers concurrently to put them in to thread
    tasks = [replicate_to_follower(follower, key, value) for follower in FOLLOWERS]

    confirmations = 0
    for res in asyncio.as_completed(tasks):
        try:
            success = await res
            # semi - sync bc we don't wait till in all quorums will be replicated data
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
    if not IS_LEADER:
        raise HTTPException(status_code=403, detail="Only leader accepts writes")

    async with storage_lock:
        storage[request.key] = request.value

    quorum_reached = await replicate_to_followers(request.key, request.value)

    if quorum_reached:
        return {"status": "success", "key": request.key, "value": request.value}
    else:
        raise HTTPException(status_code=500, detail="Quorum not reached")


@app.get("/read")
async def read(key: str):
    # thread save read, to not be randomly displayed
    async with storage_lock:
        value = storage.get(key)

    if value is None:
        raise HTTPException(status_code=404, detail="Key error")

    return {"key": key, "value": value}


@app.post("/replicate")
async def replicate(request: ReplicateRequest):
    if IS_LEADER:
        raise HTTPException(status_code=403, detail="Wrong address, this is leader")

    # thread save write
    async with storage_lock:
        storage[request.key] = request.value

    return {"status": "success"}


@app.get("/dump")
async def dump():
    # get all data from storage
    async with storage_lock:
        return dict(storage)


@app.get("/health")
async def health():
    # check if leader is available
    return {"status": "healthy", "is_leader": IS_LEADER}


if __name__ == '__main__':
    import uvicorn

    port = int(os.getenv('PORT', '5000'))
    uvicorn.run(app, host='0.0.0.0', port=port)