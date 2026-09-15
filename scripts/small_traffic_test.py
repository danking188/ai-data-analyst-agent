#!/usr/bin/env python3
"""Read-only small-traffic acceptance test for a deployed DataTrace instance."""

from __future__ import annotations

import argparse
import concurrent.futures
import http.cookies
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import NamedTuple

SENSITIVE_REDIRECT_HEADERS = ("Authorization", "Cookie", "X-CSRF-Token", "Origin")


def origin_identity(url: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    default_port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or default_port


def strip_sensitive_headers(request: urllib.request.Request) -> None:
    sensitive = {header.lower() for header in SENSITIVE_REDIRECT_HEADERS}
    for header_store in (request.headers, request.unredirected_hdrs):
        for header in list(header_store):
            if header.lower() in sensitive:
                del header_store[header]


class SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent cookies and bearer tokens from crossing an origin boundary on redirects."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and origin_identity(req.full_url) != origin_identity(newurl):
            strip_sensitive_headers(redirected)
        return redirected


URL_OPENER = urllib.request.build_opener(SameOriginRedirectHandler())


class Target(NamedTuple):
    name: str
    url: str
    authenticated: bool = False


@dataclass(frozen=True)
class Sample:
    target: str
    status: int
    latency_ms: float
    error: str | None = None


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def api_root(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/api/v1") else f"{normalized}/api/v1"


def validate_base_url(base_url: str) -> None:
    parsed = urllib.parse.urlsplit(base_url)
    origin_identity(base_url)
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("non-local targets must use HTTPS")


def platform_headers(token_env: str | None) -> dict[str, str]:
    if not token_env:
        return {}
    token = os.getenv(token_env, "")
    if not token:
        raise ValueError(f"platform token environment variable is empty: {token_env}")
    return {"Authorization": f"Bearer {token}"}


def request(
    target: Target,
    *,
    timeout_seconds: float,
    cookie: str | None,
    headers: dict[str, str],
) -> Sample:
    request_headers = {**headers, "User-Agent": "datatrace-small-traffic-test/1.0"}
    if target.authenticated and cookie:
        request_headers["Cookie"] = cookie
    started = time.perf_counter()
    status = 0
    error: str | None = None
    try:
        req = urllib.request.Request(target.url, headers=request_headers)
        with URL_OPENER.open(req, timeout=timeout_seconds) as response:
            status = response.status
            response.read(1024)
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = f"HTTP {exc.code}"
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    latency_ms = (time.perf_counter() - started) * 1000
    return Sample(target=target.name, status=status, latency_ms=round(latency_ms, 3), error=error)


def login(
    root: str,
    *,
    username: str,
    password: str,
    timeout_seconds: float,
    headers: dict[str, str],
) -> str:
    payload = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{root}/auth/login",
        data=payload,
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    with URL_OPENER.open(req, timeout=timeout_seconds) as response:
        response.read(1024)
        raw_cookies = response.headers.get_all("Set-Cookie", [])
    cookies: list[str] = []
    for raw_cookie in raw_cookies:
        parsed = http.cookies.SimpleCookie()
        parsed.load(raw_cookie)
        cookies.extend(f"{name}={morsel.value}" for name, morsel in parsed.items())
    if not cookies:
        raise RuntimeError("login succeeded without a session cookie")
    return "; ".join(cookies)


def summarize(samples: list[Sample], elapsed_seconds: float) -> dict[str, object]:
    failures = [sample for sample in samples if sample.status < 200 or sample.status >= 400]
    latencies = [sample.latency_ms for sample in samples]
    endpoint_latencies: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        endpoint_latencies[sample.target].append(sample.latency_ms)
    endpoints = {
        name: {
            "requests": len(values),
            "p50_ms": round(percentile(values, 0.50), 3),
            "p95_ms": round(percentile(values, 0.95), 3),
            "max_ms": round(max(values), 3),
        }
        for name, values in sorted(endpoint_latencies.items())
    }
    return {
        "requests": len(samples),
        "failures": len(failures),
        "error_rate": round(len(failures) / len(samples), 6) if samples else 1.0,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "throughput_rps": round(len(samples) / elapsed_seconds, 3) if elapsed_seconds else 0.0,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3) if latencies else 0.0,
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "status_counts": dict(sorted(Counter(sample.status for sample in samples).items())),
        "endpoints": endpoints,
        "sample_errors": [asdict(sample) for sample in failures[:5]],
    }


def self_test() -> int:
    assert percentile([1, 2, 3, 4], 0.50) == 2
    assert percentile([1, 2, 3, 4], 0.95) == 4
    assert api_root("https://example.test") == "https://example.test/api/v1"
    assert api_root("https://example.test/api/v1/") == "https://example.test/api/v1"
    assert origin_identity("https://EXAMPLE.test/path") == ("https", "example.test", 443)
    assert origin_identity("https://example.test:443/other") == (
        "https",
        "example.test",
        443,
    )
    redirect_source = urllib.request.Request(
        "https://example.test/start",
        headers={
            "Authorization": "Bearer example",
            "Cookie": "session=example",
            "X-CSRF-Token": "example",
            "Origin": "https://example.test",
        },
    )
    redirected = SameOriginRedirectHandler().redirect_request(
        redirect_source,
        None,
        302,
        "Found",
        {},
        "https://objects.example.test/report",
    )
    assert redirected is not None
    assert not {
        name.lower() for name, _ in redirected.header_items()
    }.intersection({header.lower() for header in SENSITIVE_REDIRECT_HEADERS})
    validate_base_url("http://127.0.0.1:7860")
    try:
        validate_base_url("http://example.test")
    except ValueError:
        pass
    else:
        raise AssertionError("insecure remote URL was accepted")
    print("small traffic test self-check passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Deployment origin or API root")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=2000.0)
    parser.add_argument("--min-throughput-rps", type=float, default=2.0)
    parser.add_argument("--require-authenticated", action="store_true")
    parser.add_argument(
        "--platform-token-env",
        help="Name of an environment variable containing an outer platform bearer token",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.base_url:
        raise SystemExit("--base-url is required")
    if args.requests < 1 or args.concurrency < 1 or args.concurrency > 64:
        raise SystemExit("requests must be positive and concurrency must be between 1 and 64")
    if not 0 <= args.max_error_rate <= 1:
        raise SystemExit("--max-error-rate must be between 0 and 1")

    validate_base_url(args.base_url)
    root = api_root(args.base_url)
    headers = platform_headers(args.platform_token_env)
    username = os.getenv("LOGIN_USERNAME", "")
    password = os.getenv("LOGIN_PASSWORD", "")
    if bool(username) != bool(password):
        raise SystemExit("LOGIN_USERNAME and LOGIN_PASSWORD must be supplied together")
    if args.require_authenticated and not username:
        raise SystemExit("authenticated traffic is required but login credentials are missing")

    cookie = None
    if username:
        cookie = login(
            root,
            username=username,
            password=password,
            timeout_seconds=args.timeout_seconds,
            headers=headers,
        )

    targets = [
        Target("health", f"{root}/health"),
        Target("readiness", f"{root}/health/ready"),
    ]
    if cookie:
        targets.extend(
            [
                Target("session", f"{root}/auth/session", authenticated=True),
                Target("capabilities", f"{root}/system/capabilities", authenticated=True),
            ]
        )

    for target in targets:
        warmup = request(
            target,
            timeout_seconds=args.timeout_seconds,
            cookie=cookie,
            headers=headers,
        )
        if warmup.status < 200 or warmup.status >= 400:
            raise SystemExit(f"warmup failed for {target.name}: {warmup.error or warmup.status}")

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                request,
                targets[index % len(targets)],
                timeout_seconds=args.timeout_seconds,
                cookie=cookie,
                headers=headers,
            )
            for index in range(args.requests)
        ]
        samples = [future.result() for future in concurrent.futures.as_completed(futures)]
    elapsed = time.perf_counter() - started
    report = summarize(samples, elapsed)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    latency = report["latency_ms"]
    assert isinstance(latency, dict)
    passed = (
        float(report["error_rate"]) <= args.max_error_rate
        and float(latency["p95"]) <= args.max_p95_ms
        and float(report["throughput_rps"]) >= args.min_throughput_rps
    )
    if not passed:
        print("small traffic acceptance thresholds failed", file=sys.stderr)
        return 1
    print("small traffic acceptance thresholds passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
