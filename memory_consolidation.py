
"""
Unified memory consolidation layer.

Existing memory implementations remain untouched.
This layer provides one normalized interface for:
    working context
    long-term facts
    projects
    events
    retrieval before reasoning
"""

from dataclasses import dataclass, field
from typing import Any
import time
import uuid


MEMORY_SCOPES = {
    "working",
    "facts",
    "projects",
    "events",
}


@dataclass
class MemoryItem:
    id: str
    scope: str
    content: Any
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "id": self.id,
            "scope": self.scope,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MemoryConsolidator:

    def __init__(self, backend=None):
        self.backend = backend
        self._items = {
            scope: []
            for scope in MEMORY_SCOPES
        }

    def _normalize_content(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return " ".join(
                f"{key} {value}"
                for key, value in content.items()
            )
        return str(content)

    def _backend_store(
        self,
        scope,
        content,
        metadata,
    ):
        backend = self.backend

        if backend is None:
            return None

        for name in (
            "store",
            "add",
            "remember",
            "save",
            "write",
        ):
            method = getattr(backend, name, None)

            if not callable(method):
                continue

            attempts = [
                lambda: method(
                    content=content,
                    scope=scope,
                    metadata=metadata,
                ),
                lambda: method(
                    content,
                    scope=scope,
                    metadata=metadata,
                ),
                lambda: method(
                    content,
                    metadata=metadata,
                ),
                lambda: method(content),
            ]

            for attempt in attempts:
                try:
                    return attempt()
                except TypeError:
                    continue
                except Exception:
                    break

        return None

    def add(
        self,
        content,
        scope="facts",
        metadata=None,
        item_id=None,
    ):
        if scope not in MEMORY_SCOPES:
            raise ValueError(
                f"Unknown memory scope: {scope}"
            )

        now = time.time()

        item = MemoryItem(
            id=item_id or str(uuid.uuid4()),
            scope=scope,
            content=content,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

        self._items[scope].append(item)

        self._backend_store(
            scope,
            content,
            item.metadata,
        )

        return item.to_dict()

    def remember_fact(
        self,
        content,
        metadata=None,
    ):
        return self.add(
            content,
            scope="facts",
            metadata=metadata,
        )

    def remember_project(
        self,
        content,
        project=None,
        metadata=None,
    ):
        metadata = dict(metadata or {})

        if project is not None:
            metadata["project"] = project

        return self.add(
            content,
            scope="projects",
            metadata=metadata,
        )

    def remember_event(
        self,
        content,
        metadata=None,
    ):
        return self.add(
            content,
            scope="events",
            metadata=metadata,
        )

    def set_working(
        self,
        content,
        metadata=None,
    ):
        self._items["working"].clear()

        return self.add(
            content,
            scope="working",
            metadata=metadata,
        )

    def clear_working(self):
        self._items["working"].clear()

    def _score(
        self,
        query,
        item,
    ):
        query_words = set(
            self._normalize_content(query)
            .lower()
            .split()
        )

        item_words = set(
            self._normalize_content(item.content)
            .lower()
            .split()
        )

        if not query_words:
            return 0

        overlap = len(
            query_words.intersection(item_words)
        )

        metadata_text = self._normalize_content(
            item.metadata
        ).lower()

        metadata_overlap = sum(
            1
            for word in query_words
            if word in metadata_text
        )

        return overlap * 10 + metadata_overlap

    def retrieve(
        self,
        query,
        scopes=None,
        limit=10,
    ):
        scopes = scopes or MEMORY_SCOPES

        matches = []

        for scope in scopes:
            if scope not in self._items:
                continue

            for item in self._items[scope]:
                score = self._score(
                    query,
                    item,
                )

                if score > 0 or scope == "working":
                    matches.append(
                        (score, item)
                    )

        matches.sort(
            key=lambda value: (
                value[0],
                value[1].updated_at,
            ),
            reverse=True,
        )

        return [
            item.to_dict()
            for _, item in matches[:limit]
        ]

    def context_for(
        self,
        query,
        limit=10,
    ):
        return {
            "query": query,
            "working": self.retrieve(
                query,
                scopes=["working"],
                limit=limit,
            ),
            "relevant_memory": self.retrieve(
                query,
                scopes=[
                    "facts",
                    "projects",
                    "events",
                ],
                limit=limit,
            ),
        }

    def snapshot(self):
        return {
            scope: [
                item.to_dict()
                for item in items
            ]
            for scope, items
            in self._items.items()
        }
