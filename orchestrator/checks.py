import ast
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from orchestrator.platform import run

COVERAGE_LINE = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", re.MULTILINE)
PYTEST_TESTS_FAILED = 1


def changed_files(worktree: Path) -> list[str]:
    output = run(["git", "status", "--porcelain", "--untracked-files=all"], worktree).stdout
    return [line[3:].strip().strip('"') for line in output.splitlines()]


def changed_since(worktree: Path, base_ref: str) -> list[str]:
    output = run(["git", "diff", "--name-only", f"{base_ref}...HEAD"], worktree).stdout
    return output.split()


def story_problems(path: Path) -> list[str]:
    if not path.exists():
        return [f"arquivo da história não foi criado: {path.name}"]
    text = path.read_text(encoding="utf-8")
    problems = []
    if not re.search(r"^\s*(Cenário|Scenario):", text, re.MULTILINE):
        problems.append("nenhum cenário BDD (linha 'Cenário:') encontrado")
    if not re.search(r"^\s*Regra:\s*\S+", text, re.MULTILINE):
        problems.append("história não rastreada a uma regra (linha 'Regra: <id>')")
    return problems


def tests_without_assertions(worktree: Path, files: list[str]) -> list[str]:
    """Critério 'sem asserções vazias' da seção 2.2."""
    empty = []
    for name in files:
        path = worktree / name
        if not (path.exists() and path.name.startswith("test_") and path.suffix == ".py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"):
                body = list(ast.walk(node))
                has_assert = any(isinstance(item, ast.Assert) for item in body)
                has_raises = any(isinstance(item, ast.Attribute) and item.attr == "raises" for item in body)
                if not (has_assert or has_raises):
                    empty.append(f"{name}::{node.name}")
    return empty


def coverage_percent(worktree: Path, service: str) -> int | None:
    result = run(
        ["pytest", f"services/{service}/tests", f"--cov={service}_service", "-q", "--no-header"],
        worktree,
        check=False,
    )
    match = COVERAGE_LINE.search(result.stdout)
    return int(match.group(1)) if match else None


def regression_fails_without_fix(worktree: Path, base_ref: str, test_files: list[str]) -> tuple[bool, str]:
    """Roda os testes novos sobre o código-base: um teste de regressão válido precisa falhar."""
    with tempfile.TemporaryDirectory(prefix="pilot-regression-") as tmp:
        checkout = Path(tmp) / "base"
        run(["git", "worktree", "add", "--detach", str(checkout), base_ref], worktree)
        try:
            for name in test_files:
                target = checkout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(worktree / name, target)
            result: subprocess.CompletedProcess[str] = run(["pytest", *test_files, "-q", "--no-header"], checkout, check=False)
            return result.returncode == PYTEST_TESTS_FAILED, result.stdout[-4000:]
        finally:
            run(["git", "worktree", "remove", "--force", str(checkout)], worktree, check=False)
