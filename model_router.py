\
"""
Model and provider routing for Akira.

Providers are injected or registered explicitly.
The router never creates a second brain and does not hardcode
API keys, model names or provider SDKs.
"""

from dataclasses import dataclass, field
from typing import Any


ROUTES = {
    "fast",
    "reasoning",
    "vision",
    "tool_use",
    "default",
}


@dataclass
class ProviderResult:
    success: bool
    provider: str | None = None
    profile: str | None = None
    result: Any = None
    error: str | None = None
    attempts: list = field(default_factory=list)

    def to_dict(self):
        return {
            "success": self.success,
            "provider": self.provider,
            "profile": self.profile,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
        }


class ModelRouter:
    """
    Host-owned provider router.

    A provider is any callable or object exposing one of:
        ask
        complete
        generate
        run
        __call__
    """

    def __init__(self, providers=None, defaults=None):
        self.providers = {}
        self.defaults = dict(defaults or {})

        for name, provider in (providers or {}).items():
            self.register(name, provider)

    def register(self, name, provider, profiles=None):
        if not name:
            raise ValueError("Provider name is required")

        self.providers[name] = {
            "provider": provider,
            "profiles": set(
                profiles or {"default"}
            ),
        }

        return name

    def unregister(self, name):
        return self.providers.pop(name, None)

    def available(self):
        return {
            name: sorted(entry["profiles"])
            for name, entry in self.providers.items()
        }

    def choose_profile(
        self,
        text=None,
        observation=None,
        needs_tools=False,
        profile=None,
    ):
        if profile is not None:
            if profile not in ROUTES:
                raise ValueError(
                    f"Unknown route profile: {profile}"
                )
            return profile

        if observation is not None:
            return "vision"

        if needs_tools:
            return "tool_use"

        text = str(text or "").lower()

        reasoning_signals = (
            "почему",
            "объясни",
            "проанализируй",
            "сравни",
            "спланируй",
            "архитектур",
            "reason",
            "analyze",
            "compare",
            "plan",
        )

        if any(
            signal in text
            for signal in reasoning_signals
        ):
            return "reasoning"

        return "fast"

    def _candidates(self, profile):
        preferred = self.defaults.get(profile)

        ordered = []

        if (
            preferred is not None
            and preferred in self.providers
        ):
            ordered.append(preferred)

        for name, entry in self.providers.items():
            if (
                name not in ordered
                and (
                    profile in entry["profiles"]
                    or "default" in entry["profiles"]
                )
            ):
                ordered.append(name)

        if not ordered:
            ordered = list(self.providers)

        return ordered

    @staticmethod
    def _invoke(
        provider,
        text,
        context,
    ):
        if callable(provider):
            attempts = [
                lambda: provider(
                    text=text,
                    context=context,
                ),
                lambda: provider(text, context),
                lambda: provider(text),
            ]
        else:
            methods = []

            for name in (
                "ask",
                "complete",
                "generate",
                "run",
            ):
                method = getattr(
                    provider,
                    name,
                    None,
                )

                if callable(method):
                    methods.append(method)

            if not methods:
                raise TypeError(
                    "Provider has no supported execution method"
                )

            method = methods[0]

            attempts = [
                lambda: method(
                    text=text,
                    context=context,
                ),
                lambda: method(text, context),
                lambda: method(text),
            ]

        last_type_error = None

        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_type_error = exc

        raise last_type_error

    def route(
        self,
        text=None,
        observation=None,
        needs_tools=False,
        profile=None,
        context=None,
    ):
        selected = self.choose_profile(
            text=text,
            observation=observation,
            needs_tools=needs_tools,
            profile=profile,
        )

        payload = dict(context or {})
        payload["route_profile"] = selected

        if observation is not None:
            payload["observation"] = observation

        attempts = []

        for name in self._candidates(selected):
            entry = self.providers[name]

            try:
                result = self._invoke(
                    entry["provider"],
                    text,
                    payload,
                )

                return ProviderResult(
                    success=True,
                    provider=name,
                    profile=selected,
                    result=result,
                    attempts=attempts,
                ).to_dict()

            except Exception as exc:
                attempts.append({
                    "provider": name,
                    "error": str(exc),
                })

        return ProviderResult(
            success=False,
            profile=selected,
            error=(
                "No provider completed the request"
            ),
            attempts=attempts,
        ).to_dict()
