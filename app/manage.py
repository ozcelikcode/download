"""Yeni sunucu yapılandırması; sırlar yalnız terminalde gösterilir."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit


def prepare(path: Path, base_url: str) -> None:
    """Mevcut .env'yi değiştirmeden özel izinli yeni yapılandırma oluştur."""
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.username or parsed.password or "\\" in base_url
            or any(c.isspace() or ord(c) < 32 for c in base_url)):
        raise ValueError("Geçerli bir HTTP/HTTPS kök adresi girin.")
    token = secrets.token_urlsafe(48)
    content = (f"APP_SECRET_KEY={secrets.token_urlsafe(48)}\n"
               f"APP_BASE_URL={base_url.rstrip('/')}\nSETUP_TOKEN={token}\n"
               "ADMIN_USERNAME=admin\nADMIN_PASSWORD_HASH=\n"
               "DOWNLOAD_DIR=storage/downloads\nDEBUG=false\n")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)
    print(f"Yapılandırma oluşturuldu. Kurulum anahtarı (gizli tutun):\n{token}")


def rotate_setup_key(path: Path) -> None:
    from dotenv import set_key

    if path.is_symlink() or not path.is_file():
        raise ValueError("Önce make setup ile normal bir .env dosyası oluşturun.")
    token = secrets.token_urlsafe(48)
    path.chmod(0o600)
    set_key(str(path), "SETUP_TOKEN", token)
    path.chmod(0o600)
    print(f"Kurulum anahtarı yenilendi; uygulamayı yeniden başlatın. Anahtar (gizli tutun):\n{token}")


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
        parser.exit(1, f"İşlem yapılmadı: {exc}\n")


if __name__ == "__main__":
    main()
