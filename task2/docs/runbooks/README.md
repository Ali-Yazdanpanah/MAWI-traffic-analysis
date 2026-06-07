# Task II — Capture method runbooks

Step-by-step guides for each telemetry **collection** method. All paths assume you are inside the Docker container (`cd /p4`) unless noted.

Homework comparison notebook (Task III): [`../../../notebooks/task3_comparison.ipynb`](../../../notebooks/task3_comparison.ipynb).

| Method | Runbook | P4 export | Collector | Output |
|--------|---------|-----------|-----------|--------|
| **1. Live in-band sniff** | [live-inband-sniff/runbook.md](live-inband-sniff/runbook.md) | in-band trailer | Scapy on h2 | `data/capture.jsonl` |
| **2. h2 tcpdump** | [h2-tcpdump/runbook.md](h2-tcpdump/runbook.md) | in-band trailer | tcpdump on h2 | `data/capture.pcap` |
| **3. Switch port pcap** | [switch-port-pcap/runbook.md](switch-port-pcap/runbook.md) | in-band trailer | BMv2 `pcaps/s1-eth2.pcap` | port-2 pcap |
| **4. UDP INT sniff** | [udp-int-sniff/runbook.md](udp-int-sniff/runbook.md) | UDP INT reports | Scapy UDP on h2 | `data/capture.jsonl` |
| **5. Register readout** | [register-readout/runbook.md](register-readout/runbook.md) | *(none)* | Thrift / gRPC | `data/registers*.json` |

Shared setup: [RUN_WITH_MAWI.md](../RUN_WITH_MAWI.md) · Architecture: [task2/README.md](../../README.md#getting-telemetry-out-of-the-data-plane)
