import base64
import collections
import json
import math
import urllib.error
import urllib.request
from io import BytesIO
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(part.strip() for part in self.title_parts if part.strip())[:180]


@dataclass
class VerificationReport:
    url: str
    status: str
    checked_at: str
    status_code: int | None = None
    content_type: str = ""
    title: str = ""
    issues: list[str] = field(default_factory=list)
    browser: str = "http"
    screenshot_path: str | None = None
    screenshot_base64: str | None = None
    html_snapshot_path: str | None = None
    console_errors: list[dict[str, Any]] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    network_failures: list[dict[str, Any]] = field(default_factory=list)
    blank_page: bool = False
    first_contentful_paint_ms: float | None = None
    playwright_error: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    fix_suggestion_prompt: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "title": self.title,
            "issues": self.issues,
            "checked_at": self.checked_at,
            "browser": self.browser,
            "screenshot_path": self.screenshot_path,
            "screenshot_base64": self.screenshot_base64,
            "html_snapshot_path": self.html_snapshot_path,
            "console_errors": self.console_errors,
            "page_errors": self.page_errors,
            "network_failures": self.network_failures,
            "blank_page": self.blank_page,
            "first_contentful_paint_ms": self.first_contentful_paint_ms,
            "playwright_error": self.playwright_error,
            "artifacts": self.artifacts,
            "verification_report": {
                "browser": self.browser,
                "blank_page": self.blank_page,
                "first_contentful_paint_ms": self.first_contentful_paint_ms,
                "console_error_count": len(self.console_errors),
                "page_error_count": len(self.page_errors),
                "network_failure_count": len(self.network_failures),
                "screenshot_entropy": next((item.get("entropy") for item in self.artifacts if item.get("kind") == "screenshot"), None),
            },
            "fix_suggestion_prompt": self.fix_suggestion_prompt,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_probe(url: str) -> tuple[int | None, str, str, str, list[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Arceus-Code-Preview/1.0"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            content_type = response.headers.get("content-type", "")
            body = response.read(250_000).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, "", "", "", [f"HTTP {exc.code}"]
    except Exception as exc:
        return None, "", "", "", [str(exc)]

    parser = _TitleParser()
    if "html" in content_type.lower():
        parser.feed(body)
    return status_code, content_type, body, parser.title, []


def _issue_markers(body: str) -> list[str]:
    markers = [
        "Unhandled Runtime Error",
        "Application error",
        "Traceback",
        "Module not found",
        "ReferenceError",
        "TypeError:",
        "SyntaxError:",
        "Internal Server Error",
        "Hydration failed",
        "Minified React error",
    ]
    lower = body.lower()
    return [marker for marker in markers if marker.lower() in lower]


def _fix_prompt(url: str, issues: list[str], title: str = "") -> str:
    return "\n".join([
        "Fix the latest preview verification failure.",
        f"Preview URL: {url}",
        f"Title: {title or 'unknown'}",
        f"Issues: {', '.join(issues) or 'unknown'}",
        "Use the smallest safe patch. Do not rewrite unrelated files.",
    ])


def _screenshot_entropy(screenshot: bytes) -> float | None:
    try:
        from PIL import Image

        image = Image.open(BytesIO(screenshot)).convert("L").resize((96, 96))
        histogram = image.histogram()
        total = sum(histogram) or 1
        entropy = 0.0
        for count in histogram:
            if not count:
                continue
            probability = count / total
            entropy -= probability * math.log2(probability)
        return round(entropy, 4)
    except Exception:
        return None


def is_blank_page(screenshot_bytes: bytes, threshold: float = 0.5) -> bool:
    try:
        from PIL import Image

        image = Image.open(BytesIO(screenshot_bytes)).convert("L").resize((96, 96))
        pixels = list(image.getdata())
        if not pixels:
            return True
        frequency = collections.Counter(pixels)
        total = len(pixels)
        entropy = -sum((count / total) * math.log2(count / total) for count in frequency.values())
        return entropy < threshold
    except Exception:
        return False


async def verify_preview(url: str, artifacts_dir: Path, timeout_ms: int = 15000) -> VerificationReport:
    import asyncio

    result = await asyncio.to_thread(verify_preview_url, url, artifacts_dir, timeout_ms)
    return VerificationReport(
        url=result["url"],
        status=result["status"],
        checked_at=result["checked_at"],
        status_code=result.get("status_code"),
        content_type=result.get("content_type") or "",
        title=result.get("title") or "",
        issues=result.get("issues") or [],
        browser=result.get("browser") or "playwright",
        screenshot_path=result.get("screenshot_path"),
        screenshot_base64=result.get("screenshot_base64"),
        html_snapshot_path=result.get("html_snapshot_path"),
        console_errors=result.get("console_errors") or [],
        page_errors=result.get("page_errors") or [],
        network_failures=result.get("network_failures") or [],
        blank_page=bool(result.get("blank_page")),
        first_contentful_paint_ms=result.get("first_contentful_paint_ms"),
        playwright_error=result.get("playwright_error"),
        artifacts=result.get("artifacts") or [],
        fix_suggestion_prompt=result.get("fix_suggestion_prompt"),
    )


def verify_preview_url(url: str, artifacts_dir: Path, timeout_ms: int = 15000) -> dict[str, Any]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    checked_at = _now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    screenshot_path = artifacts_dir / f"preview-{stamp}.png"
    html_path = artifacts_dir / f"preview-{stamp}.html"

    status_code, content_type, body, title, http_issues = _http_probe(url)
    issues = list(http_issues) + _issue_markers(body)
    report = VerificationReport(
        url=url,
        status="failed",
        checked_at=checked_at,
        status_code=status_code,
        content_type=content_type,
        title=title,
        issues=issues,
    )

    try:
        from playwright.sync_api import sync_playwright

        console_errors: list[dict[str, Any]] = []
        page_errors: list[str] = []
        network_failures: list[dict[str, Any]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})

            def capture_console_error(msg: Any) -> None:
                if msg.type != "error":
                    return
                args: list[str] = []
                for arg in msg.args:
                    try:
                        args.append(str(arg.json_value()))
                    except Exception:
                        args.append(str(arg))
                console_errors.append({
                    "type": msg.type,
                    "text": msg.text,
                    "args": args,
                    "url": msg.location.get("url") if msg.location else "",
                    "line": msg.location.get("lineNumber") if msg.location else None,
                    "column": msg.location.get("columnNumber") if msg.location else None,
                })

            def capture_request_failure(req: Any) -> None:
                failure = req.failure or {}
                network_failures.append({
                    "url": req.url,
                    "error": failure.get("errorText") if isinstance(failure, dict) else str(failure),
                    "method": req.method,
                    "resource_type": req.resource_type,
                })

            page.on("console", capture_console_error)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("requestfailed", capture_request_failure)
            response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            screenshot = page.screenshot(path=str(screenshot_path), full_page=True)
            html = page.content()
            html_path.write_text(html, encoding="utf-8", errors="ignore")
            visible_text = (page.locator("body").inner_text(timeout=3000) if page.locator("body").count() else "").strip()
            element_count = page.locator("body *").count() if page.locator("body").count() else 0
            paint_entries = page.evaluate("""() => performance.getEntriesByType('paint').map((entry) => ({ name: entry.name, startTime: entry.startTime }))""")
            browser.close()

        fcp = next((float(item["startTime"]) for item in paint_entries if item.get("name") == "first-contentful-paint"), None)
        report.browser = "playwright"
        report.status_code = response.status if response else status_code
        report.screenshot_path = str(screenshot_path)
        report.screenshot_base64 = base64.b64encode(screenshot).decode("ascii")
        report.html_snapshot_path = str(html_path)
        report.console_errors = console_errors[-20:]
        report.page_errors = page_errors[-20:]
        report.network_failures = network_failures[-20:]
        entropy = _screenshot_entropy(screenshot)
        report.blank_page = (len(visible_text) < 12 and element_count < 4) or is_blank_page(screenshot, threshold=0.5)
        report.first_contentful_paint_ms = fcp
        report.artifacts = [
            {"name": screenshot_path.name, "path": str(screenshot_path), "kind": "screenshot", "size_bytes": screenshot_path.stat().st_size, "entropy": entropy},
            {"name": html_path.name, "path": str(html_path), "kind": "html_snapshot", "size_bytes": html_path.stat().st_size},
        ]
    except Exception as exc:
        report.browser = "http-fallback"
        report.playwright_error = str(exc)[:300]

    report.issues.extend([f"console: {str(item.get('text') or item)[:120]}" for item in report.console_errors])
    report.issues.extend([f"page: {item[:120]}" for item in report.page_errors])
    if report.network_failures:
        report.issues.append(f"{len(report.network_failures)} network failure(s)")
    if report.blank_page:
        report.issues.append("Blank or nearly blank page")
    if report.first_contentful_paint_ms and report.first_contentful_paint_ms > 3000:
        report.issues.append(f"Slow first contentful paint: {int(report.first_contentful_paint_ms)}ms")
    report.issues = list(dict.fromkeys(report.issues))
    report.status = "passed" if report.status_code and 200 <= report.status_code < 400 and not report.issues else "failed"
    if report.status != "passed":
        report.fix_suggestion_prompt = _fix_prompt(url, report.issues, report.title)
    return report.as_dict()
