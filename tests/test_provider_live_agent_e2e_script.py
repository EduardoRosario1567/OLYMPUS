from scripts.provider_live_agent_e2e import validate_html, choose_models, QualificationVerifier


class Row:
    def __init__(self, model_id, available=True):
        self.model_id = model_id
        self.available = available


class Adapter:
    def list_models(self):
        return [
            Row("audio-model", False),
            Row("qwen/qwen3.8-27b"),
            Row("openai/gpt-oss-20b"),
        ]


def test_live_provider_proof_requires_semantic_repair_contract():
    ok, failures = validate_html(
        '<!doctype html><html><body><main><h1>OLYMPUS QUALIFICATION</h1>'
        '<p data-status="ready">ok</p></main></body></html>'
    )
    assert ok is True
    assert failures == []

    ok, failures = validate_html("<html><body><div>OLYMPUS QUALIFICATION</div></body></html>")
    assert ok is False
    assert "missing semantic main" in failures
    assert "missing required h1" in failures
    assert "missing ready status" in failures


def test_live_provider_proof_never_invents_requested_model():
    adapter = Adapter()
    assert choose_models(adapter, "missing-model") == []
    assert choose_models(adapter, "openai/gpt-oss-20b") == ["openai/gpt-oss-20b"]
    candidates = choose_models(adapter, None)
    assert "qwen/qwen3.8-27b" in candidates
    assert "openai/gpt-oss-20b" in candidates
    assert "audio-model" not in candidates


def test_qualification_verifier_rejects_initial_defective_html(tmp_path):
    target = tmp_path / "app" / "index.html"
    target.parent.mkdir(parents=True)
    target.write_text(
        '<!doctype html><html><body><div>OLYMPUS QUALIFICATION</div></body></html>',
        encoding="utf-8",
    )
    verifier = QualificationVerifier(str(tmp_path))
    errors = verifier.verify_task_deliverable(
        "Repair the existing app/index.html.",
        ("app/index.html",),
    )
    assert "qualification: missing semantic main" in errors
    assert "qualification: missing required h1" in errors
    assert "qualification: missing ready status" in errors


def test_qualification_verifier_accepts_exact_contract(tmp_path):
    target = tmp_path / "app" / "index.html"
    target.parent.mkdir(parents=True)
    target.write_text(
        '<!doctype html><html><body><main><h1>OLYMPUS QUALIFICATION</h1>'
        '<p data-status="ready">ok</p></main></body></html>',
        encoding="utf-8",
    )
    verifier = QualificationVerifier(str(tmp_path))
    errors = verifier.verify_task_deliverable(
        "Repair the existing app/index.html.",
        ("app/index.html",),
    )
    assert not [e for e in errors if e.startswith("qualification:")]
