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
    if sources:
        names = set()
        for title, url in sources:
            names.add(title)
            names.add(urlsplit(url).hostname.removeprefix('www.'))
        lines = []
        for line in text.splitlines():
            match = re.match(r'^\s*(?:[-*]\s*)?(?:источники?|sources?)\s*:\s*(.*)$', line, re.IGNORECASE)
            if match:
                remainder = match[1]
                for name in sorted(names, key=len, reverse=True):
                    remainder = re.sub(re.escape(name), '', remainder, flags=re.IGNORECASE)
                remainder = re.sub(r'\b(?:и|and)\b', '', remainder, flags=re.IGNORECASE)
                if not re.search(r'\w', remainder):
                    continue
            lines.append(line)
        text = '\n'.join(lines)
    return text.strip(), sources


def add_valid(url):
    try:
        return urlsplit(url).scheme in ('http', 'https') and bool(urlsplit(url).hostname)
    except ValueError:
        return False
