import fnmatch
import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator.tracing import Trace

FORBIDDEN_SHELL_CHARS = set(";&|<>`$\n\r")
GIT_WRITE_SUBCOMMANDS = {
    "add", "am", "apply", "branch", "checkout", "cherry-pick", "clean", "clone", "commit",
    "config", "fetch", "merge", "pull", "push", "rebase", "remote", "reset", "restore",
    "revert", "rm", "stash", "switch", "tag", "worktree",
}
PRODUCTION_TOKENS = {"prod", "production", "producao", "--prod", "--production"}
DANGEROUS_OPTIONS = {
    "pytest": ("-p", "-c", "-o", "--rootdir", "--override-ini", "--confcutdir", "--basetemp"),
    "git": ("--output", "--no-index", "--ext-diff", "--exec-path", "-c"),
    "node": ("-e", "-p", "-r", "--eval", "--print", "--require", "--import", "--loader", "--experimental-loader", "--inspect"),
}
SECRET_NAMES = {"id_rsa", "id_ed25519", "credentials.json", ".netrc", ".npmrc", ".pypirc"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SECRET_DIRS = {"secrets", ".ssh", ".aws", ".git"}
PATH_FIELDS = {"Read": "file_path", "Write": "file_path", "Edit": "file_path", "Glob": "path", "Grep": "path"}
WRITE_TOOLS = {"Write", "Edit"}


@dataclass(frozen=True)
class Policy:
    agent: str
    worktree: Path
    tools: tuple[str, ...]
    writable: tuple[str, ...] = ()
    write_excluded: tuple[str, ...] = ()
    commands: tuple[tuple[str, ...], ...] = field(default=())


@dataclass(frozen=True)
class Decision:
    allowed: bool
    rule: str = ""
    reason: str = ""


ALLOW = Decision(True)


def deny(rule: str, reason: str) -> Decision:
    return Decision(False, rule, f"Bloqueado pelo guarda-corpo [{rule}]: {reason}")


def is_secret_path(value: str) -> bool:
    parts = PurePosixPath(value.replace("\\", "/")).parts
    for part in parts:
        if part.startswith(".env") and part != ".env.example":
            return True
        if part in SECRET_DIRS or part in SECRET_NAMES:
            return True
        if PurePosixPath(part).suffix in SECRET_SUFFIXES:
            return True
    return False


def relative_to_worktree(policy: Policy, value: str) -> str | None:
    resolved = (policy.worktree / value).resolve()
    try:
        return resolved.relative_to(policy.worktree.resolve()).as_posix()
    except ValueError:
        return None


def is_writable(policy: Policy, relative: str) -> bool:
    def matches(prefix: str) -> bool:
        return relative == prefix.rstrip("/") or relative.startswith(prefix)

    return any(matches(p) for p in policy.writable) and not any(
        matches(p) for p in policy.write_excluded
    )


def evaluate_bash(policy: Policy, command: str) -> Decision:
    if FORBIDDEN_SHELL_CHARS & set(command):
        return deny("shell_metachar", "encadeamento, redirecionamento e substituição são proibidos")
    try:
        tokens = shlex.split(command)
    except ValueError:
        return deny("command_not_allowed", "comando malformado")
    if not tokens:
        return deny("command_not_allowed", "comando vazio")

    for token in tokens:
        if is_secret_path(token):
            return deny("secret", f"acesso a caminho sensível: {token}")
        looks_like_path = "/" in token and not token.startswith("-")
        if looks_like_path and relative_to_worktree(policy, token.split("::")[0]) is None:
            return deny("outside_worktree", f"caminho fora do worktree: {token}")
    if PRODUCTION_TOKENS & {token.lower() for token in tokens}:
        return deny("prod_deploy", "agentes não operam o ambiente de produção")
    if tokens[0] == "git" and len(tokens) > 1 and tokens[1] in GIT_WRITE_SUBCOMMANDS:
        return deny("forbidden_git", f"git {tokens[1]} é exclusivo do supervisor")

    if not any(tuple(tokens[: len(prefix)]) == prefix for prefix in policy.commands):
        return deny("command_not_allowed", f"comando fora da lista permitida: {tokens[0]}")

    program = "pytest" if "pytest" in tokens[:3] else tokens[0]
    for option in DANGEROUS_OPTIONS.get(program, ()):
        for token in tokens[1:]:
            short_match = not option.startswith("--") and token.startswith(option) and not token.startswith("--")
            if token == option or short_match or token.startswith(f"{option}="):
                return deny("dangerous_option", f"opção proibida: {token}")
    return ALLOW


def evaluate(policy: Policy, tool: str, tool_input: dict[str, Any]) -> Decision:
    if tool not in policy.tools:
        return deny("tool_not_allowed", f"{policy.agent} não pode usar {tool}")
    if tool == "Bash":
        return evaluate_bash(policy, str(tool_input.get("command", "")))

    path = str(tool_input.get(PATH_FIELDS.get(tool, ""), "") or ".")
    file_filter = tool_input.get("pattern") if tool == "Glob" else tool_input.get("glob") if tool == "Grep" else None
    patterns = [path, str(file_filter)] if file_filter else [path]
    if any(is_secret_path(value) for value in patterns):
        return deny("secret", f"acesso a caminho sensível: {path}")
    if ".." in PurePosixPath(str(tool_input.get("pattern", ""))).parts and tool == "Glob":
        return deny("outside_worktree", "padrão escapa do worktree")

    relative = relative_to_worktree(policy, path)
    if relative is None:
        return deny("outside_worktree", f"caminho fora do worktree: {path}")
    if tool in WRITE_TOOLS and not is_writable(policy, relative):
        return deny("write_scope", f"{policy.agent} não pode escrever em {relative}")
    return ALLOW


def out_of_scope(policies: list[Policy], changed: list[str]) -> list[str]:
    """Segunda camada: confere os arquivos alterados contra o escopo somado dos agentes."""
    return [
        path for path in changed
        if not any(is_writable(policy, path) for policy in policies)
        and not fnmatch.fnmatch(path, ".pilot/*")
    ]


Hook = Callable[..., Any]


def build_hooks(policy: Policy, trace: Trace, canary: str | None = None) -> tuple[Hook, Hook]:
    async def pre_tool_use(input_data: dict, _tool_use_id: str | None, _context: Any) -> dict:
        tool, tool_input = input_data["tool_name"], input_data["tool_input"]
        decision = evaluate(policy, tool, tool_input)
        trace.emit("tool_call", agent=policy.agent, tool=tool, input=tool_input, allowed=decision.allowed)
        if decision.allowed:
            return {}
        trace.emit("guardrail_block", agent=policy.agent, tool=tool, input=tool_input, rule=decision.rule)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": decision.reason,
            }
        }

    async def post_tool_use(input_data: dict, _tool_use_id: str | None, _context: Any) -> dict:
        if canary and canary in json.dumps(input_data.get("tool_response"), default=str):
            trace.emit(
                "failure",
                agent=policy.agent,
                category="vazamento_segredo",
                description=f"Canário apareceu na saída de {input_data['tool_name']}",
            )
        return {}

    return pre_tool_use, post_tool_use
