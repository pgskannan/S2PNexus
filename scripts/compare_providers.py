#!/usr/bin/env python3
"""Compare Gemini vs. Ollama responses to the same prompt against a running S2PNexus backend.

Uses the existing runtime provider-override endpoint (PUT /api/v1/ai/provider, DB-backed,
no restart needed) to flip providers between calls, then restores whatever provider was
active before the script ran.

Usage:
    python scripts/compare_providers.py --prompt "Summarize the PO approval workflow"

Requires the local docker-compose stack running (backend + ollama at minimum) and an
admin user to log in as (provider override is admin-only).
"""

from __future__ import annotations

import argparse
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"
PROVIDERS = ["ollama", "gemini"]


def login(base_url: str, email: str, password: str) -> str:
    resp = requests.post(
        f"{base_url}/auth/login",
        data={"username": email, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_current_provider(base_url: str, headers: dict) -> str:
    resp = requests.get(f"{base_url}/ai/provider", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["current_provider"]


def set_provider(base_url: str, headers: dict, provider: str) -> None:
    resp = requests.put(
        f"{base_url}/ai/provider",
        json={"provider": provider},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()


def chat(base_url: str, headers: dict, prompt: str, max_tokens: int, timeout: int) -> tuple[str, int]:
    started = time.perf_counter()
    resp = requests.post(
        f"{base_url}/ai/chat",
        json={"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        headers=headers,
        timeout=timeout,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    resp.raise_for_status()
    return resp.json().get("text", ""), elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default="admin@s2pnexus.com", help="Admin user email")
    parser.add_argument("--password", default="changeme", help="Admin user password")
    parser.add_argument("--prompt", required=True, help="Prompt to send to both providers")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=PROVIDERS,
        help="Providers to compare, in order (default: ollama gemini)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=200,
        help="Cap generation length -- keeps CPU-only Ollama runs from taking minutes (default: 200)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-request timeout in seconds (default: 300, generous for cold-loaded CPU inference)",
    )
    args = parser.parse_args()

    try:
        token = login(args.base_url, args.email, args.password)
    except requests.HTTPError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        print("Pass --email/--password for an admin account, or create one first.", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    original_provider = get_current_provider(args.base_url, headers)

    print(f"Prompt: {args.prompt!r}\n")
    results = []
    try:
        for provider in args.providers:
            set_provider(args.base_url, headers, provider)
            try:
                text, elapsed_ms = chat(args.base_url, headers, args.prompt, args.max_tokens, args.timeout)
                results.append((provider, elapsed_ms, text))
            except requests.HTTPError as exc:
                results.append((provider, None, f"ERROR: {exc}"))
    finally:
        set_provider(args.base_url, headers, original_provider)

    for provider, elapsed_ms, text in results:
        latency = f"{elapsed_ms} ms" if elapsed_ms is not None else "n/a"
        print(f"=== {provider} ({latency}) ===")
        print(text)
        print()

    print(f"(restored provider: {original_provider})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
