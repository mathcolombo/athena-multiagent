from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import PROMPTS_DIR
from orchestrator.guardrails import Policy

READ_TOOLS = ("Read", "Glob", "Grep")
TEST_COMMANDS = (
    ("pytest",),
    ("python", "-m", "pytest"),
    ("git", "status"),
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
)
DEPLOY_COMMANDS = (
    ("scripts/deploy_homolog.sh",),
    ("./scripts/deploy_homolog.sh",),
    ("bash", "scripts/deploy_homolog.sh"),
    ("python", "scripts/healthcheck.py"),
    ("git", "log"),
    ("docker", "compose", "-p", "skynet-homolog", "ps"),
    ("docker", "compose", "-p", "skynet-homolog", "logs"),
)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt_file: str
    tools: tuple[str, ...]
    max_turns: int
    max_budget_usd: float
    sandboxed: bool

    def system_prompt(self, worktree: Path) -> str:
        sections = [(PROMPTS_DIR / self.prompt_file).read_text(encoding="utf-8")]
        for knowledge in ("AGENTS.md", "docs/glossario.md"):
            path = worktree / knowledge
            if path.exists():
                sections.append(f"# Conhecimento do projeto: {knowledge}\n\n{path.read_text(encoding='utf-8')}")
        return "\n\n".join(sections)


REQUISITOS = AgentSpec("requisitos", "requisitos.md", (*READ_TOOLS, "Write", "Edit"), 20, 1.5, False)
CODIGO = AgentSpec("codigo", "codigo.md", (*READ_TOOLS, "Write", "Edit", "Bash"), 50, 4.0, True)
TESTES = AgentSpec("testes", "testes.md", (*READ_TOOLS, "Write", "Edit", "Bash"), 40, 3.0, True)
DEPLOY = AgentSpec("deploy", "deploy.md", (*READ_TOOLS, "Write", "Bash"), 20, 1.0, False)


def policy_for(spec: AgentSpec, service: str, worktree: Path) -> Policy:
    service_dir = f"services/{service}/"
    service_tests = f"{service_dir}tests/"
    events_tests = "libs/events/tests/"
    scopes: dict[str, dict] = {
        "requisitos": {"writable": ("docs/backlog/",)},
        "codigo": {
            "writable": (service_dir, "libs/events/", ".pilot/repro/"),
            "write_excluded": (service_tests, events_tests),
            "commands": TEST_COMMANDS,
        },
        "testes": {"writable": (service_tests, events_tests), "commands": TEST_COMMANDS},
        "deploy": {"writable": (".pilot/deploy_report.md",), "commands": DEPLOY_COMMANDS},
    }
    return Policy(agent=spec.name, worktree=worktree, tools=spec.tools, **scopes[spec.name])
