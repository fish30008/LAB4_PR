# perf_test.py
import asyncio, time, statistics, os, json
import httpx

LEADER = os.getenv("LEADER", "http://localhost:5000")
FOLLOWERS = os.getenv("FOLLOWERS", "http://localhost:5001,http://localhost:5002,http://localhost:5003,http://localhost:5004,http://localhost:5005").split(",")
NUM_WRITES = int(os.getenv("NUM_WRITES", "100"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "10"))
KEYS = [f"key{i}" for i in range(10)]
WRITE_QUORUM = 52

OUTPUT_FILE = f"perf_results_q{WRITE_QUORUM}.json"


async def write(client, key, value):
    t0 = time.perf_counter()
    try:
        # write to the leader
        r = await client.post(f"{LEADER}/write", json={
            "key": key,
            "value": value
        }, timeout=10.0)
        ok = (r.status_code == 200)
    except:
        ok = False

    # returns execution time aka latency
    t1 = time.perf_counter()
    return (t1 - t0), ok, key, value


async def run_all():
    sem = asyncio.Semaphore(CONCURRENCY)
    results = []

    async with httpx.AsyncClient() as client:

        async def task(i):
            async with sem:
                k = KEYS[i % len(KEYS)]
                v = f"val-{i}-{time.time()}"
                lat, ok, key, value = await write(client, k, v)
                return lat, ok, key, value

        tasks = [asyncio.create_task(task(i)) for i in range(NUM_WRITES)]
        for job in asyncio.as_completed(tasks):
            results.append(await job)

    return results


async def fetch_state(url):
    try:
        async with httpx.AsyncClient() as client:
            ## get all data
            r = await client.get(f"{url}/dump", timeout=5.0)
            return r.json()
    except:
        return {"error": True}


def analyze(results):
    latencies = [lat for lat, ok, _, _ in results if ok]
    # count if for some reason value was not written
    fails = sum(1 for _, ok, _, _ in results if not ok)

    metrics = {
        "requests": len(results),
        "successes": len(latencies),
        "fails": fails
    }

    if latencies:
        metrics["avg_latency"] = statistics.mean(latencies)
        metrics["median_latency"] = statistics.median(latencies)
        metrics["p95_latency"] = statistics.quantiles(latencies, n=100)[94] #
    else:
        metrics["avg_latency"] = None
        metrics["median_latency"] = None
        metrics["p95_latency"] = None

    return metrics


def check_correctness(leader_state, follower_states, results):
    last_written = {}
    for _, ok, key, value in results:
        if ok:
            last_written[key] = value

    mismatches = {}
    for f_url, state in follower_states.items():
        for key, expected in last_written.items():
            actual = state.get(key)
            if actual != expected:
                mismatches.setdefault(f_url, {})[key] = {
                    "expected": expected,
                    "actual": actual
                }
    return mismatches


def main():
    results = asyncio.run(run_all())
    metrics = analyze(results)

    # fetch states
    leader_state = asyncio.run(fetch_state(LEADER))
    follower_states = {
        f: asyncio.run(fetch_state(f)) for f in FOLLOWERS
    }

    correctness = check_correctness(leader_state, follower_states, results)

    output = {
        "write_quorum": WRITE_QUORUM,
        "metrics": metrics,
        "leader_state": leader_state,
        "followers": follower_states,
        "correctness_mismatches": correctness,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
