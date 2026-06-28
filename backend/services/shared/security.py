import re

# Regex list for prompt injection keywords
INJECTION_KEYWORDS = [
    r"ignore\s+previous\s+instructions",
    r"ignore\s+the\s+above\s+instructions",
    r"you\s+are\s+now",
    r"your\s+new\s+role",
    r"system:",
    r"assistant:",
    r"user:",
    r"developer\s+mode"
]

def sanitize_user_input(text: str) -> str:
    """
    Sanitizes user input:
    1. Removes null bytes and control characters.
    2. Strips prompt injection phrases.
    3. Normalizes Unicode characters.
    """
    if not text:
        return ""
    
    # 1. Strip null bytes
    sanitized = text.replace("\x00", "")
    
    # 2. Strip prompt injection patterns
    for pattern in INJECTION_KEYWORDS:
        sanitized = re.sub(pattern, "[FILTERED_INJECTION]", sanitized, flags=re.IGNORECASE)
        
    # 3. Strip control characters except whitespace (newlines, tabs)
    sanitized = "".join(c for c in sanitized if c.isprintable() or c in "\r\n\t")
    
    return sanitized

def wrap_input_xml(text: str) -> str:
    """
    Wraps user input inside structural XML tags to separate instructions from untrusted data.
    """
    sanitized = sanitize_user_input(text)
    return f"<user_input>\n{sanitized}\n</user_input>"

# Regex list for sensitive credentials in log lines
SECRET_PATTERNS = [
    (re.compile(r"(bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), r"\1[REDACTED_JWT]"),
    (re.compile(r"(password\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[REDACTED_PASSWORD]\2"),
    (re.compile(r"(api_key\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[REDACTED_KEY]\2"),
    (re.compile(r"(secret_key\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[REDACTED_KEY]\2"),
    (re.compile(r"(access_token\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[REDACTED_TOKEN]\2")
]

def scrub_log_message(msg: str) -> str:
    """
    Scrubs sensitive strings (JWTs, passwords, API keys) from raw logs.
    """
    if not msg:
        return ""
    scrubbed = msg
    for pattern, repl in SECRET_PATTERNS:
        scrubbed = pattern.sub(repl, scrubbed)
    return scrubbed
