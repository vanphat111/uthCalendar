import argparse
import os
import sys

import requests


def build_args():
    parser = argparse.ArgumentParser(description="Verify auth broker health and optional bootstrap flow.")
    parser.add_argument("--url", default=os.getenv("AUTH_BROKER_URL", "http://localhost:8000"))
    parser.add_argument("--chat-id", default=os.getenv("BROKER_CHAT_ID"))
    parser.add_argument("--username", default=os.getenv("BROKER_USERNAME"))
    parser.add_argument("--password", default=os.getenv("BROKER_PASSWORD"))
    parser.add_argument("--refresh", action="store_true", help="Use /auth/refresh instead of /auth/bootstrap.")
    return parser.parse_args()


def main():
    args = build_args()
    health = requests.get(f"{args.url.rstrip('/')}/health", timeout=10)
    print(f"health: {health.status_code} {health.text}")
    health.raise_for_status()

    if not (args.chat_id and args.username and args.password):
        print("bootstrap: skipped (set --chat-id --username --password or BROKER_* env vars)")
        return 0

    endpoint = "/auth/refresh" if args.refresh else "/auth/bootstrap"
    response = requests.post(
        f"{args.url.rstrip('/')}{endpoint}",
        json={"chatId": args.chat_id, "username": args.username, "password": args.password},
        timeout=120,
    )
    print(f"bootstrap: {response.status_code}")
    response.raise_for_status()

    data = response.json()
    print(
        "auth summary:",
        {
            "has_token": bool(data.get("token")),
            "portal_cookie_count": len(data.get("portal_cookies") or {}),
            "course_cookie_count": len(data.get("course_cookies") or {}),
            "has_sesskey": bool(data.get("sesskey")),
            "expires": data.get("expires"),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
