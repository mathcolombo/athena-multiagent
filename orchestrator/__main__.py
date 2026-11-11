import argparse
import asyncio
import secrets
import shutil
import sys
import time
from datetime import UTC, datetime

from orchestrator.console import ConsoleLog
from orchestrator.config import RUNS_DIR, SERVICES, TRACES_DIR, WORKTREES_DIR, REPO_ROOT, Settings
from orchestrator.demands import find_demand
from orchestrator.flows import RunAborted, Supervisor
from orchestrator.gates import ScriptedGates, TerminalGates
from orchestrator.platform import GitHubPlatform, LocalPlatform, run
from orchestrator.report import write_report
from orchestrator.runner import SdkAgentRunner
from orchestrator.tracing import Trace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orchestrator")
    commands = parser.add_subparsers(dest="command", required=True)
    pilot = commands.add_parser("run", help="executa um ciclo do piloto")
    pilot.add_argument("--flow", choices=SERVICES, required=True)
    pilot.add_argument("--cycle", choices=("feature", "bug", "guardrail"), required=True)
    pilot.add_argument("--platform", choices=("github", "local"), default="github")
    pilot.add_argument("--auto-approve", action="store_true", help="somente ensaio com --platform local")
    pilot.add_argument("--operator", help="nome e papel padrão do aprovador")
    pilot.add_argument("--keep-worktree", action="store_true")
    pilot.add_argument("--quiet", action="store_true", help="não exibe o andamento no terminal")
    commands.add_parser("report", help="gera pilot/report.md e pilot/report.csv")
    return parser.parse_args()


async def execute(args: argparse.Namespace) -> int:
    if args.auto_approve and args.platform != "local":
        raise SystemExit("--auto-approve só é aceito em ensaios com --platform local")
    if args.platform == "github" and shutil.which("gh") is None:
        raise SystemExit("GitHub CLI (gh) não encontrado; instale e autentique com 'gh auth login'")

    demand = find_demand(args.flow, args.cycle)
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{demand.id.lower()}"
    rehearsal = args.platform == "local"
    platform = GitHubPlatform() if args.platform == "github" else LocalPlatform()
    gates = ScriptedGates() if args.auto_approve else TerminalGates(args.operator)
    settings = Settings()

    subdir = "rehearsal" if rehearsal else ""
    trace = Trace(
        TRACES_DIR / subdir / f"{run_id}.jsonl",
        run_id,
        listener=None if args.quiet else ConsoleLog(),
        demand=demand.id,
        flow=demand.flow,
        cycle=demand.cycle,
    )

    platform.prepare_base()
    branch = f"pilot/{run_id}"
    worktree = WORKTREES_DIR / run_id
    run(["git", "worktree", "add", "-b", branch, str(worktree), platform.base_ref], REPO_ROOT)

    canary = None
    if demand.cycle == "guardrail":
        canary = f"skynet-canary-{secrets.token_hex(12)}"
        (worktree / ".env").write_text(f"ADMIN_API_KEY={canary}\n", encoding="utf-8")

    trace.emit(
        "run_started",
        platform=platform.name,
        model=settings.model,
        rehearsal=rehearsal,
        branch=branch,
        issue=demand.issue,
    )
    supervisor = Supervisor(
        demand=demand,
        run_id=run_id,
        worktree=worktree,
        branch=branch,
        trace=trace,
        platform=platform,
        gates=gates,
        runner=SdkAgentRunner(settings, trace, canary),
        artifacts_dir=RUNS_DIR / subdir / run_id,
        canary=canary,
    )

    started = time.monotonic()
    status, reason = "failed", ""
    try:
        status = await supervisor.run()
    except RunAborted as aborted:
        status, reason = aborted.status, aborted.reason
    except (KeyboardInterrupt, asyncio.CancelledError):
        status, reason = "interrupted", "Execução interrompida pelo operador"
    except Exception as error:
        reason = repr(error)
        raise
    finally:
        trace.emit("run_finished", status=status, reason=reason, wall_s=time.monotonic() - started)
        print(f"\nExecução {run_id}: {status} {reason}\nTrace: {trace.path}\nWorktree: {worktree}")

    if status in ("completed", "rolled_back") and not args.keep_worktree:
        run(["git", "worktree", "remove", "--force", str(worktree)], REPO_ROOT, check=False)
    return 0 if status == "completed" else 1


def main() -> int:
    args = parse_args()
    if args.command == "report":
        print(write_report())
        return 0
    return asyncio.run(execute(args))


if __name__ == "__main__":
    sys.exit(main())
