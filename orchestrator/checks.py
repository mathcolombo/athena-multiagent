import ast
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import MAX_TASKS
from orchestrator.platform import run

COVERAGE_LINE = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", re.MULTILINE)
JS_TEST_CALL = re.compile(r"^\s*(?:test|it)\(\s*([\"'`])(.+?)\1", re.MULTILINE)
JS_ASSERTION = re.compile(r"\bassert(\.\w+)?\(|\bexpect\(")
TASK_HEADING = re.compile(r"^###\s+(T\d+):\s*(.+?)\s*$", re.MULTILINE)
NEXT_SECTION = re.compile(r"^##\s", re.MULTILINE)
PYTEST_TESTS_FAILED = 1


def changed_files(worktree: Path) -> list[str]:
    output = run(["git", "status", "--porcelain", "--untracked-files=all"], worktree).stdout
    return [line[3:].strip().strip('"') for line in output.splitlines()]


def changed_since(worktree: Path, base_ref: str) -> list[str]:
    output = run(["git", "diff", "--name-only", f"{base_ref}...HEAD"], worktree).stdout
    return output.split()


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    body: str


def parse_tasks(story: str) -> list[Task]:
    headings = list(TASK_HEADING.finditer(story))
    tasks = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(story)
        segment = story[heading.end():end]
        section_end = NEXT_SECTION.search(segment)
        body = segment[: section_end.start()] if section_end else segment
        tasks.append(Task(heading.group(1), heading.group(2), body.strip()))
    return tasks


def story_problems(path: Path) -> list[str]:
    if not path.exists():
        return [f"arquivo da história não foi criado: {path.name}"]
    text = path.read_text(encoding="utf-8")
    problems = []
    if not re.search(r"^\s*(Cenário|Scenario):", text, re.MULTILINE):
        problems.append("nenhum cenário BDD (linha 'Cenário:') encontrado")
    if not re.search(r"^\s*Regra:\s*\S+", text, re.MULTILINE):
        problems.append("história não rastreada a uma regra (linha 'Regra: <id>')")
    tasks = parse_tasks(text)
    if not tasks:
        problems.append("nenhuma task no formato '### T1: <título>' na seção '## Tasks'")
    if len(tasks) > MAX_TASKS:
        problems.append(f"{len(tasks)} tasks; o máximo é {MAX_TASKS}")
    if len({task.id for task in tasks}) != len(tasks):
        problems.append("identificadores de task repetidos")
    for task in tasks:
        if not re.search(r"^\s*Cenários:\s*\S+", task.body, re.MULTILINE):
            problems.append(f"{task.id} não indica os cenários que cobre (linha 'Cenários: ...')")
    return problems


def is_python_test(path: str) -> bool:
    return "/tests/" in path and Path(path).name.startswith("test_") and path.endswith(".py")


def is_js_test(path: str) -> bool:
    return path.startswith("web/tests/") and path.endswith(".test.js")


def is_test_file(path: str) -> bool:
    return is_python_test(path) or is_js_test(path)


def js_tests_without_assertions(source: str) -> list[str]:
    calls = list(JS_TEST_CALL.finditer(source))
    empty = []
    for index, call in enumerate(calls):
        end = calls[index + 1].start() if index + 1 < len(calls) else len(source)
        if not JS_ASSERTION.search(source[call.end():end]):
            empty.append(call.group(2))
    return empty


def tests_without_assertions(worktree: Path, files: list[str]) -> list[str]:
    """Critério 'sem asserções vazias' da seção 2.2."""
    empty = []
    for name in files:
        path = worktree / name
        if path.exists() and is_js_test(name):
            empty += [f"{name}::{title}" for title in js_tests_without_assertions(path.read_text(encoding="utf-8"))]
            continue
        if not (path.exists() and is_python_test(name)):
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
            python_tests = [name for name in test_files if is_python_test(name)]
            js_tests = [name for name in test_files if is_js_test(name)]
            failed, output = False, ""
            if python_tests:
                result: subprocess.CompletedProcess[str] = run(["pytest", *python_tests, "-q", "--no-header"], checkout, check=False)
                failed |= result.returncode == PYTEST_TESTS_FAILED
                output += result.stdout[-3000:]
            if js_tests:
                result = run(["node", "--test", *js_tests], checkout, check=False)
                failed |= result.returncode != 0
                output += result.stdout[-3000:]
            return failed, output
        finally:
            run(["git", "worktree", "remove", "--force", str(checkout)], worktree, check=False)
