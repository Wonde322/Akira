"""Safe source-chip extraction; message bodies stay plain text."""
import re
from urllib.parse import urlsplit


def extract_sources(text):
    sources = []
    seen = set()
    def add(url, label=None):
        url = url.rstrip('.,;!?')
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                return None
        except ValueError:
            return None
        if url not in seen:
            sources.append((label or parsed.hostname.removeprefix('www.'), url))
            seen.add(url)
        return label or ''
    text = re.sub(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)',
                  lambda m: add(m[2], m[1]) if add_valid(m[2]) else m[0], str(text))
    text = re.sub(r'https?://[^\s<>\]]+', lambda m: add(m[0]) if add_valid(m[0]) else m[0], text)
    return text.strip(), sources


def add_valid(url):
    try:
        return urlsplit(url).scheme in ('http', 'https') and bool(urlsplit(url).hostname)
    except ValueError:
        return False
