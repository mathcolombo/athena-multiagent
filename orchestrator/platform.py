import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from orchestrator.config import LOCAL_BASE_BRANCH, REPO_ROOT


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    branch: str


@dataclass(frozen=True)
class CiResult:
    passed: bool
    log: str


def run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{REPO_ROOT / '.venv' / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(args, cwd=cwd, env=env, check=check, capture_output=True, text=True)


class Platform(Protocol):
    name: str
    base_ref: str

    def prepare_base(self) -> None: ...

    def open_pr(self, worktree: Path, branch: str, title: str, body: str) -> PullRequest: ...

    def push(self, worktree: Path, branch: str) -> None: ...

    def wait_ci(self, worktree: Path, pr: PullRequest, service: str) -> CiResult: ...

    def is_merged(self, worktree: Path, pr: PullRequest) -> bool: ...

    def complete_review(self, worktree: Path, pr: PullRequest) -> None: ...

    def review_comments(self, worktree: Path, pr: PullRequest) -> str: ...

    def sync_merged(self, worktree: Path) -> None: ...

    def tag_release(self, worktree: Path, tag: str) -> None: ...


class GitHubPlatform:
    name = "github"
    base_ref = "origin/main"

    def prepare_base(self) -> None:
        run(["git", "fetch", "origin", "main", "--tags"], REPO_ROOT)

    def open_pr(self, worktree: Path, branch: str, title: str, body: str) -> PullRequest:
        run(["git", "push", "-u", "origin", branch], worktree)
        created = run(
            ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", body],
            worktree,
        )
        url = created.stdout.strip().splitlines()[-1]
        return PullRequest(int(url.rsplit("/", 1)[1]), url, branch)

    def push(self, worktree: Path, branch: str) -> None:
        run(["git", "push", "origin", branch], worktree)

    def wait_ci(self, worktree: Path, pr: PullRequest, service: str) -> CiResult:
        watched = run(["gh", "pr", "checks", str(pr.number), "--watch", "--interval", "15"], worktree, check=False)
        if watched.returncode == 0:
            return CiResult(True, watched.stdout)
        head = run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
        runs = run(["gh", "run", "list", "--commit", head, "--json", "databaseId", "--limit", "1"], worktree)
        run_ids = json.loads(runs.stdout)
        if not run_ids:
            return CiResult(False, watched.stdout + watched.stderr)
        logs = run(["gh", "run", "view", str(run_ids[0]["databaseId"]), "--log-failed"], worktree, check=False)
        return CiResult(False, logs.stdout[-12000:])

    def is_merged(self, worktree: Path, pr: PullRequest) -> bool:
        view = run(["gh", "pr", "view", str(pr.number), "--json", "state"], worktree)
        return json.loads(view.stdout)["state"] == "MERGED"

    def complete_review(self, worktree: Path, pr: PullRequest) -> None:
        """No GitHub o merge é feito pelo revisor humano, nunca pelo supervisor."""

    def review_comments(self, worktree: Path, pr: PullRequest) -> str:
        view = run(["gh", "pr", "view", str(pr.number), "--json", "reviews,comments"], worktree)
        data = json.loads(view.stdout)
        entries = [*data.get("reviews", []), *data.get("comments", [])]
        return "\n".join(entry["body"] for entry in entries if entry.get("body"))

    def sync_merged(self, worktree: Path) -> None:
        run(["git", "fetch", "origin", "main"], worktree)
        run(["git", "checkout", "--detach", "origin/main"], worktree)

    def tag_release(self, worktree: Path, tag: str) -> None:
        run(["git", "tag", tag], worktree)
        run(["git", "push", "origin", tag], worktree)


class LocalPlatform:
    """Ensaio sem GitHub: branch local como base e CI executada na máquina."""

    name = "local"
    base_ref = LOCAL_BASE_BRANCH

    def prepare_base(self) -> None:
        exists = run(["git", "rev-parse", "--verify", "--quiet", LOCAL_BASE_BRANCH], REPO_ROOT, check=False)
        if exists.returncode != 0:
            run(["git", "branch", LOCAL_BASE_BRANCH, "HEAD"], REPO_ROOT)

    def open_pr(self, worktree: Path, branch: str, title: str, body: str) -> PullRequest:
        return PullRequest(0, f"local:{branch}", branch)

    def push(self, worktree: Path, branch: str) -> None:
        pass

    def wait_ci(self, worktree: Path, pr: PullRequest, service: str) -> CiResult:
        result = run(["bash", "scripts/ci.sh", service], worktree, check=False)
        return CiResult(result.returncode == 0, (result.stdout + result.stderr)[-12000:])

    def is_merged(self, worktree: Path, pr: PullRequest) -> bool:
        head = run(["git", "rev-parse", pr.branch], worktree).stdout.strip()
        base = run(["git", "rev-parse", LOCAL_BASE_BRANCH], worktree).stdout.strip()
        return head == base

    def complete_review(self, worktree: Path, pr: PullRequest) -> None:
        run(["git", "fetch", ".", f"{pr.branch}:{LOCAL_BASE_BRANCH}"], worktree)

    def review_comments(self, worktree: Path, pr: PullRequest) -> str:
        return ""

    def sync_merged(self, worktree: Path) -> None:
        run(["git", "checkout", "--detach", LOCAL_BASE_BRANCH], worktree)

    def tag_release(self, worktree: Path, tag: str) -> None:
        run(["git", "tag", f"rehearsal-{tag}"], worktree)
