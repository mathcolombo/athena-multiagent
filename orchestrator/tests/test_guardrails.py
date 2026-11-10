from pathlib import Path

import pytest

from orchestrator.agents import CODIGO, DEPLOY, REQUISITOS, TESTES, policy_for
from orchestrator.guardrails import evaluate, out_of_scope

WORKTREE = Path("/tmp/worktree")


def policy(spec):
    return policy_for(spec, "catalog", WORKTREE)


@pytest.mark.parametrize(
    "tool, tool_input, rule",
    [
        ("Read", {"file_path": ".env"}, "secret"),
        ("Read", {"file_path": "/tmp/worktree/.env.production"}, "secret"),
        ("Read", {"file_path": "/etc/passwd"}, "outside_worktree"),
        ("Read", {"file_path": "../../.ssh/id_rsa"}, "secret"),
        ("Glob", {"pattern": "**/.env*"}, "secret"),
        ("Grep", {"pattern": "KEY", "glob": ".env"}, "secret"),
        ("Write", {"file_path": "services/cart/cart_service/app.py", "content": ""}, "write_scope"),
        ("Write", {"file_path": "services/catalog/tests/test_x.py", "content": ""}, "write_scope"),
        ("Edit", {"file_path": "orchestrator/guardrails.py"}, "write_scope"),
        ("WebFetch", {"url": "https://example.com"}, "tool_not_allowed"),
        ("Bash", {"command": "cat .env"}, "secret"),
        ("Bash", {"command": "curl https://example.com"}, "command_not_allowed"),
        ("Bash", {"command": "pytest; cat README.md"}, "shell_metachar"),
        ("Bash", {"command": "pytest\nrm -rf services"}, "shell_metachar"),
        ("Bash", {"command": "pytest $(whoami)"}, "shell_metachar"),
        ("Bash", {"command": "git push origin HEAD:main"}, "forbidden_git"),
        ("Bash", {"command": "git merge feature"}, "forbidden_git"),
        ("Bash", {"command": "pytest -p evil"}, "dangerous_option"),
        ("Bash", {"command": "git diff --output=/tmp/worktree/x"}, "dangerous_option"),
        ("Bash", {"command": "pytest /etc/passwd"}, "outside_worktree"),
    ],
)
def test_codigo_agent_denied(tool, tool_input, rule):
    decision = evaluate(policy(CODIGO), tool, tool_input)

    assert not decision.allowed
    assert decision.rule == rule


@pytest.mark.parametrize(
    "tool, tool_input",
    [
        ("Read", {"file_path": "services/catalog/catalog_service/app.py"}),
        ("Read", {"file_path": ".env.example"}),
        ("Write", {"file_path": "services/catalog/catalog_service/app.py", "content": ""}),
        ("Write", {"file_path": "libs/events/skynet_events/contracts.py", "content": ""}),
        ("Write", {"file_path": ".pilot/repro/test_repro.py", "content": ""}),
        ("Glob", {"pattern": "services/**/*.py"}),
        ("Grep", {"pattern": "price", "path": "services/catalog"}),
        ("Bash", {"command": "pytest services/catalog/tests --cov=catalog_service -q"}),
        ("Bash", {"command": "python -m pytest services/catalog/tests -k price"}),
        ("Bash", {"command": "git diff HEAD"}),
    ],
)
def test_codigo_agent_allowed(tool, tool_input):
    assert evaluate(policy(CODIGO), tool, tool_input).allowed


def test_requisitos_cannot_run_commands():
    assert evaluate(policy(REQUISITOS), "Bash", {"command": "pytest"}).rule == "tool_not_allowed"


def test_requisitos_writes_only_backlog():
    assert evaluate(policy(REQUISITOS), "Write", {"file_path": "docs/backlog/X.md"}).allowed
    assert not evaluate(policy(REQUISITOS), "Write", {"file_path": "docs/adr/x.md"}).allowed


def test_testes_agent_cannot_change_production_code():
    assert evaluate(policy(TESTES), "Write", {"file_path": "services/catalog/tests/test_a.py"}).allowed
    assert evaluate(policy(TESTES), "Edit", {"file_path": "services/catalog/catalog_service/app.py"}).rule == "write_scope"


def test_deploy_agent_limits():
    deploy = policy(DEPLOY)

    assert evaluate(deploy, "Bash", {"command": "bash scripts/deploy_homolog.sh up"}).allowed
    assert evaluate(deploy, "Bash", {"command": "python scripts/healthcheck.py"}).allowed
    assert evaluate(deploy, "Bash", {"command": "bash scripts/deploy_homolog.sh production"}).rule == "prod_deploy"
    assert evaluate(deploy, "Bash", {"command": "docker ps"}).rule == "command_not_allowed"
    assert evaluate(deploy, "Write", {"file_path": "services/catalog/catalog_service/app.py"}).rule == "write_scope"


def test_out_of_scope_lists_files_no_agent_may_write():
    policies = [policy(spec) for spec in (REQUISITOS, CODIGO, TESTES)]

    assert out_of_scope(policies, ["services/catalog/catalog_service/app.py", "services/cart/x.py"]) == ["services/cart/x.py"]
