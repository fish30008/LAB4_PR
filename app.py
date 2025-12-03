'''For that reason, it is impractical for all followers to be synchronous: any one node
 outage would cause the whole system to grind to a halt. In practice, if you enable syn
chronous replication on a database, it usually means that one of the followers is syn
chronous, and the others are asynchronous. If the synchronous follower becomes
 unavailable or slow, one of the asynchronous followers is made synchronous. This
 guarantees that you have an up-to-date copy of the data on at least two nodes: the
 leader and one synchronous follower. This configuration is sometimes also called
 semi-synchronous
 '''

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import httpx
import asyncio
import random
from typing import Dict, List, Tuple

app = FastAPI()

# Thread-safe to prevent race conditions
storage: Dict[str, str] = {}
storage_lock = asyncio.Lock()

# Configuration from dcoker-compose file
IS_LEADER = os.getenv('IS_LEADER', 'false').lower() == 'true'
FOLLOWERS = os.getenv('FOLLOWERS', '').split(',') if os.getenv('FOLLOWERS') else []
WRITE_QUORUM = int(os.getenv('WRITE_QUORUM', '1'))
MIN_DELAY = int(os.getenv('MIN_DELAY', '0'))
SYNC_TIMEOUT_MS = MAX_DELAY = int(os.getenv('MAX_DELAY', '1000'))

SYNC_FOLLOWERS = os.getenv('SYNC_FOLLOWERS', '').split(',') if os.getenv('SYNC_FOLLOWERS') else []
ASYNC_FOLLOWERS = os.getenv('ASYNC_FOLLOWERS', '').split(',') if os.getenv('ASYNC_FOLLOWERS') else []

print(f'SYNC - > ', SYNC_FOLLOWERS)
print(f'SYNC - > ', ASYNC_FOLLOWERS)


class WriteRequest(BaseModel):
    key: str
    value: str


class ReplicateRequest(BaseModel):
    key: str
    value: str


async def replicate_to_follower(follower_url: str, key: str, value: str, is_sync: bool = False) -> bool:
    delay = random.randint(MIN_DELAY, MAX_DELAY) / 1000.0
    await asyncio.sleep(delay)

    timeout = SYNC_TIMEOUT_MS / 1000.0 if is_sync else 3.0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f'http://{follower_url}/replicate',
                json={'key': key, 'value': value}
            )
            return response.status_code == 200
    except Exception as e:
        print(f"Failed to replicate to {follower_url} (sync={is_sync}): {e}")
        return False
async def replicate_semi_sync(key: str, value: str) -> Tuple[bool, List[str]]:
    failed_sync_followers = []
    # sync part
    sync_tasks = [
        replicate_to_follower(SYNC_FOLLOWERS[0], key, value, is_sync=True)
    ]
    sync_success = False
    for task in asyncio.as_completed(sync_tasks):
        try:
            if await task:
                sync_success = True
                break
        except Exception as e:
            print(f"Sync replication error: {e}")
            continue

    if not sync_success:
        failed_sync_followers = SYNC_FOLLOWERS.copy()

    #async task
    if sync_success and WRITE_QUORUM == 1:
        return True, failed_sync_followers

    if ASYNC_FOLLOWERS:
        async_tasks = [
            replicate_to_follower(follower, key, value, is_sync=False)
            for follower in ASYNC_FOLLOWERS
        ]

        confirmations = 0
        for task in asyncio.as_completed(async_tasks):
            try:
                if await task:
                    confirmations += 1
                    if confirmations >= WRITE_QUORUM - 1:
                        break
            except Exception as e:
                print(f"Async replication error: {e}")

        if confirmations < WRITE_QUORUM - 1:
            return False, failed_sync_followers

    return True, failed_sync_followers



@app.post("/write")
async def write(request: WriteRequest):
    if not IS_LEADER:
        raise HTTPException(status_code=403, detail="Only leader accepts writes")

    async with storage_lock:
        storage[request.key] = request.value

    success, failed_sync_followers = await replicate_semi_sync(request.key, request.value)

    if success:
        response = {
            "status": "success",
            "key": request.key,
            "value": request.value,
            "sync_followers": SYNC_FOLLOWERS,
            "async_followers": ASYNC_FOLLOWERS,
            "write_quorum": WRITE_QUORUM,
            "async_confirmations_needed": max(0, WRITE_QUORUM - 1)
        }
        if failed_sync_followers:
            response["warning"] = f"Some sync followers failed: {failed_sync_followers}"

        return response
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Replication failed. Required sync followers unavailable: {failed_sync_followers}"
        )


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