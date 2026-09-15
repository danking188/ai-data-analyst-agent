#!/usr/bin/env python3
"""Run a disposable, evidence-producing DataTrace workflow against a deployment."""

from __future__ import annotations

import argparse
import http.cookies
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

TERMINAL_JOB_STATES = {"succeeded", "failed", "cancelled", "blocked"}
SENSITIVE_REDIRECT_HEADERS = ("Authorization", "Cookie", "X-CSRF-Token", "Origin")


def validate_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("non-local targets must use HTTPS")
    return parsed


def origin_identity(url: str) -> tuple[str, str, int | None]:
    parsed = validate_url(url)
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


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float,
        platform_token: str | None = None,
    ) -> None:
        self.root = base_url.rstrip("/")
        if not self.root.endswith("/api/v1"):
            self.root = f"{self.root}/api/v1"
        parsed = validate_url(self.root)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.origin_identity = origin_identity(self.root)
        self.timeout_seconds = timeout_seconds
        self.platform_token = platform_token
        self.cookies: dict[str, str] = {}

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        if path.startswith(("http://", "https://")):
            url = path
            validate_url(url)
        elif path.startswith("/api/v1/"):
            url = f"{self.origin}{path}"
        else:
            url = f"{self.root}{path}"
        request_headers = {"User-Agent": "datatrace-production-workflow-smoke/1.0"}
        same_origin = origin_identity(url) == self.origin_identity
        if self.platform_token and same_origin:
            request_headers["Authorization"] = f"Bearer {self.platform_token}"
        if self.cookies and same_origin:
            request_headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in self.cookies.items()
            )
        if method not in {"GET", "HEAD", "OPTIONS"} and self.cookies and same_origin:
            csrf = self.cookies.get("datatrace_csrf")
            if csrf:
                request_headers["X-CSRF-Token"] = csrf
            request_headers["Origin"] = self.origin
        if payload is not None:
            body = json.dumps(payload).encode()
            content_type = "application/json"
        if content_type:
            request_headers["Content-Type"] = content_type
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, data=body, method=method, headers=request_headers)
        try:
            with URL_OPENER.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                for raw_cookie in response.headers.get_all("Set-Cookie", []):
                    parsed_cookie = http.cookies.SimpleCookie()
                    parsed_cookie.load(raw_cookie)
                    self.cookies.update(
                        {name: morsel.value for name, morsel in parsed_cookie.items()}
                    )
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode(errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
        if not expect_json:
            return raw
        return json.loads(raw) if raw else None

    def login(self, username: str, password: str) -> None:
        self.request("POST", "/auth/login", payload={"username": username, "password": password})
        if "datatrace_session" not in self.cookies:
            raise RuntimeError("login did not return the expected session cookie")


def multipart_upload(filename: str, content: bytes, dataset_name: str) -> tuple[bytes, str]:
    boundary = f"----datatrace-smoke-{uuid.uuid4().hex}"
    chunks = [
        (
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="dataset_name"\r\n\r\n{dataset_name}\r\n'
        ).encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{filename}\"\r\nContent-Type: text/csv\r\n\r\n"
        ).encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def wait_for_job(
    client: ApiClient,
    job_id: str,
    timeout_seconds: float,
    *,
    expected_statuses: frozenset[str] = frozenset({"succeeded"}),
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    while True:
        job = client.request("GET", f"/jobs/{job_id}")
        if job["status"] in TERMINAL_JOB_STATES:
            elapsed = time.monotonic() - started
            if job["status"] not in expected_statuses:
                raise RuntimeError(
                    f"job {job_id} ended as {job['status']}: "
                    f"{json.dumps(job.get('error'), ensure_ascii=False)}"
                )
            return job, elapsed
        if time.monotonic() - started >= timeout_seconds:
            raise TimeoutError(f"job {job_id} did not finish within {timeout_seconds}s")
        time.sleep(0.5)


def build_dataset() -> bytes:
    rows = ["feature,target,segment"]
    for index in range(1, 121):
        target = "yes" if index % 2 else "no"
        segment = ("a", "b", "c")[index % 3]
        rows.append(f"{index},{target},{segment}")
    return ("\n".join(rows) + "\n").encode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--keep-project", action="store_true")
    parser.add_argument(
        "--exercise-llm",
        action="store_true",
        help="Also verify AI narrative and the Assistant plan/confirm/execute loop",
    )
    parser.add_argument(
        "--platform-token-env",
        help="Name of an environment variable containing an outer platform bearer token",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def self_test() -> int:
    client = ApiClient(
        "https://example.test",
        timeout_seconds=1.0,
        platform_token="example-platform-token",
    )
    client.cookies = {"datatrace_session": "example-session"}
    assert client.origin_identity == origin_identity("https://example.test:443/api/v1")
    assert client.origin_identity != origin_identity("https://objects.example.test/report")
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
    try:
        validate_url("http://objects.example.test/report")
    except ValueError:
        pass
    else:
        raise AssertionError("insecure remote download URL was accepted")
    assert frozenset({"blocked"}).issubset(TERMINAL_JOB_STATES)
    print("production workflow smoke self-check passed")
    return 0


def message_by_id(messages: dict[str, Any], message_id: str) -> dict[str, Any]:
    for item in messages.get("items", []):
        if item.get("message_id") == message_id:
            return item
    raise RuntimeError(f"assistant message was not returned after its job completed: {message_id}")


def exercise_llm_workflow(
    client: ApiClient,
    *,
    project_id: str,
    version_id: str,
    run_id: str,
    claim_ids: list[str],
    run_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    capabilities = client.request("GET", "/system/capabilities")
    llm = capabilities.get("llm", {})
    if llm.get("assistant") is not True or llm.get("evidence_narrative") is not True:
        raise RuntimeError("--exercise-llm requested but the deployment does not expose LLM features")

    narrative_job = client.request(
        "POST",
        f"/projects/{project_id}/reports",
        payload={
            "run_id": run_id,
            "format": "ai_narrative",
            "claim_ids": claim_ids,
            "include_code": False,
            "include_evidence": True,
        },
        headers={"Idempotency-Key": f"smoke-ai-narrative-{run_key}"},
    )
    narrative_result, narrative_seconds = wait_for_job(
        client, narrative_job["job_id"], timeout_seconds
    )
    narrative_artifact_id = narrative_result.get("resource_id")
    artifacts = client.request("GET", f"/projects/{project_id}/runs/{run_id}/artifacts")
    narrative_artifact = next(
        (
            item
            for item in artifacts.get("items", [])
            if item.get("artifact_id") == narrative_artifact_id
            and item.get("producer") == "llm_report_narrative"
        ),
        None,
    )
    if narrative_artifact is None or not narrative_artifact.get("result"):
        raise RuntimeError("AI narrative job succeeded without a persisted narrative artifact")

    conversation = client.request(
        "POST",
        f"/projects/{project_id}/assistant/conversations",
        payload={
            "title": f"Release LLM smoke {run_key[:8]}",
            "dataset_version_id": version_id,
        },
        headers={"Idempotency-Key": f"smoke-assistant-conversation-{run_key}"},
    )
    conversation_id = conversation["conversation_id"]

    read_turn = client.request(
        "POST",
        f"/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
        payload={
            "content": (
                "读取当前数据版本的字段和质量问题，只根据工具返回的可引用证据进行总结，"
                "不要运行新的分析。"
            )
        },
        headers={"Idempotency-Key": f"smoke-assistant-read-{run_key}"},
    )
    _, read_seconds = wait_for_job(client, read_turn["job"]["job_id"], timeout_seconds)
    messages = client.request(
        "GET",
        f"/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
    )
    read_message = message_by_id(messages, read_turn["assistant_message"]["message_id"])
    read_calls = read_message.get("tool_calls", [])
    if read_message.get("status") != "completed" or not read_message.get("answer"):
        raise RuntimeError("Assistant read-only turn did not persist a completed structured answer")
    if not read_calls or any(call.get("status") != "succeeded" for call in read_calls):
        raise RuntimeError("Assistant read-only turn did not complete its evidence tools")

    plan_turn = client.request(
        "POST",
        f"/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
        payload={
            "content": (
                "为当前数据集创建并运行二分类分析：target 是目标列，feature 和 segment "
                "是特征；使用分层切分、accuracy 和 f1，并在真正执行前让我确认。"
            )
        },
        headers={"Idempotency-Key": f"smoke-assistant-plan-{run_key}"},
    )
    _, plan_seconds = wait_for_job(
        client,
        plan_turn["job"]["job_id"],
        timeout_seconds,
        expected_statuses=frozenset({"blocked"}),
    )
    messages = client.request(
        "GET",
        f"/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
    )
    plan_message = message_by_id(messages, plan_turn["assistant_message"]["message_id"])
    proposed_calls = [
        call
        for call in plan_message.get("tool_calls", [])
        if call.get("status") == "proposed" and call.get("requires_confirmation") is True
    ]
    if plan_message.get("status") != "awaiting_confirmation" or not plan_message.get("plan"):
        raise RuntimeError("Assistant did not stop at the human confirmation boundary")
    if not proposed_calls:
        raise RuntimeError("Assistant plan did not persist any confirmable tool call")

    confirmation = client.request(
        "POST",
        f"/projects/{project_id}/assistant/messages/{plan_message['message_id']}/confirm",
        payload={
            "decision": "approve",
            "tool_call_ids": [call["tool_call_id"] for call in proposed_calls],
        },
        headers={"Idempotency-Key": f"smoke-assistant-confirm-{run_key}"},
    )
    if not confirmation.get("job"):
        raise RuntimeError("Assistant confirmation did not create a continuation job")
    _, execute_seconds = wait_for_job(
        client, confirmation["job"]["job_id"], timeout_seconds
    )
    messages = client.request(
        "GET",
        f"/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
    )
    source_message = message_by_id(messages, plan_message["message_id"])
    continuation = message_by_id(
        messages, confirmation["assistant_message"]["message_id"]
    )
    approved_ids = {call["tool_call_id"] for call in proposed_calls}
    completed_calls = [
        call
        for call in source_message.get("tool_calls", [])
        if call.get("tool_call_id") in approved_ids
    ]
    if continuation.get("status") != "completed" or not continuation.get("answer"):
        raise RuntimeError("Assistant continuation did not complete after confirmation")
    if len(completed_calls) != len(approved_ids) or any(
        call.get("status") != "succeeded" for call in completed_calls
    ):
        raise RuntimeError("One or more confirmed Assistant actions did not succeed")

    metrics = client.request("GET", f"/projects/{project_id}/assistant/metrics?window_days=1")
    if metrics.get("turn_count", 0) < 3 or metrics.get("tool_succeeded_count", 0) < 1:
        raise RuntimeError("Assistant metrics did not include the verified live turns")
    return {
        "narrative_artifact_id": narrative_artifact_id,
        "conversation_id": conversation_id,
        "read_tool_names": [call["tool_name"] for call in read_calls],
        "confirmed_tool_names": [call["tool_name"] for call in completed_calls],
        "metrics": metrics,
        "timings": {
            "narrative_seconds": round(narrative_seconds, 3),
            "assistant_read_seconds": round(read_seconds, 3),
            "assistant_plan_seconds": round(plan_seconds, 3),
            "assistant_execute_seconds": round(execute_seconds, 3),
        },
    }


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.base_url:
        raise SystemExit("--base-url is required")
    username = os.getenv("LOGIN_USERNAME", "")
    password = os.getenv("LOGIN_PASSWORD", "")
    if not username or not password:
        raise SystemExit("LOGIN_USERNAME and LOGIN_PASSWORD are required")
    platform_token = None
    if args.platform_token_env:
        platform_token = os.getenv(args.platform_token_env, "")
        if not platform_token:
            raise SystemExit(f"platform token is missing from {args.platform_token_env}")

    client = ApiClient(
        args.base_url,
        timeout_seconds=args.timeout_seconds,
        platform_token=platform_token,
    )
    run_key = uuid.uuid4().hex
    timings: dict[str, float] = {}
    project_id: str | None = None
    try:
        client.login(username, password)
        project = client.request(
            "POST",
            "/projects",
            payload={
                "name": f"Release smoke {run_key[:8]}",
                "description": "Disposable production workflow verification",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
            },
            headers={"Idempotency-Key": f"smoke-project-{run_key}"},
        )
        project_id = project["project_id"]

        upload_body, upload_type = multipart_upload(
            "release-smoke.csv", build_dataset(), "Release smoke dataset"
        )
        upload = client.request(
            "POST",
            f"/projects/{project_id}/datasets",
            body=upload_body,
            content_type=upload_type,
            headers={"Idempotency-Key": f"smoke-upload-{run_key}"},
        )
        upload_job, timings["ingestion_seconds"] = wait_for_job(
            client, upload["job_id"], args.timeout_seconds
        )
        version_id = upload_job["resource_id"]

        quality = client.request(
            "POST",
            f"/projects/{project_id}/dataset-versions/{version_id}/quality-scans",
            payload={},
            headers={"Idempotency-Key": f"smoke-quality-{run_key}"},
        )
        _, timings["quality_seconds"] = wait_for_job(
            client, quality["job_id"], args.timeout_seconds
        )

        spec = client.request(
            "POST",
            f"/projects/{project_id}/analysis-specs",
            payload={
                "name": "Release smoke classification",
                "dataset_version_id": version_id,
                "task": "binary_classification",
                "target": "target",
                "prediction_time_description": "Pre-event smoke-test features",
                "split_strategy": "stratified",
                "metrics": ["accuracy", "f1"],
                "included_columns": ["feature", "segment"],
                "excluded_columns": [],
                "random_seed": 42,
                "causal_interpretation_allowed": False,
            },
            headers={"Idempotency-Key": f"smoke-spec-{run_key}"},
        )
        client.request(
            "POST",
            f"/projects/{project_id}/analysis-specs/{spec['spec_id']}/confirm",
            headers={"Idempotency-Key": f"smoke-confirm-{run_key}"},
        )
        run_job = client.request(
            "POST",
            f"/projects/{project_id}/runs",
            payload={
                "analysis_spec_id": spec["spec_id"],
                "dataset_version_id": version_id,
                "run_kind": "full",
            },
            headers={"Idempotency-Key": f"smoke-run-{run_key}"},
        )
        completed_run_job, timings["analysis_seconds"] = wait_for_job(
            client, run_job["job_id"], args.timeout_seconds
        )
        run_id = completed_run_job["resource_id"]
        artifacts = client.request("GET", f"/projects/{project_id}/runs/{run_id}/artifacts")
        claims = client.request("GET", f"/projects/{project_id}/runs/{run_id}/claims")
        if artifacts["total"] < 1 or claims["total"] < 1:
            raise RuntimeError("analysis completed without artifacts and validated claims")
        if any(item["validation_status"] != "passed" for item in claims["items"]):
            raise RuntimeError("analysis returned a claim that did not pass validation")

        report_job = client.request(
            "POST",
            f"/projects/{project_id}/reports",
            payload={
                "run_id": run_id,
                "format": "html",
                "claim_ids": [item["claim_id"] for item in claims["items"]],
                "include_code": True,
                "include_evidence": True,
            },
            headers={"Idempotency-Key": f"smoke-report-{run_key}"},
        )
        completed_report_job, timings["report_seconds"] = wait_for_job(
            client, report_job["job_id"], args.timeout_seconds
        )
        artifact_id = completed_report_job["resource_id"]
        download = client.request(
            "POST",
            f"/projects/{project_id}/artifacts/{artifact_id}/download",
            headers={"Idempotency-Key": f"smoke-download-{run_key}"},
        )
        downloaded = client.request("GET", download["download_url"], expect_json=False)
        if b"AI Data Analyst" not in downloaded:
            raise RuntimeError("downloaded report did not contain the expected marker")

        llm_verification = None
        if args.exercise_llm:
            llm_verification = exercise_llm_workflow(
                client,
                project_id=project_id,
                version_id=version_id,
                run_id=run_id,
                claim_ids=[item["claim_id"] for item in claims["items"]],
                run_key=run_key,
                timeout_seconds=args.timeout_seconds,
            )

        print(
            json.dumps(
                {
                    "status": "passed",
                    "project_id": project_id,
                    "dataset_version_id": version_id,
                    "run_id": run_id,
                    "artifact_count": artifacts["total"],
                    "validated_claim_count": claims["total"],
                    "report_size_bytes": len(downloaded),
                    "timings": {key: round(value, 3) for key, value in timings.items()},
                    "llm_verification": llm_verification,
                    "project_archived": not args.keep_project,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if project_id and not args.keep_project:
            try:
                client.request("DELETE", f"/projects/{project_id}", expect_json=False)
            except (OSError, RuntimeError, TimeoutError, urllib.error.URLError, ValueError) as exc:
                print(
                    f"warning: disposable project could not be archived: {exc}",
                    file=os.sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
