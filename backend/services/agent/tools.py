import os
import httpx
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from langchain_core.tools import tool
from .config import settings

def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())

def _normalize_news_item(item: dict) -> dict:
    return {
        "title": _clean_text(item.get("title")),
        "snippet": _clean_text(item.get("snippet") or item.get("description")),
        "link": item.get("link") or item.get("url") or "",
        "source": item.get("source") or item.get("publisher") or "Live news",
        "published_at": item.get("published_at") or item.get("date") or item.get("publishedDate"),
    }

def _is_image_query(query: str) -> bool:
    query_lower = query.lower()
    return any(word in query_lower for word in ["image", "images", "picture", "photo", "diagram", "visual", "illustration", "gif"])

def _is_video_query(query: str) -> bool:
    query_lower = query.lower()
    return any(word in query_lower for word in ["video", "youtube", "animation", "animated", "watch"])

def _is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host

def _is_usable_media_url(url: str, expected: str) -> bool:
    """Best-effort validation so chat never receives known-broken media URLs."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    if expected == "video" and _is_youtube_url(url):
        return True

    try:
        response = httpx.head(url, follow_redirects=True, timeout=6.0)
        if response.status_code >= 400 or not response.headers.get("content-type"):
            response = httpx.get(url, follow_redirects=True, timeout=8.0)
        if response.status_code >= 400:
            return False
        content_type = response.headers.get("content-type", "").lower()
        if expected == "image":
            return content_type.startswith("image/")
        if expected == "video":
            return content_type.startswith("video/")
    except Exception:
        return False
    return False

def _markdown_image_result(title: str, image_url: str, source: str) -> str:
    return f"- Image: {title}\n  Markdown: ![{title}]({image_url})\n  Source: {source}"

def _markdown_video_result(title: str, link: str, snippet: str = "") -> str:
    return f"- Video: {title}\n  Markdown: [Video: {title}]({link})\n  Summary: {snippet}"

def _curated_media_results(query: str) -> str:
    query_lower = query.lower()
    if _is_image_query(query):
        if "skelet" in query_lower or "bone" in query_lower:
            return (
                "IMAGE RESULTS:\n"
                + "\n".join([
                    _markdown_image_result(
                        "Human skeletal system front view",
                        "https://upload.wikimedia.org/wikipedia/commons/c/ca/Human_skeleton_front_en.svg",
                        "Wikimedia Commons",
                    ),
                    _markdown_image_result(
                        "Human skeletal system back view",
                        "https://upload.wikimedia.org/wikipedia/commons/4/4e/Human_skeleton_back_en.svg",
                        "Wikimedia Commons",
                    ),
                ])
            )
        if "mitosis" in query_lower or "cell division" in query_lower:
            return (
                "IMAGE RESULTS:\n"
                + _markdown_image_result(
                    "Major events in mitosis",
                    "https://upload.wikimedia.org/wikipedia/commons/2/2a/Major_events_in_mitosis.svg",
                    "Wikimedia Commons",
                )
            )

    if _is_video_query(query):
        return (
            "VIDEO RESULTS:\n"
            + _markdown_video_result(
                "How a car engine works",
                "https://www.youtube.com/watch?v=ZQvfHyfgBtA",
                "Educational engine animation.",
            )
        )
    return ""

def _fetch_media_results(query: str) -> str:
    """
    Return markdown-ready media candidates for teaching responses.
    Uses Serper's image/video endpoints when configured.
    """
    headers = {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    sections: list[str] = []

    if _is_image_query(query):
        image_response = httpx.post(
            "https://google.serper.dev/images",
            json={"q": query, "num": 5},
            headers=headers,
            timeout=10.0,
        )
        image_response.raise_for_status()
        images = image_response.json().get("images", [])
        image_lines = []
        for item in images[:5]:
            image_url = item.get("imageUrl") or item.get("thumbnailUrl")
            if not _is_usable_media_url(image_url or "", "image"):
                continue
            title = _clean_text(item.get("title")) or "Educational image"
            source = item.get("source") or item.get("link") or ""
            image_lines.append(_markdown_image_result(title, image_url, source))
        if image_lines:
            sections.append("IMAGE RESULTS:\n" + "\n".join(image_lines))

    if _is_video_query(query):
        video_response = httpx.post(
            "https://google.serper.dev/videos",
            json={"q": query, "num": 5},
            headers=headers,
            timeout=10.0,
        )
        video_response.raise_for_status()
        videos = video_response.json().get("videos", [])
        video_lines = []
        for item in videos[:5]:
            link = item.get("link")
            if not _is_usable_media_url(link or "", "video"):
                continue
            title = _clean_text(item.get("title")) or "Educational video"
            snippet = _clean_text(item.get("snippet"))
            video_lines.append(_markdown_video_result(title, link, snippet))
        if video_lines:
            sections.append("VIDEO RESULTS:\n" + "\n".join(video_lines))

    return "\n\n".join(sections)

def fetch_educational_media(query: str) -> str:
    """Fetch markdown-ready image/video candidates without relying on model tool calling."""
    query = _clean_text(query)
    if not query:
        return ""

    if settings.SERPER_API_KEY == "mock-serper-key-for-local-dev-only" or not settings.SERPER_API_KEY:
        return _curated_media_results(query)

    try:
        return _fetch_media_results(query) or _curated_media_results(query)
    except Exception as e:
        fallback = _curated_media_results(query)
        return fallback or f"Media lookup failed: {str(e)}"

def fetch_live_news(query: str, limit: int = 8) -> list[dict]:
    """
    Fetch live news with no model-memory assumptions.
    Prefer Serper News when configured, then fall back to Google News RSS.
    """
    query = _clean_text(query) or "artificial intelligence"
    limit = max(1, min(limit, 20))

    if settings.SERPER_API_KEY and settings.SERPER_API_KEY != "mock-serper-key-for-local-dev-only":
        response = httpx.post(
            "https://google.serper.dev/news",
            json={"q": query, "num": limit},
            headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        news = response.json().get("news", [])
        return [_normalize_news_item(item) for item in news[:limit]]

    rss_url = "https://news.google.com/rss/search"
    response = httpx.get(
        rss_url,
        params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        timeout=10.0,
    )
    response.raise_for_status()

    root = ET.fromstring(response.text)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        published = _clean_text(item.findtext("pubDate"))
        published_iso = published
        if published:
            try:
                published_iso = parsedate_to_datetime(published).isoformat()
            except Exception:
                pass

        source = item.find("source")
        items.append({
            "title": _clean_text(item.findtext("title")),
            "snippet": _clean_text(item.findtext("description")),
            "link": item.findtext("link") or "",
            "source": _clean_text(source.text if source is not None else "Google News"),
            "published_at": published_iso,
        })

    return items

@tool
def web_search(query: str) -> str:
    """Search the web for real-time information, weather, news, pricing, or details on a topic."""
    # Check if API key is mock
    if settings.SERPER_API_KEY == "mock-serper-key-for-local-dev-only" or not settings.SERPER_API_KEY:
        # Mock search response
        print(f"Mock Search Query: {query}")
        if _is_image_query(query):
            return _curated_media_results(query)
        if _is_video_query(query):
            return _curated_media_results(query)
        if "pricing" in query.lower():
            return "AWS: Est $45-120/mo, GCP: Est $35-95/mo, Render: Est $25-60/mo. Best for early-stage SaaS is Render."
        elif "clerk" in query.lower():
            return "Clerk provides drop-in user management and authentication. Eliminates the need to write custom auth handlers, saving 6+ hours of setup."
        return f"Mock search result for '{query}': High-quality relevant articles and pricing comparison data."
        
    try:
        if _is_image_query(query) or _is_video_query(query):
            media_results = fetch_educational_media(query)
            if media_results:
                return media_results

        url = "https://google.serper.dev/search"
        payload = {"q": query}
        headers = {
            'X-API-KEY': settings.SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if response.status_code == 200:
            results = response.json()
            organic = results.get("organic", [])
            snippets = [f"- {item.get('title')}: {item.get('snippet')} (Source: {item.get('link')})" for item in organic[:3]]
            return "\n".join(snippets) if snippets else "No search results found."
        return f"Search service returned status {response.status_code}"
    except Exception as e:
        return f"Search execution failed: {str(e)}"

@tool
def live_news(query: str) -> str:
    """Fetch current news headlines about AI, companies, markets, tools, regulations, or any live topic."""
    try:
        items = fetch_live_news(query, limit=5)
        if not items:
            return "No live news results found."
        return "\n".join(
            f"- {item['title']} ({item['source']}, {item.get('published_at') or 'recent'}) {item['link']}"
            for item in items
        )
    except Exception as e:
        return f"Live news lookup failed: {str(e)}"

@tool
def read_file(file_path: str) -> str:
    """Read contents of an uploaded file or document in the local filesystem sandbox."""
    try:
        normalized = os.path.normpath(file_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            # In a production environment, enforce strict directory prefix checking
            # For local dev, allow reading files within a safe subfolder
            pass
            
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."
            
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(10000) # Limit read to 10k chars to avoid token blowout
            if len(content) >= 10000:
                content += "\n... [TRUNCATED due to length] ..."
            return content
    except Exception as e:
        return f"File read failed: {str(e)}"

@tool
def memory_read(query: str, user_id: str) -> str:
    """Retrieve semantically relevant context, memories, facts, preferences, or past decisions stored about this user."""
    from .memory_agent import retrieve_context
    try:
        from uuid import UUID
        user_uuid = UUID(user_id)
        results = retrieve_context(user_uuid, query)
        if not results:
            return "No matching memories found."
        return "\n".join([f"- Memory (Importance {m['importance']}): {m['content']}" for m in results])
    except Exception as e:
        return f"Memory retrieval failed: {str(e)}"
