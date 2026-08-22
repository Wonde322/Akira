\
"""
Unified entry gateway for Akira.

Text, voice and UI all enter through submit().
"""

from request_context import create_request_context


class AkiraGateway:

    def __init__(self, runtime=None):
        if runtime is None:
            from akira_runtime import AkiraRuntime
            runtime = AkiraRuntime()

        self.runtime = runtime

    def submit(
        self,
        text=None,
        voice_text=None,
        observation=None,
        source=None,
        metadata=None,
        request_id=None,
    ):
        request = create_request_context(
            text=text,
            voice_text=voice_text,
            observation=observation,
            source=source,
            metadata=metadata,
            request_id=request_id,
        )

        router = getattr(
            self.runtime,
            "route_request",
            None,
        )

        if callable(router):
            return router(request)

        return self.runtime.handle(
            text=request.primary_text(),
            voice_text=request.voice_text,
            observation=request.observation,
            metadata=request.metadata,
        )

    def submit_text(
        self,
        text,
        metadata=None,
    ):
        return self.submit(
            text=text,
            source="text",
            metadata=metadata,
        )

    def submit_voice(
        self,
        transcript,
        metadata=None,
    ):
        return self.submit(
            voice_text=transcript,
            source="voice",
            metadata=metadata,
        )

    def submit_ui(
        self,
        text=None,
        observation=None,
        metadata=None,
    ):
        return self.submit(
            text=text,
            observation=observation,
            source="ui",
            metadata=metadata,
        )


def create_gateway(runtime=None):
    return AkiraGateway(runtime=runtime)
