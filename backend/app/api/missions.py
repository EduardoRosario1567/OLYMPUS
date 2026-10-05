import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from olympus.agent.mission import AutonomousPatchRunner, MissionSpec, MissionStep
from olympus.routing.omniroute_adapter import OmniRouteAdapter
from app.core.provider_runtime import build_delivery_verifier

router = APIRouter(prefix="/missions", tags=["missions"])


class MissionCreate(BaseModel):
    task: str = Field(min_length=3, max_length=12000)
    max_iterations: int = Field(default=24, ge=1, le=24)


class MissionView(BaseModel):
    id: str
    task: str
    status: str
    created_at: float
    updated_at: float
    elapsed_seconds: int
    models: List[str] = []
    files_modified: List[str] = []
    tests_run: List[str] = []
    confidence: Optional[float] = None
    error: Optional[str] = None


_LOCK = threading.Lock()
_MISSIONS: Dict[str, dict] = {}


def _now() -> float:
    return time.time()


def _public(record: dict) -> dict:
    out = {k: v for k, v in record.items() if not k.startswith("_") and k != "events"}
    out["elapsed_seconds"] = max(0, int(out["updated_at"] - out["created_at"]))
    return out


def _event(mission_id: str, kind: str, **payload) -> None:
    with _LOCK:
        rec = _MISSIONS.get(mission_id)
        if rec is None:
            return
        rec["updated_at"] = _now()
        event = {"seq": len(rec["events"]) + 1, "event": kind, "at": rec["updated_at"]}
        event.update(payload)
        rec["events"].append(event)
        model = payload.get("model")
        if model and model not in rec["models"]:
            rec["models"].append(model)


def _seed_workspace(root: Path) -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "README.md").write_text(
        "# OLYMPUS Web Tester Sandbox\n\nThis workspace is disposable and isolated.\n",
        encoding="utf-8",
    )


def _run_mission(mission_id: str) -> None:
    with _LOCK:
        rec = _MISSIONS[mission_id]
        task = rec["task"]
        max_iterations = rec["_max_iterations"]
        rec["status"] = "running"
        rec["updated_at"] = _now()

    workspace = Path(tempfile.mkdtemp(prefix="olympus-web-"))
    try:
        _seed_workspace(workspace)
        _event(mission_id, "mission_start", isolated=True)
        router_adapter = OmniRouteAdapter(
            base_url=os.environ.get("OLYMPUS_OMNIROUTE_URL", "http://127.0.0.1:20128"),
            api_key=(os.environ.get("OLYMPUS_OMNIROUTE_API_KEY") or os.environ.get("OMNIROUTE_API_KEY") or None),
            timeout_seconds=int(os.environ.get("OLYMPUS_MODEL_TIMEOUT", "30")),
        )
        spec = MissionSpec(
            mission_id,
            "Web Tester Mission",
            (MissionStep("AUTO-1", "Autonomous sandbox mission", task, max_iterations),),
        )
        runner = AutonomousPatchRunner(
            str(workspace),
            router_adapter,
            verifier_factory=build_delivery_verifier,
            telemetry=lambda e: _event(mission_id, e.get("event", "runtime"), **{k: v for k, v in e.items() if k != "event"}),
        )
        result = runner.run(spec)
        models, files, tests = [], [], []
        for item in result.steps:
            for model in item.models_attempted:
                if model not in models:
                    models.append(model)
            state = item.loop_result.state
            for name in state.files_modified:
                if name not in files:
                    files.append(name)
            for name in state.tests_run:
                if name not in tests:
                    tests.append(name)
        with _LOCK:
            rec = _MISSIONS[mission_id]
            rec["status"] = "completed" if result.success else result.status
            rec["models"] = models or rec["models"]
            rec["files_modified"] = files
            rec["tests_run"] = tests
            rec["confidence"] = 1.0 if result.success else 0.0
            rec["error"] = result.error
            rec["updated_at"] = _now()
        _event(mission_id, "mission_end", status=result.status)
    except Exception as exc:
        with _LOCK:
            rec = _MISSIONS[mission_id]
            rec["status"] = "failed"
            rec["error"] = str(exc)
            rec["updated_at"] = _now()
        _event(mission_id, "mission_error", error=str(exc))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@router.post("", response_model=MissionView, status_code=202)
def create_mission(payload: MissionCreate):
    mission_id = uuid.uuid4().hex[:12]
    now = _now()
    record = {
        "id": mission_id,
        "task": payload.task.strip(),
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "models": [],
        "files_modified": [],
        "tests_run": [],
        "confidence": None,
        "error": None,
        "events": [],
        "_max_iterations": payload.max_iterations,
    }
    with _LOCK:
        _MISSIONS[mission_id] = record
    threading.Thread(target=_run_mission, args=(mission_id,), daemon=True).start()
    return _public(record)


@router.get("/{mission_id}", response_model=MissionView)
def get_mission(mission_id: str):
    with _LOCK:
        record = _MISSIONS.get(mission_id)
        if record is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return _public(record)


@router.get("/{mission_id}/events")
def get_events(mission_id: str, after: int = 0):
    with _LOCK:
        record = _MISSIONS.get(mission_id)
        if record is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return {"mission_id": mission_id, "events": [e for e in record["events"] if e["seq"] > after]}
