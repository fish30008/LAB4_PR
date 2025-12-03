# Distributed Key-Value Store with Leader-Follower Replication

## Overview

This project implements a distributed key-value store with leader-follower replication architecture, featuring configurable write quorums and simulated network delays. The system consists of two main components:

1. **FastAPI-based server** - A distributed node that can act as either a leader or follower
2. **Performance testing script** - A comprehensive test suite for evaluating system performance and correctness

## Architecture

### System Design

- **Leader-Follower Model**: Only leader nodes accept write operations; followers handle replication requests
- **Quorum-based Consistency**: Configurable write quorum ensures data durability
- **Thread-safe Storage**: Uses asyncio locks to prevent race conditions
- **Simulated Network Delays**: Configurable delay ranges for realistic testing

### Key Features

- **Dynamic Role Assignment**: Nodes configured as leader/follower via environment variables
- **Concurrent Replication**: Asynchronous replication to multiple followers
- **Health Monitoring**: Built-in health check endpoints
- **Data Inspection**: `/dump` endpoint for complete data inspection
- **Performance Testing**: Comprehensive test suite with correctness verification

## Components

### 1. FastAPI Server (`app.py`)

#### Endpoints

| Endpoint | Method | Description | Access |
|----------|--------|-------------|---------|
| `/write` | POST | Write key-value pair (leader only) | Leader |
| `/read` | GET | Read value by key | All nodes |
| `/replicate` | POST | Internal replication endpoint | Followers only |
| `/dump` | GET | Get all stored data | All nodes |
| `/health` | GET | Health check with role info | All nodes |

#### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `IS_LEADER` | `false` | Set to `true` for leader node |
| `FOLLOWERS` | `""` | Comma-separated follower addresses |
| `WRITE_QUORUM` | `1` | Minimum followers for successful write |
| `MIN_DELAY` | `0` | Minimum network delay in milliseconds |
| `MAX_DELAY` | `1000` | Maximum network delay in milliseconds |
| `PORT` | `5000` | Server port |

### 2. Performance Test (`perf_test.py`)

#### Features
- Configurable concurrent write operations
- Latency measurement (average, median, p95)
- Correctness verification across all nodes
- Results export to JSON format

#### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `LEADER` | `http://localhost:5000` | Leader node URL |
| `FOLLOWERS` | Comma-separated URLs | Follower node URLs |
| `NUM_WRITES` | `100` | Number of write operations |
| `CONCURRENCY` | `10` | Concurrent requests |
| `WRITE_QUORUM` | `5` | Expected write quorum |

## Implementation Details

### Data Structures

```python
# Thread-safe storage
storage: Dict[str, str] = {}
storage_lock = asyncio.Lock()
```

### Replication Strategy

1. **Leader receives write request**
2. **Local write** with thread-safe lock
3. **Concurrent replication** to all followers
4. **Quorum checking** with early exit optimization
5. **Response based on quorum achievement**

### Network Delay Simulation

```python
delay = random.randint(MIN_DELAY, MAX_DELAY) / 1000.0
await asyncio.sleep(delay)
```

## Deployment

### Docker Compose Example

```yaml
version: '3.8'
services:
  leader:
    build: .
    environment:
      - IS_LEADER=true
      - FOLLOWERS=follower1:5001,follower2:5002,follower3:5003
      - WRITE_QUORUM=2
      - MIN_DELAY=50
      - MAX_DELAY=300
    ports:
      - "5000:5000"

  follower1:
    build: .
    environment:
      - IS_LEADER=false
      - PORT=5001
```

### Running the System

```bash
# Build and start containers
docker-compose up --build

# Run performance test
export LEADER="http://localhost:5000"
export FOLLOWERS="http://localhost:5001,http://localhost:5002"
python perf_test.py
```

## Performance Characteristics

### Factors Affecting Performance

1. **Write Quorum Size**: Higher quorum → higher latency, better durability
2. **Network Delays**: Simulated delays impact replication time
3. **Concurrency Level**: More concurrent requests increase throughput
4. **Number of Followers**: More followers increase replication overhead

### Expected Behavior

- **Linearizability**: All successful writes are visible to subsequent reads
- **Eventual Consistency**: With sufficient quorum, all nodes eventually converge
- **Fault Tolerance**: System operates with failed followers as long as quorum is met

## Testing Results

The performance test generates a JSON report including:

1. **Latency Metrics**: Average, median, and p95 latencies
2. **Success/Failure Rates**: Request completion statistics
3. **State Comparison**: Data consistency across all nodes
4. **Correctness Analysis**: Identifies any replication mismatches

Example output structure:
```json
{
  "write_quorum": 3,
  "metrics": {
    "requests": 100,
    "successes": 100,
    "fails": 0,
    "avg_latency": 0.234,
    "median_latency": 0.198,
    "p95_latency": 0.456
  },
  "correctness_mismatches": {}
}
```

