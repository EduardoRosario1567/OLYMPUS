"""Internal, non-public candidate path for static website missions.

The model writes via StaticSiteActionExecutor. No generated code executes on
the host. A result is only ARTIFACT_VERIFIED, never a claim of a real-model or
browser-verified delivery. The public /missions API remains fail-closed.
"""
from __future__ import annotations

import re
from pathlib import Path

from olympus.agent.mission import AutonomousPatchRunner, MissionSpec, MissionStep
from olympus.agent.static_site_executor import static_site_loop_factory
from olympus.agent.verifier import AgentVerifier
from scripts.preserve_static_delivery import preserve_validated_site
from scripts.verificar_entrega_estatica import verify


_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class StaticCandidateVerifier(AgentVerifier):
    """Static checks only; NEVER invoke a browser on untrusted generated JS."""

    def verify_task_deliverable(self, task, files_modified, active_skills=()):
        # Do not allow the agent to claim success when only a partial page
        # exists. Browser and design quality are separate acceptance stages.
        issues, count = verify(str(self.root / "site"), str(self.root))
        if count == 0 and not issues:
            issues = ["empty candidate"]
        return tuple("static artifact: " + str(issue) for issue in issues)


def build_static_candidate(workspace, delivery_root, mission_id, task, router,
                           selector=None, planner_factory=None, max_iterations=12):
    """Run a private restricted agent and preserve a validated candidate.

    Caller must choose a trusted provider, approve cost, and supply a fresh
    empty workspace. This function does not authorize provider access.
    """
    if not isinstance(mission_id, str) or not _ID_RE.fullmatch(mission_id):
        raise ValueError("BLOCKED: invalid server-generated mission ID")
    if not isinstance(task, str) or not 3 <= len(task.strip()) <= 12000:
        raise ValueError("BLOCKED: mission instruction is required")
    if router is None:
        raise ValueError("BLOCKED: trusted routing adapter is required")
    root = Path(workspace)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("BLOCKED: invalid workspace")
    root = root.resolve(strict=True)
    if any(root.iterdir()):
        raise ValueError("BLOCKED: fresh empty workspace required")
    destination = Path(delivery_root)
    if destination.is_symlink() or root == destination.resolve() or root in destination.resolve().parents:
        raise ValueError("BLOCKED: delivery root overlaps workspace")
    if (destination / mission_id).exists() or (destination / mission_id).is_symlink():
        raise FileExistsError("BLOCKED: mission delivery already exists")

    # Restrict the *loop's* executor on every model attempt, regardless
    # of instructions returned by the provider or any failover.
    kwargs = {
        "loop_factory": static_site_loop_factory(StaticCandidateVerifier),
        "verifier_factory": StaticCandidateVerifier,
    }
    if selector is not None:
        kwargs["selector"] = selector
    if planner_factory is not None:
        kwargs["planner_factory"] = planner_factory
    runner = AutonomousPatchRunner(str(root), router, **kwargs)
    contract = (
        "STATIC ARTIFACT CANDIDATE. Write only site/index.html and other "
        "text assets under site/. Do not run tests, shell, package managers, "
        "network requests, or modify other folders. Do not claim browser or "
        "visual verification.\n\nUSER REQUEST:\n" + task.strip()
    )
    mission = MissionSpec(mission_id, "Static candidate", (
        MissionStep("SITE", "Generate static files only", contract, max_iterations),
    ))
    result = runner.run(mission, resume=False)
    files = tuple(dict.fromkeys(
        path for step in result.steps for path in step.loop_result.state.files_modified
    ))
    if not result.success:
        return {"status": "BLOCKED", "reason": "agent did not satisfy static candidate contract",
                "model_inference_verified": False, "browser_verified": False}
    if "site/index.html" not in files or any(not p.startswith("site/") for p in files):
        return {"status": "BLOCKED", "reason": "no newly generated site/index.html or invalid output path",
                "model_inference_verified": False, "browser_verified": False}
    try:
        artifact = preserve_validated_site(root, destination, mission_id)
    except (ValueError, OSError, FileExistsError) as exc:
        return {"status": "BLOCKED", "reason": str(exc),
                "model_inference_verified": False, "browser_verified": False}

    return {
        "status": "ARTIFACT_VERIFIED",
        "files": artifact["files"],
        "model_inference_verified": False,
        "browser_verified": False,
        "visual_reviewed": False,
        "source": "restricted_model_agent",
        "delivery_path": artifact["path"],
        "note": "Static checks and preservation only; not a completed mission.",
    }
