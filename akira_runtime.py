\
"""
Unified runtime for Akira.

This module does not replace existing subsystems.
It composes them behind one stable entry point.
"""

from importlib import import_module


def _load_component(module_name, class_names):
    """
    Safely load the first available class from an existing module.

    Returns None when a component is optional or unavailable.
    """
    try:
        module = import_module(module_name)
    except Exception:
        return None

    for class_name in class_names:
        component_class = getattr(module, class_name, None)

        if component_class is None:
            continue

        try:
            return component_class()
        except Exception:
            continue

    return None


class AkiraRuntime:
    """
    Unified composition root for Akira.

    Existing systems remain independent:
    - brain / reasoning
    - task lifecycle
    - planning
    - recovery
    - capability discovery
    - outcome verification
    - permissions
    - proactive runtime
    - voice lifecycle
    - goals
    - multimodal context
    """

    def __init__(self, components=None):
        components = components or {}

        self.brain = components.get("brain") or _load_component(
            "brain",
            ("Brain", "AgentBrain", "AkiraBrain"),
        )

        self.tasks = components.get("tasks") or _load_component(
            "task_runtime",
            ("TaskRuntime",),
        )

        self.recovery = components.get("recovery") or _load_component(
            "agent_loop",
            ("RecoveryState",),
        ) or _load_component(
            "brain",
            ("RecoveryState",),
        )

        self.planner = components.get("planner") or _load_component(
            "agent_loop",
            ("TaskPlanState",),
        ) or _load_component(
            "brain",
            ("TaskPlanState",),
        )

        self.capabilities = components.get("capabilities") or _load_component(
            "capability_discovery",
            ("CapabilityDiscovery",),
        )

        self.verifier = components.get("verifier") or _load_component(
            "outcome_verification",
            ("OutcomeVerifier",),
        )

        self.safety = components.get("safety") or _load_component(
            "execution_safety",
            ("ExecutionSafetyGate",),
        )

        self.proactive = components.get("proactive") or _load_component(
            "proactive_runtime",
            ("ProactiveRuntime",),
        )

        self.heartbeat = components.get("heartbeat") or _load_component(
            "proactive_runtime",
            ("ProactiveHeartbeat",),
        )

        self.voice = components.get("voice")

        self.goals = components.get("goals") or _load_component(
            "goal_manager",
            ("GoalInitiative",),
        )

        self.context = None
        self.last_result = None

    def status(self):
        """Return availability of all major subsystems."""
        return {
            "brain": self.brain is not None,
            "tasks": self.tasks is not None,
            "planner": self.planner is not None,
            "recovery": self.recovery is not None,
            "capabilities": self.capabilities is not None,
            "verifier": self.verifier is not None,
            "safety": self.safety is not None,
            "proactive": self.proactive is not None,
            "heartbeat": self.heartbeat is not None,
            "goals": self.goals is not None,
            "voice": self.voice is not None,
        }

    def build_context(
        self,
        text=None,
        voice_text=None,
        observation=None,
        source=None,
        metadata=None,
    ):
        """Create one normalized input context."""
        try:
            from multimodal_context import build_input_context

            self.context = build_input_context(
                text=text,
                voice_text=voice_text,
                observation=observation,
                source=source,
                metadata=metadata,
            )

        except Exception:
            self.context = {
                "text": text,
                "voice_text": voice_text,
                "observation": observation,
                "source": source or (
                    "voice" if voice_text else "text"
                ),
                "metadata": metadata or {},
            }

        return self.context

    def discover_capability(self, request):
        """Find the most suitable existing capability."""
        if self.capabilities is None:
            return {
                "success": False,
                "reason": "Capability discovery unavailable",
            }

        choose = getattr(self.capabilities, "choose", None)

        if callable(choose):
            return choose(request)

        return {
            "success": False,
            "reason": "Capability chooser unavailable",
        }

    def authorize(self, tool_name, arguments=None, confirmed=False):
        """Run the existing permission gate."""
        if self.safety is None:
            return {
                "authorized": True,
                "reason": "No safety gate configured",
            }

        authorize = getattr(self.safety, "authorize", None)

        if callable(authorize):
            return authorize(
                tool_name,
                arguments or {},
                confirmed=confirmed,
            )

        return {
            "authorized": True,
            "reason": "Safety adapter has no authorize method",
        }

    def verify(
        self,
        goal=None,
        tool_result=None,
        before=None,
        after=None,
        check=None,
    ):
        """Verify the actual outcome of an action."""
        if self.verifier is None:
            return {
                "status": "unknown",
                "verified": False,
                "reason": "Outcome verifier unavailable",
            }

        result = self.verifier.verify(
            goal=goal,
            tool_result=tool_result,
            before=before,
            after=after,
            check=check,
        )

        if hasattr(result, "to_dict"):
            return result.to_dict()

        return result

    def recover(self, action, arguments=None, error=None):
        """Record a failed attempt for alternative strategy selection."""
        if self.recovery is None:
            return {
                "success": False,
                "reason": "Recovery subsystem unavailable",
            }

        record = getattr(self.recovery, "record_failure", None)

        if callable(record):
            record(
                action,
                arguments or {},
                error=error,
            )

        context = getattr(
            self.recovery,
            "recovery_context",
            None,
        )

        return (
            context()
            if callable(context)
            else {"success": True}
        )

    def heartbeat_tick(self):
        """Run one proactive cycle without forcing notifications."""
        if self.heartbeat is None:
            return []

        run_once = getattr(self.heartbeat, "run_once", None)

        if callable(run_once):
            return run_once(self.proactive)

        tick = getattr(self.heartbeat, "tick", None)

        if callable(tick):
            return tick()

        return []

    def run_goal_analysis(self):
        """Analyze existing goals without autonomously executing actions."""
        if self.goals is None:
            return {
                "success": False,
                "reason": "Goal subsystem unavailable",
            }

        run_once = getattr(self.goals, "run_once", None)

        if callable(run_once):
            return run_once()

        analyze = getattr(self.goals, "analyze", None)

        if callable(analyze):
            return {
                "success": True,
                "suggestions": analyze(),
            }

        return {
            "success": False,
            "reason": "Goal analysis unavailable",
        }

    def handle(
        self,
        text=None,
        voice_text=None,
        observation=None,
        metadata=None,
    ):
        """
        Main unified entry point.

        Builds shared context, then delegates reasoning to the existing
        brain instead of implementing a second agent loop.
        """
        context = self.build_context(
            text=text,
            voice_text=voice_text,
            observation=observation,
            metadata=metadata,
        )

        request = (
            context.primary_text()
            if hasattr(context, "primary_text")
            else (
                context.get("text")
                or context.get("voice_text")
                or ""
            )
        )

        if self.brain is None:
            self.last_result = {
                "success": False,
                "error": "Brain subsystem unavailable",
                "context": (
                    context.to_dict()
                    if hasattr(context, "to_dict")
                    else context
                ),
            }
            return self.last_result

        for method_name in (
            "ask",
            "run",
            "handle",
            "process",
        ):
            method = getattr(self.brain, method_name, None)

            if not callable(method):
                continue

            try:
                self.last_result = method(request)
                return self.last_result

            except TypeError:
                try:
                    self.last_result = method(
                        request,
                        context=context,
                    )
                    return self.last_result
                except TypeError:
                    continue

        self.last_result = {
            "success": False,
            "error": "No supported brain entry point found",
        }

        return self.last_result


    def run_agent_loop(
        self,
        goal,
        observer=None,
        executor=None,
        max_iterations=20,
    ):
        """
        Run the real host-owned agent loop.

        executor must be the project's existing tool execution
        boundary. This method deliberately does not invent one.
        """
        from unified_agent_loop import UnifiedAgentLoop

        if executor is None:
            executor = self.get_tool_executor()

        loop = UnifiedAgentLoop(
            brain=self.brain,
            safety=self.safety,
            verifier=self.verifier,
            recovery=self.recovery,
            observer=observer,
            executor=executor,
            planner=self.planner,
            max_iterations=max_iterations,
        )

        self.last_result = loop.run(goal)
        return self.last_result


    def get_tool_executor(self):
        """Return the project's real tool execution boundary."""
        from tool_execution_adapter import ToolExecutionAdapter

        return ToolExecutionAdapter().execute


    def route_request(self, request):
        """
        Single entry point for normalized input.

        Accepts RequestContext or a compatible dictionary.
        """
        if hasattr(request, "primary_text"):
            text = request.primary_text()
            context = (
                request.to_dict()
                if hasattr(request, "to_dict")
                else {}
            )
        elif isinstance(request, dict):
            text = (
                request.get("text")
                or request.get("voice_text")
                or ""
            )
            context = request
        else:
            text = str(request)
            context = {
                "text": text,
                "source": "unknown",
            }

        self.context = context

        return self.handle(
            text=text,
            voice_text=context.get("voice_text"),
            observation=context.get("observation"),
            metadata=context.get("metadata"),
        )


    def run_computer_task(
        self,
        goal,
        observer,
        executor=None,
        decider=None,
        verifier=None,
        max_iterations=20,
    ):
        """
        Execute a task through the strict computer-use loop.

        The caller supplies the real observer.
        The existing Akira tool executor is used automatically
        when executor is not supplied.
        """
        from computer_use_loop import ComputerUseLoop

        if executor is None:
            executor = self.get_tool_executor()

        if decider is None:
            brain = self.brain

            def decider(task_goal, context):
                for name in (
                    "decide",
                    "next_action",
                    "agent_step",
                ):
                    method = getattr(
                        brain,
                        name,
                        None,
                    )

                    if callable(method):
                        try:
                            return method(
                                task_goal,
                                context=context,
                            )
                        except TypeError:
                            try:
                                return method(context)
                            except TypeError:
                                continue

                return {
                    "type": "finish",
                    "status": "failed",
                    "error": "Brain has no structured decision API",
                }

        loop = ComputerUseLoop(
            observer=observer,
            executor=executor,
            decider=decider,
            verifier=verifier,
            max_iterations=max_iterations,
        )

        self.last_result = loop.run(goal)
        return self.last_result


    def get_browser_executor(self):
        """Return browser as a normal executable capability."""
        from browser_capability import BrowserCapability
        return BrowserCapability().execute


    def get_model_router(self):
        """
        Return the shared model/provider router.

        Existing self.brain is registered as the default backend.
        Additional providers can be registered by the application.
        """
        from model_router import ModelRouter

        router = getattr(
            self,
            "_model_router",
            None,
        )

        if router is None:
            router = ModelRouter()

            if getattr(self, "brain", None) is not None:
                router.register(
                    "brain",
                    self.brain,
                    profiles={
                        "default",
                        "fast",
                        "reasoning",
                        "tool_use",
                    },
                )

            self._model_router = router

        return router


    def register_model_provider(
        self,
        name,
        provider,
        profiles=None,
    ):
        """Register an additional model/provider backend."""
        router = self.get_model_router()

        return router.register(
            name,
            provider,
            profiles=profiles,
        )


    def route_model_request(
        self,
        text=None,
        observation=None,
        needs_tools=False,
        profile=None,
        context=None,
    ):
        """
        Route a request to the most suitable registered provider.
        """
        router = self.get_model_router()

        return router.route(
            text=text,
            observation=observation,
            needs_tools=needs_tools,
            profile=profile,
            context=context,
        )


    def run(
        self,
        text=None,
        voice_text=None,
        observation=None,
        metadata=None,
        source=None,
    ):
        """
        Final unified public entry point.

        Input -> RequestContext -> Runtime -> existing execution path.
        """
        from request_context import create_request_context

        request = create_request_context(
            text=text,
            voice_text=voice_text,
            observation=observation,
            source=source,
            metadata=metadata,
        )

        router = getattr(
            self,
            "route_request",
            None,
        )

        if callable(router):
            return router(request)

        return self.handle(
            text=request.primary_text(),
            voice_text=request.voice_text,
            observation=request.observation,
            metadata=request.metadata,
        )


def create_runtime(components=None):
    """Stable factory for the unified Akira runtime."""
    return AkiraRuntime(components=components)


# Backwards-friendly aliases.
AgentRuntime = AkiraRuntime
Runtime = AkiraRuntime
