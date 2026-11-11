import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACES_DIR = REPO_ROOT / "pilot" / "traces"
RUNS_DIR = REPO_ROOT / "pilot" / "runs"
WORKTREES_DIR = REPO_ROOT / ".pilot-worktrees"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

LOCAL_BASE_BRANCH = "pilot-local"
MAX_REWORK_ROUNDS = 3
MAX_TASKS = 6
SERVICES = ("catalog", "cart", "orders")


@dataclass(frozen=True)
class Settings:
    model: str = os.environ.get("PILOT_MODEL", "claude-sonnet-5-5")
    budget_multiplier: float = float(os.environ.get("PILOT_BUDGET_MULTIPLIER", "1"))
    sandbox: bool = os.environ.get("PILOT_SANDBOX", "1") == "1"
