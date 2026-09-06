"""
tests/run_adversarial_standalone.py - Standalone Verification Harness for Milestone 1
"""
import asyncio
import os
import socket
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
from web_dashboard import start_web_server

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

async def run_harness():
    print("=== TEST 1: DECOUPLED STARTUP & HEALTH PROBES ===")
    port1 = get_free_port()
    runner1, site1, bound1 = await start_web_server(bot_instance=None, host="127.0.0.1", port=port1)
    try:
        async with aiohttp.ClientSession() as session:
            for path in ["/health", "/api/health"]:
                async with session.get(f"http://127.0.0.1:{bound1}{path}") as resp:
                    data = await resp.json()
                    st = data.get("status")
                    srv = data.get("service")
                    ver = data.get("version")
                    rdy = data.get("discord_ready")
                    up = data.get("uptime")
                    print(f"Path: {path} | HTTP Status: {resp.status} | Payload: {data}")
                    assert resp.status == 200, f"Expected 200, got {resp.status}"
                    assert st == "degraded", f"Expected degraded, got {st}"
                    assert srv == "mr-roast", f"Expected mr-roast, got {srv}"
                    assert ver == "3.0", f"Expected 3.0, got {ver}"
                    assert rdy is False, f"Expected False, got {rdy}"
                    assert isinstance(up, float), f"Expected float uptime, got {type(up)}"
                    assert up >= 0.0, f"Expected positive uptime, got {up}"
    finally:
        await runner1.cleanup()

    print("\n=== TEST 2: PORT COLLISION STRESS TEST ===")
    port2 = get_free_port()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port2))
    sock.listen(1)
    print(f"Raw socket occupying port: {port2}")
    try:
        runner2, site2, bound2 = await start_web_server(bot_instance=None, host="127.0.0.1", port=port2, max_fallback_attempts=5)
        try:
            print(f"Requested port: {port2} | Fallback bound port: {bound2}")
            assert bound2 == port2 + 1, f"Expected fallback {port2 + 1}, got {bound2}"
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{bound2}/health") as resp:
                    data = await resp.json()
                    print(f"Fallback probe HTTP Status: {resp.status} | Payload: {data}")
                    assert resp.status == 200
                    assert data.get("status") == "degraded"
        finally:
            await runner2.cleanup()
    finally:
        sock.close()

    print("\n=== TEST 3: RAPID CONCURRENT PROBES (50 SIMULTANEOUS GETs) ===")
    port3 = get_free_port()
    runner3, site3, bound3 = await start_web_server(bot_instance=None, host="127.0.0.1", port=port3)
    try:
        async with aiohttp.ClientSession() as session:
            async def get_probe(i):
                t0 = time.perf_counter()
                async with session.get(f"http://127.0.0.1:{bound3}/health") as resp:
                    payload = await resp.json()
                    dt = (time.perf_counter() - t0) * 1000
                    return resp.status, dt, payload

            tasks = [get_probe(i) for i in range(50)]
            res = await asyncio.gather(*tasks)

            statuses = [r[0] for r in res]
            times = sorted([r[1] for r in res])
            mean_t = sum(times) / len(times)
            p50_t = times[int(0.50 * len(times))]
            p95_t = times[int(0.95 * len(times))]
            p99_t = times[int(0.99 * len(times))]
            max_t = max(times)

            print(f"Concurrent requests: {len(statuses)}")
            print(f"200 OK count:        {statuses.count(200)}")
            print(f"Error count:         {len(statuses) - statuses.count(200)}")
            print(f"Mean latency:        {mean_t:.2f}ms")
            print(f"p50 latency:         {p50_t:.2f}ms")
            print(f"p95 latency:         {p95_t:.2f}ms")
            print(f"p99 latency:         {p99_t:.2f}ms")
            print(f"Max latency:         {max_t:.2f}ms")
            assert all(s == 200 for s in statuses), "Some requests failed"
            assert max_t < 500.0, f"Max latency too high: {max_t}ms"
    finally:
        await runner3.cleanup()

    print("\nALL ADVERSARIAL CHALLENGE HARNESSES PASSED EMPIRICALLY!")

if __name__ == "__main__":
    asyncio.run(run_harness())
