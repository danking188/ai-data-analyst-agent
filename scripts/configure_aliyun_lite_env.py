#!/usr/bin/env python3
"""Create a locked-down Aliyun lightweight production env file."""

from __future__ import annotations

import argparse
import os
import secrets
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", help="Public hostname without a URL scheme")
    parser.add_argument(
        "--enable-registration",
        action="store_true",
        help="Allow visitors to create isolated user accounts",
    )
    args = parser.parse_args()

    domain = args.domain.strip().lower()
    if not domain or "/" in domain or ":" in domain:
        raise SystemExit("domain must be a bare hostname")

    repo_root = Path(__file__).resolve().parent.parent
    profile_dir = repo_root / "deploy" / "aliyun-lite"
    example_path = profile_dir / "env.example"
    env_path = profile_dir / ".env"
    values = {
        "DOMAIN": domain,
        "JWT_SECRET": secrets.token_urlsafe(48),
        "LOGIN_USERNAME": "analyst",
        "LOGIN_PASSWORD": secrets.token_urlsafe(24),
        "REGISTRATION_ENABLED": "true" if args.enable_registration else "false",
        "CORS_ORIGINS": f"https://{domain}",
        "TRUSTED_HOSTS": f"{domain},127.0.0.1,app",
    }

    rendered: list[str] = []
    for line in example_path.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        rendered.append(f"{key}={values[key]}" if key in values else line)

    profile_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", dir=profile_dir, text=True)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("\n".join(rendered) + "\n")
        os.replace(temporary_path, env_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    print(f"Created {env_path} with mode 600 for user analyst.")


if __name__ == "__main__":
    main()
