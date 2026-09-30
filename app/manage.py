"""Prepare server configuration and display setup keys only in the local terminal."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit


def prepare(path: Path, base_url: str) -> None:
    """Create a private configuration file without overwriting an existing file."""
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.username or parsed.password or "\\" in base_url
            or any(c.isspace() or ord(c) < 32 for c in base_url)):
        raise ValueError("Enter a valid HTTP/HTTPS root URL.")
    token = secrets.token_urlsafe(48)
    content = (f"APP_SECRET_KEY={secrets.token_urlsafe(48)}\n"
               f"APP_BASE_URL={base_url.rstrip('/')}\nSETUP_TOKEN={token}\n"
               "ADMIN_USERNAME=admin\nADMIN_PASSWORD_HASH=\n"
               "DOWNLOAD_DIR=storage/downloads\nDEBUG=false\n")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)
    print(f"Configuration created. Setup key (keep private):\n{token}")


def rotate_setup_key(path: Path) -> None:
    from dotenv import set_key

    if path.is_symlink() or not path.is_file():
        raise ValueError("Create a regular .env file with make setup first.")
    token = secrets.token_urlsafe(48)
    path.chmod(0o600)
    set_key(str(path), "SETUP_TOKEN", token)
    path.chmod(0o600)
    print(f"Setup key rotated. Restart the application. Key (keep private):\n{token}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "setup-key"])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(Path(".env"), args.url)
        else:
            rotate_setup_key(Path(".env"))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Operation not completed: {exc}\n")


if __name__ == "__main__":
    main()
