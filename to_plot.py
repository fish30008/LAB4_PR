import json
import glob
import matplotlib.pyplot as plt

files = sorted(glob.glob("perf_results_q*.json"))

quorums = []
avg_lat = []
med_lat = []
p95_lat = []
fails = []

for index, f in enumerate(files):
    with open(f) as fp:
        data = json.load(fp)
        q = index+1
        quorums.append(q)

        m = data["metrics"]
        avg_lat.append(m["avg_latency"])
        med_lat.append(m["median_latency"])
        p95_lat.append(m["p95_latency"])
        fails.append(m["fails"])

# --- Plot Latencies ---
plt.figure(figsize=(10,6))
plt.plot(quorums, avg_lat, marker='o', label="avg")
plt.plot(quorums, med_lat, marker='o', label="median")
# plt.plot(quorums, p95_lat, marker='o', label="p95")

plt.title("Latency vs Write Quorum")
plt.xlabel("Write Quorum")
plt.ylabel("Latency (seconds)")
plt.grid(True)
plt.legend()
plt.show()
plt.savefig("performance.png")


