"""Final public Akira application facade.

This file does not duplicate the runtime.
It owns the application-level composition only.
"""


class Akira:
    def __init__(self, runtime=None, daemon=None):
        if runtime is None:
            from akira_runtime import AkiraRuntime

            runtime = AkiraRuntime()

        self.runtime = runtime
        self._daemon = daemon

    def start(self, background=False):
        if self._daemon is None:
            from akira_daemon import AkiraDaemon

            self._daemon = AkiraDaemon(runtime=self.runtime)

        return self._daemon.start(background=background)

    def stop(self):
        if self._daemon is None:
            return {"status": "stopped"}

        return self._daemon.stop()

    def status(self):
        if self._daemon is None:
            return {"status": "created"}

        return self._daemon.status()

    def ask(
        self,
        text=None,
        voice_text=None,
        observation=None,
        metadata=None,
        source=None,
    ):
        """Send one request through AkiraRuntime's actual public entry point."""
        request = {
            "text": text,
            "voice_text": voice_text,
            "observation": observation,
            "metadata": metadata or {},
        }
        if source is not None:
            request["source"] = source
        return self.runtime.route_request(request)

    def computer_task(
        self,
        goal,
        observer,
        executor=None,
        decider=None,
        verifier=None,
        max_iterations=20,
    ):
        return self.runtime.run_computer_task(
            goal=goal,
            observer=observer,
            executor=executor,
            decider=decider,
            verifier=verifier,
            max_iterations=max_iterations,
        )


def create_akira(runtime=None):
    return Akira(runtime=runtime)
