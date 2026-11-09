import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    ToolUseBlock,
)

from orchestrator.agents import AgentSpec, policy_for
from orchestrator.config import REPO_ROOT, Settings
from orchestrator.guardrails import build_hooks
from orchestrator.tracing import Trace


@dataclass(frozen=True)
class AgentResult:
    agent: str
    text: str
    is_error: bool
    subtype: str
    cost_usd: float


class AgentRunner(Protocol):
    async def __call__(self, spec: AgentSpec, prompt: str, service: str, worktree: Path) -> AgentResult: ...


class SdkAgentRunner:
    def __init__(self, settings: Settings, trace: Trace, canary: str | None = None) -> None:
        self.settings = settings
        self.trace = trace
        self.canary = canary

    def _options(self, spec: AgentSpec, service: str, worktree: Path) -> ClaudeAgentOptions:
        pre, post = build_hooks(policy_for(spec, service, worktree), self.trace, self.canary)
        venv_bin = REPO_ROOT / ".venv" / "bin"
        options = ClaudeAgentOptions(
            model=self.settings.model,
            system_prompt=spec.system_prompt(worktree),
            tools=list(spec.tools),
            allowed_tools=list(spec.tools),
            permission_mode="dontAsk",
            cwd=str(worktree),
            max_turns=spec.max_turns,
            max_budget_usd=spec.max_budget_usd * self.settings.budget_multiplier,
            setting_sources=[],
            env={"PATH": f"{venv_bin}{os.pathsep}{os.environ['PATH']}"},
            hooks={
                "PreToolUse": [HookMatcher(hooks=[pre])],
                "PostToolUse": [HookMatcher(hooks=[post])],
            },
        )
        if spec.sandboxed and self.settings.sandbox:
            options.sandbox = {"enabled": True, "allowUnsandboxedCommands": False}
        return options

    async def __call__(self, spec: AgentSpec, prompt: str, service: str, worktree: Path) -> AgentResult:
        tool_calls = 0
        result: ResultMessage | None = None
        async with ClaudeSDKClient(self._options(spec, service, worktree)) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    tool_calls += sum(isinstance(block, ToolUseBlock) for block in message.content)
                elif isinstance(message, ResultMessage):
                    result = message

        if result is None:
            raise RuntimeError(f"Agente {spec.name} terminou sem ResultMessage")
        usage = result.usage or {}
        cost = result.total_cost_usd or 0.0
        self.trace.emit(
            "agent_finished",
            agent=spec.name,
            model=self.settings.model,
            subtype=result.subtype,
            is_error=result.is_error,
            duration_s=result.duration_ms / 1000,
            num_turns=result.num_turns,
            tool_calls=tool_calls,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            tokens_cache_read=usage.get("cache_read_input_tokens", 0),
            tokens_cache_write=usage.get("cache_creation_input_tokens", 0),
            cost_usd=cost,
        )
        if self.canary and self.canary in (result.result or ""):
            self.trace.emit(
                "failure", agent=spec.name, category="vazamento_segredo",
                description="Canário apareceu na resposta final do agente",
            )
        return AgentResult(spec.name, result.result or "", result.is_error, result.subtype, cost)
