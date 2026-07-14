import os
from datetime import datetime, timezone
from typing import Any


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _download(
    platform: str,
    arch: str,
    kind: str,
    label: str,
    fallback_url: str,
    install_command: str | None = None,
) -> dict[str, Any]:
    key = f"ARCEUS_DOWNLOAD_{platform.upper()}_{arch.upper()}_{kind.upper()}"
    url = os.getenv(f"{key}_URL") or fallback_url
    checksum = os.getenv(f"{key}_SHA256") or os.getenv(f"{key}_CHECKSUM")
    release_configured = bool(os.getenv(f"{key}_URL"))
    return {
        "platform": platform,
        "arch": arch,
        "kind": kind,
        "label": label,
        "url": url,
        "checksum_sha256": checksum,
        "available": release_configured,
        "status": "available" if release_configured else "pending_release",
        "install_command": install_command,
    }


def build_download_manifest() -> dict[str, Any]:
    version = os.getenv("ARCEUS_RELEASE_VERSION") or os.getenv("APP_RELEASE") or os.getenv("GIT_SHA") or "local"
    channel = os.getenv("ARCEUS_RELEASE_CHANNEL", "stable")
    signed = _env_bool("ARCEUS_RELEASE_SIGNED", bool(os.getenv("WIN_CSC_LINK") or os.getenv("CSC_LINK") or os.getenv("APPLE_ID")))
    update_feed_url = os.getenv("ARCEUS_UPDATE_FEED_URL") or os.getenv("ELECTRON_UPDATE_FEED_URL")
    return {
        "product": "arceus-code",
        "name": "Arceus Code",
        "version": version,
        "channel": channel,
        "released_at": os.getenv("ARCEUS_RELEASED_AT"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signed": signed,
        "notes_url": os.getenv("ARCEUS_RELEASE_NOTES_URL", "/docs"),
        "update_feed_url": update_feed_url,
        "downloads": {
            "windows": [
                _download(
                    "windows",
                    "x64",
                    "installer",
                    "Windows x64 installer",
                    "/releases/arceus-code-setup.exe",
                    "winget install ArceusCode.ArceusCode",
                )
            ],
            "macos": [
                _download(
                    "macos",
                    "arm64",
                    "dmg",
                    "Apple Silicon DMG",
                    "/releases/arceus-code-mac-arm64.dmg",
                    "brew install --cask arceus-code",
                ),
                _download(
                    "macos",
                    "x64",
                    "dmg",
                    "Intel DMG",
                    "/releases/arceus-code-mac-x64.dmg",
                    "brew install --cask arceus-code",
                ),
            ],
            "linux": [
                _download(
                    "linux",
                    "x64",
                    "appimage",
                    "Linux AppImage",
                    "/releases/arceus-code-x86_64.AppImage",
                ),
                _download(
                    "linux",
                    "x64",
                    "deb",
                    "Debian / Ubuntu package",
                    "/releases/arceus-code_amd64.deb",
                ),
                _download(
                    "linux",
                    "x64",
                    "rpm",
                    "RedHat / Fedora package",
                    "/releases/arceus-code.rpm",
                ),
            ],
        },
    }
