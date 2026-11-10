import json
import subprocess
from pathlib import Path

import pytest

from orchestrator.demands import Demand
from orchestrator.flows import RunAborted, Supervisor
from orchestrator.gates import GateDecision, ScriptedGates
from orchestrator.platform import CiResult, PullRequest
from orchestrator.runner import AgentResult
from orchestrator.tracing import Trace

STORY = "# H\n\nRegra: RN-01\n\nCenário: ok\n"
REJECT = GateDecision("rejected", "faltou caso", "rev", 1.0, 2.0, "qualidade_codigo", "ambos")


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/healthcheck.py").write_text("print('ok')\n")
    (tmp_path / "scripts/deploy_homolog.sh").write_text('mkdir -p .pilot && echo "$1" >> .pilot/deploy.log\n')
    (tmp_path / "services/catalog/tests").mkdir(parents=True)
    (tmp_path / "services/catalog/mod.py").write_text("VALUE = 1\n")
    (tmp_path / "docs/backlog").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text(".pilot/\n__pycache__/\n.pytest_cache/\n.coverage\n")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["services/catalog"]\naddopts = "--import-mode=importlib"\n')
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "base")
    git(tmp_path, "checkout", "-b", "work")
    return tmp_path


class FakePlatform:
    name = "fake"
    base_ref = "main"

    def __init__(self, ci=(True,), merged=(True,)):
        self.ci = list(ci)
        self.merged = list(merged)
        self.tags = []

    def prepare_base(self): ...
    def open_pr(self, worktree, branch, title, body): return PullRequest(1, "url", branch)
    def push(self, worktree, branch): ...
    def wait_ci(self, worktree, pr, service): return CiResult(self.ci.pop(0) if self.ci else True, "log")
    def is_merged(self, worktree, pr): return self.merged.pop(0) if self.merged else True
    def complete_review(self, worktree, pr): ...
    def review_comments(self, worktree, pr): return ""
    def sync_merged(self, worktree): ...
    def tag_release(self, worktree, tag): self.tags.append(tag)


class FakeRunner:
    """Simula os agentes escrevendo arquivos no worktree."""

    def __init__(self, repo, test_body="from mod import VALUE\n\ndef test_ok():\n    assert VALUE == 2\n"):
        self.repo = repo
        self.test_body = test_body
        self.calls = []
        self.errors = {}

    async def __call__(self, spec, prompt, service, worktree):
        self.calls.append(spec.name)
        if spec.name in self.errors:
            return AgentResult(spec.name, "", True, self.errors[spec.name], 0.0)
        if spec.name == "requisitos":
            (worktree / "docs/backlog/D-1.md").write_text(STORY)
        elif spec.name == "codigo":
            (worktree / "services/catalog/mod.py").write_text("VALUE = 2\n")
        elif spec.name == "testes":
            (worktree / "services/catalog/tests/test_mod.py").write_text(self.test_body)
        elif spec.name == "deploy":
            (worktree / ".pilot").mkdir(exist_ok=True)
            (worktree / ".pilot/deploy_report.md").write_text("STATUS: OK\n")
        return AgentResult(spec.name, "ok", False, "success", 0.1)


def build(repo, tmp_path_factory, cycle="feature", gates=None, platform=None, runner=None):
    trace_path = tmp_path_factory.mktemp("trace") / "t.jsonl"
    runner = runner or FakeRunner(repo)
    platform = platform or FakePlatform()
    supervisor = Supervisor(
        demand=Demand("D-1", "catalog", cycle, "título", "corpo"),
        run_id="r1",
        worktree=repo,
        branch="work",
        trace=Trace(trace_path, "r1", demand="D-1", flow="catalog", cycle=cycle),
        platform=platform,
        gates=gates or ScriptedGates(),
        runner=runner,
        artifacts_dir=trace_path.parent / "artifacts",
    )
    return supervisor, runner, platform, trace_path


def events(path, kind):
    return [e for e in map(json.loads, path.read_text().splitlines()) if e["event"] == kind]


async def test_feature_passes_all_gates_in_order(repo, tmp_path_factory):
    supervisor, runner, platform, trace = build(repo, tmp_path_factory)

    assert await supervisor.run() == "completed"
    assert [e["gate"] for e in events(trace, "gate_decision")] == ["G3", "G5", "G7"]
    assert runner.calls == ["requisitos", "codigo", "testes", "deploy"]
    assert platform.tags == ["release/r1"]


def test_pr_body_closes_demand_issue(repo, tmp_path_factory):
    supervisor, _, _, _ = build(repo, tmp_path_factory)
    supervisor.demand = Demand("D-1", "catalog", "feature", "título", "corpo", issue=7)

    assert "Closes #7" in supervisor._pr_body()


def deploy_calls(repo):
    log = repo / ".pilot/deploy.log"
    return log.read_text().split() if log.exists() else []


async def test_approved_release_keeps_environment_running(repo, tmp_path_factory):
    supervisor, _, _, _ = build(repo, tmp_path_factory)

    assert await supervisor.run() == "completed"
    assert "down" not in deploy_calls(repo)


async def test_g5_waits_for_merge_without_new_gate_decision(repo, tmp_path_factory):
    supervisor, _, _, trace = build(repo, tmp_path_factory, platform=FakePlatform(merged=(False, False, True)))

    assert await supervisor.run() == "completed"
    assert [e["gate"] for e in events(trace, "gate_decision")] == ["G3", "G5", "G7"]
    assert len(events(trace, "merge_pending")) == 2
    assert not events(trace, "failure")


async def test_bug_cycle_skips_requirements(repo, tmp_path_factory):
    supervisor, runner, _, trace = build(repo, tmp_path_factory, cycle="bug")

    assert await supervisor.run() == "completed"
    assert runner.calls == ["codigo", "testes", "deploy"]
    assert [e["gate"] for e in events(trace, "gate_decision")] == ["G5", "G7"]
    assert events(trace, "regression_check")[0]["failed_on_base"] is True


async def test_tautological_regression_test_is_rejected(repo, tmp_path_factory):
    runner = FakeRunner(repo, test_body="def test_ok():\n    assert 1 == 1\n")
    supervisor, _, _, trace = build(repo, tmp_path_factory, cycle="bug", runner=runner)

    with pytest.raises(RunAborted):
        await supervisor.run()
    assert events(trace, "failure")[0]["category"] == "teste_tautologico"


async def test_test_without_assertion_is_rejected(repo, tmp_path_factory):
    runner = FakeRunner(repo, test_body="def test_ok():\n    pass\n")
    supervisor, _, _, trace = build(repo, tmp_path_factory, runner=runner)

    with pytest.raises(RunAborted):
        await supervisor.run()
    assert "testes sem asserção" in events(trace, "quality_check")[0]["problems"][0]


async def test_g5_rejection_reruns_agents_and_counts(repo, tmp_path_factory):
    approve = GateDecision("approved", "", "rev", 1.0, 1.0)
    gates = ScriptedGates([approve, REJECT, approve, approve])
    supervisor, runner, _, trace = build(repo, tmp_path_factory, gates=gates)

    assert await supervisor.run() == "completed"
    assert runner.calls.count("codigo") == 2
    assert [e["decision"] for e in events(trace, "gate_decision") if e["gate"] == "G5"] == ["rejected", "approved"]
    assert events(trace, "failure")[0]["category"] == "qualidade_codigo"


async def test_ci_failure_sends_log_to_code_agent(repo, tmp_path_factory):
    supervisor, runner, _, trace = build(repo, tmp_path_factory, platform=FakePlatform(ci=(False, True)))

    assert await supervisor.run() == "completed"
    assert runner.calls.count("codigo") == 2
    assert [e["passed"] for e in events(trace, "ci_result")] == [False, True]


async def test_g7_rejection_does_not_release(repo, tmp_path_factory):
    approve = GateDecision("approved", "", "rev", 1.0, 1.0)
    gates = ScriptedGates([approve, approve, REJECT])
    supervisor, _, platform, trace = build(repo, tmp_path_factory, gates=gates)

    assert await supervisor.run() == "rolled_back"
    assert platform.tags == []
    assert events(trace, "rollback")
    assert deploy_calls(repo) == ["down"]


async def test_budget_exhaustion_aborts_with_category(repo, tmp_path_factory):
    runner = FakeRunner(repo)
    runner.errors["codigo"] = "error_max_budget_usd"
    supervisor, _, _, trace = build(repo, tmp_path_factory, runner=runner)

    with pytest.raises(RunAborted):
        await supervisor.run()
    assert events(trace, "failure")[0]["category"] == "limite_execucao"


async def test_out_of_scope_file_blocks_commit(repo, tmp_path_factory):
    class Rogue(FakeRunner):
        async def __call__(self, spec, prompt, service, worktree):
            result = await super().__call__(spec, prompt, service, worktree)
            if spec.name == "testes":
                (worktree / "scripts/rogue.sh").write_text("x")
            return result

    supervisor, _, _, trace = build(repo, tmp_path_factory, runner=Rogue(repo))

    with pytest.raises(RunAborted):
        await supervisor.run()
    assert events(trace, "failure")[0]["category"] == "violacao_escopo"
