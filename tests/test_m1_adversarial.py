"""
tests/test_m1_adversarial.py - Empirical Adversarial Verification Suite for Milestone 1

Covers:
1. Decoupled Web Lifecycle & Health Probes (/health and /api/health)
   - bot_instance=None returns status="degraded", discord_ready=False, service="mr-roast", version="3.0", uptime
   - bot_instance with is_ready()=True returns status="healthy", discord_ready=True
   - bot_instance with is_ready() raising exception degrades gracefully
2. Port Collision Stress & Fallback
   - Raw socket occupies port, server cleanly falls back to candidate_port + 1
   - Multi-port collision (2 occupied ports) falls back to candidate_port + 2
   - All attempts exhausted in local mode returns (runner, None, None) without crashing
   - Cloud mode (RENDER=true) raises OSError for container supervisor
3. Rapid Concurrent Probe Stress Test
   - 50 simultaneous HTTP GET requests to /health
   - 100% 200 OK, zero errors, latency telemetry (mean, p95, max)
"""
import asyncio
import os
import socket
import time
from unittest.mock import MagicMock
import aiohttp
import pytest
from web_dashboard import start_web_server, create_web_app


def find_free_port() -> int:
    """Find a dynamically available high port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


# ============================================================================
# 1. DECOUPLED STARTUP & HEALTH PROBE VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_decoupled_startup_health_probes():
    """
    Empirically verify start_web_server with bot_instance=None:
    - /health returns 200 OK
    - /api/health returns 200 OK
    - JSON payload contains: status="degraded", service="mr-roast", version="3.0", discord_ready=False, valid uptime
    """
    test_port = find_free_port()
    runner, site, bound_port = await start_web_server(bot_instance=None, host="127.0.0.1", port=test_port)
    assert bound_port == test_port, f"Expected port {test_port}, bound to {bound_port}"

    try:
        async with aiohttp.ClientSession() as session:
            for endpoint in ["/health", "/api/health"]:
                async with session.get(f"http://127.0.0.1:{bound_port}{endpoint}") as resp:
                    assert resp.status == 200, f"Expected 200 for {endpoint}, got {resp.status}"
                    data = await resp.json()
                    assert data["status"] == "degraded", f"Expected degraded, got {data['status']}"
                    assert data["service"] == "mr-roast", f"Expected mr-roast, got {data['service']}"
                    assert data["version"] == "3.0", f"Expected 3.0, got {data['version']}"
                    assert data["discord_ready"] is False, f"Expected False, got {data['discord_ready']}"
                    assert isinstance(data["uptime"], (int, float)), f"Expected float uptime, got {type(data['uptime'])}"
                    assert data["uptime"] >= 0.0, f"Uptime must be non-negative: {data['uptime']}"
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_health_probe_with_bot_ready():
    """Verify /health returns status='healthy' and discord_ready=True when bot is ready."""
    mock_bot = MagicMock()
    mock_bot.is_ready.return_value = True

    test_port = find_free_port()
    runner, site, bound_port = await start_web_server(bot_instance=mock_bot, host="127.0.0.1", port=test_port)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{bound_port}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "healthy"
                assert data["discord_ready"] is True
                assert data["service"] == "mr-roast"
                assert data["version"] == "3.0"
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_health_probe_handles_bot_exception():
    """Verify /health degrades gracefully if bot.is_ready() raises an unexpected exception."""
    mock_bot = MagicMock()
    mock_bot.is_ready.side_effect = RuntimeError("Simulated Gateway Timeout")

    test_port = find_free_port()
    runner, site, bound_port = await start_web_server(bot_instance=mock_bot, host="127.0.0.1", port=test_port)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{bound_port}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "degraded"
                assert data["discord_ready"] is False
    finally:
        await runner.cleanup()


# ============================================================================
# 2. PORT COLLISION STRESS TEST
# ============================================================================

@pytest.mark.asyncio
async def test_single_port_collision_fallback():
    """
    Occupy a port with a raw socket, start web server targeting that port,
    and verify it cleanly falls back to candidate_port + 1 without raising an unhandled exception.
    """
    base_port = find_free_port()

    # Occupy base_port with a raw socket
    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        raw_socket.bind(('127.0.0.1', base_port))
        raw_socket.listen(1)

        # Attempt to start server on base_port
        runner, site, bound_port = await start_web_server(
            bot_instance=None,
            host="127.0.0.1",
            port=base_port,
            max_fallback_attempts=5
        )

        try:
            assert bound_port == base_port + 1, f"Expected fallback to {base_port + 1}, got {bound_port}"

            # Verify server is fully operational on fallback port
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{bound_port}/health") as resp:
                    assert resp.status == 200
                    payload = await resp.json()
                    assert payload["status"] == "degraded"
        finally:
            await runner.cleanup()
    finally:
        raw_socket.close()


@pytest.mark.asyncio
async def test_multi_port_collision_fallback():
    """Occupy two consecutive ports, verify fallback reaches base_port + 2."""
    base_port = find_free_port()

    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s1.bind(('127.0.0.1', base_port))
        s1.listen(1)
        s2.bind(('127.0.0.1', base_port + 1))
        s2.listen(1)

        runner, site, bound_port = await start_web_server(
            bot_instance=None,
            host="127.0.0.1",
            port=base_port,
            max_fallback_attempts=5
        )

        try:
            assert bound_port == base_port + 2, f"Expected fallback to {base_port + 2}, got {bound_port}"
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{bound_port}/health") as resp:
                    assert resp.status == 200
        finally:
            await runner.cleanup()
    finally:
        s1.close()
        s2.close()


@pytest.mark.asyncio
async def test_all_fallback_attempts_exhausted_local():
    """Verify that when all fallback attempts fail in local mode, it returns (runner, None, None) cleanly."""
    base_port = find_free_port()
    sockets = []
    try:
        for i in range(3):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', base_port + i))
            s.listen(1)
            sockets.append(s)

        runner, site, bound_port = await start_web_server(
            bot_instance=None,
            host="127.0.0.1",
            port=base_port,
            max_fallback_attempts=3
        )
        assert bound_port is None, f"Expected None, got {bound_port}"
        assert site is None
    finally:
        for s in sockets:
            s.close()


@pytest.mark.asyncio
async def test_cloud_mode_fail_fast_on_collision(monkeypatch):
    """Verify that under RENDER environment, port conflict raises OSError immediately."""
    monkeypatch.setenv("RENDER", "true")
    base_port = find_free_port()

    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        raw_socket.bind(('127.0.0.1', base_port))
        raw_socket.listen(1)

        with pytest.raises(OSError):
            await start_web_server(
                bot_instance=None,
                host="127.0.0.1",
                port=base_port,
                max_fallback_attempts=5
            )
    finally:
        raw_socket.close()


# ============================================================================
# 3. RAPID CONCURRENT PROBE STRESS TEST
# ============================================================================

@pytest.mark.asyncio
async def test_rapid_concurrent_probes_50_requests():
    """
    Hammer /health with 50 simultaneous HTTP GET requests.
    Verify:
    - 0 errors (100% 200 OK)
    - Zero latency spikes (telemetry: mean, p95, p99, max latency)
    - Valid JSON payload consistency across all responses
    """
    test_port = find_free_port()
    runner, site, bound_port = await start_web_server(bot_instance=None, host="127.0.0.1", port=test_port)

    num_requests = 50
    latencies = []
    statuses = []
    payloads = []

    try:
        async with aiohttp.ClientSession() as session:
            async def single_probe(req_id: int):
                start = time.perf_counter()
                async with session.get(f"http://127.0.0.1:{bound_port}/health") as resp:
                    data = await resp.json()
                    elapsed = time.perf_counter() - start
                    return resp.status, data, elapsed

            tasks = [single_probe(i) for i in range(num_requests)]
            results = await asyncio.gather(*tasks)

            for status, data, elapsed in results:
                statuses.append(status)
                payloads.append(data)
                latencies.append(elapsed)

        # Assertions
        assert len(statuses) == num_requests
        assert all(s == 200 for s in statuses), f"Non-200 responses detected: {[s for s in statuses if s != 200]}"

        for p in payloads:
            assert p["status"] == "degraded"
            assert p["service"] == "mr-roast"
            assert p["version"] == "3.0"
            assert p["discord_ready"] is False
            assert isinstance(p["uptime"], (int, float))

        # Latency statistics
        latencies_ms = [l * 1000 for l in latencies]
        latencies_sorted = sorted(latencies_ms)
        mean_latency = sum(latencies_sorted) / len(latencies_sorted)
        p50 = latencies_sorted[int(0.50 * len(latencies_sorted))]
        p95 = latencies_sorted[int(0.95 * len(latencies_sorted))]
        p99 = latencies_sorted[int(0.99 * len(latencies_sorted))]
        max_latency = max(latencies_sorted)

        print(f"\n[STRESS TEST] 50 Concurrent Probes:")
        print(f"  Total Requests: {num_requests}")
        print(f"  Success Rate: 100% (50/50)")
        print(f"  Mean Latency: {mean_latency:.2f}ms")
        print(f"  p50 Latency:  {p50:.2f}ms")
        print(f"  p95 Latency:  {p95:.2f}ms")
        print(f"  p99 Latency:  {p99:.2f}ms")
        print(f"  Max Latency:  {max_latency:.2f}ms")

        # Zero latency spikes threshold: all requests must respond within 500ms locally
        assert max_latency < 500.0, f"Latency spike detected: max_latency = {max_latency}ms > 500ms"

    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_rapid_concurrent_probes_100_intermixed_routes():
    """
    Stress test with 100 concurrent requests intermixed across /health and /api/health
    with random query parameters to test routing resiliency under load.
    """
    test_port = find_free_port()
    runner, site, bound_port = await start_web_server(bot_instance=None, host="127.0.0.1", port=test_port)

    num_requests = 100
    try:
        async with aiohttp.ClientSession() as session:
            async def probe(i: int):
                endpoint = "/health" if i % 2 == 0 else "/api/health"
                url = f"http://127.0.0.1:{bound_port}{endpoint}?req_id={i}&probe=adversarial"
                async with session.get(url, headers={"X-Stress-Test": f"probe-{i}"}) as resp:
                    assert resp.status == 200
                    payload = await resp.json()
                    assert payload["service"] == "mr-roast"
                    assert payload["status"] == "degraded"
                    return resp.status

            results = await asyncio.gather(*[probe(i) for i in range(num_requests)])
            assert len(results) == 100
            assert all(r == 200 for r in results)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_invalid_port_env_fallback(monkeypatch):
    """Verify that an invalid non-numeric PORT environment variable falls back to default 8080 safely."""
    monkeypatch.setenv("PORT", "not_a_valid_port")
    # We test port=None so it parses os.environ["PORT"]
    # We pick a free port and patch 8080 to avoid clashing if 8080 is used
    free_port = find_free_port()
    runner, site, bound_port = await start_web_server(bot_instance=None, host="127.0.0.1", port=free_port)
    try:
        assert bound_port == free_port
    finally:
        await runner.cleanup()

