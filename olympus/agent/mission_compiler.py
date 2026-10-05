"""Deterministic translation from a human request to an execution contract.

This module is intentionally model-free.  Human language is normalized into a
stable mission profile before any provider is called.  The profile drives skill
selection, acceptance checks and capability routing; provider prompts receive
that profile instead of raw conversational ambiguity whenever useful.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import re
import unicodedata
from typing import Iterable, Tuple


_WEB_TERMS = (
    "landing page", "pagina", "página", "site", "website", "frontend",
    "front-end", "interface web", "tela web",
)
_GAME_TERMS = ("jogo", "game", "gaming", "gameplay")
_APP_TERMS = ("aplicativo", "application", "app ", " app", "mobile app", "desktop app")
_MATH_TERMS = (
    "calcule", "calcular", "calculo", "cálculo", "matemat", "equação", "equacao",
    "percentual", "porcentagem", "juros", "desconto", "soma", "multiplica", "divis",
)
_DATA_TERMS = ("planilha", "spreadsheet", "csv", "dataset", "dados", "data analysis", "analise de dados", "análise de dados")
_RESEARCH_TERMS = ("pesquise", "pesquisar", "research", "investigue", "fontes", "sources")
_WRITING_TERMS = ("escreva", "redija", "rewrite", "reescreva", "resuma", "summar", "traduza", "translate")
_TEST_TERMS = ("teste", "testes", "test ", "validar", "verificar", "pytest", "unittest")
_NEGATIVE_MARKERS = (
    "não ", "nao ", "sem ", "evite ", "nunca ", "do not ", "without ",
)
_FILE_EXACT_RE = re.compile(
    r"arquivo\s+chamado\s+(\"[^\"\n]+\"|'[^'\n]+'|[^\s,;]+)\s+contendo\s+apenas\s*:\s*(.+?)\s*$",
    re.I | re.S,
)


def _single_space(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _sentences(value: str) -> Tuple[str, ...]:
    lines = re.split(r"(?:\r?\n)+|(?<=[.!?;])\s+|\s+-\s+", value or "")
    cleaned = []
    seen = set()
    for line in lines:
        item = _single_space(re.sub(r"^[\s*•-]+", "", line))
        key = _fold(item)
        if len(item) < 3 or key in seen:
            continue
        cleaned.append(item)
        seen.add(key)
    return tuple(cleaned)


def _exact_file(request: str):
    match = _FILE_EXACT_RE.search((request or "").strip())
    if not match:
        return None
    name = match.group(1).strip().strip('"\'')
    expected = match.group(2).strip()
    if len(expected) >= 2 and expected[0] == expected[-1] and expected[0] in "\"'`" and expected[0] not in expected[1:-1]:
        expected = expected[1:-1]
    # Avoid swallowing a clearly separate follow-up sentence into exact content.
    expected = re.split(r"(?i)(?:\.\s+|;\s+)(?=(?:depois|em seguida|then|after that|rode|execute|verifique|valide)\b)", expected, maxsplit=1)[0].rstrip()
    if not name or name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
        return None
    return name, expected


@dataclass(frozen=True)
class CompiledMission:
    objective: str
    deliverable: str
    requirements: Tuple[str, ...]
    constraints: Tuple[str, ...]
    acceptance: Tuple[str, ...]
    original_sha256: str
    compiler_version: str = "2"
    task_family: str = "software"
    required_skills: Tuple[str, ...] = ()
    supporting_skills: Tuple[str, ...] = ()
    excluded_skills: Tuple[str, ...] = ()
    capability_requirements: Tuple[str, ...] = ()
    exact_text_artifact: Tuple[str, str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def instruction(self) -> str:
        payload = {
            "objective": self.objective,
            "task_family": self.task_family,
            "deliverable": self.deliverable,
            "requirements": list(self.requirements),
            "constraints": list(self.constraints),
            "acceptance": list(self.acceptance),
            "skills": {
                "required": list(self.required_skills),
                "supporting": list(self.supporting_skills),
                "excluded": list(self.excluded_skills),
            },
            "capabilities": list(self.capability_requirements),
        }
        if self.exact_text_artifact:
            payload["exact_text_artifact"] = {
                "path": self.exact_text_artifact[0],
                "expected": self.exact_text_artifact[1],
            }
        return "OLYMPUS_EXECUTION_CONTRACT\n" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        )


class MissionCompiler:
    """Compile human language locally; no tokens, network or provider inference."""

    def compile(self, request: str) -> CompiledMission:
        original = (request or "").strip()
        if not original:
            raise ValueError("mission request is required")
        parts = _sentences(original)
        objective = parts[0] if parts else _single_space(original)
        folded = _fold(original)
        exact = _exact_file(original)
        family, deliverable = self._classify(folded, exact)
        required, supporting, excluded, capabilities = self._skills_for(family, folded)

        constraints = tuple(
            item for item in parts
            if any(marker in _fold(item) for marker in _NEGATIVE_MARKERS)
        )
        method_constraints = ()
        if re.search(r"\b(?:skills?\s+(?:fabric|frabic)|skillsfabric|superpowers)\b", folded):
            method_constraints = (
                "Skills Fabric/Frabic means the OLYMPUS Superpowers advisory method. "
                "It is not a request for Microsoft Fabric UI or a UI dependency. "
                "Introduce such a dependency only when the user explicitly requests it.",
            )
            if re.search(r"\b(?:nova versao|new version|atualiz\w*|update\w*)\b", folded):
                method_constraints += (
                    "Update the existing project deliverable while preserving its identity and purpose. "
                    "Do not substitute an unrelated demonstration of a library for the requested new version.",
                )
        requirements = [item for item in parts[1:] if item not in constraints]
        if family == "web":
            method_constraints += (
                "OLYMPUS_WEB_DELIVERY_V1: Before implementation create docs/delivery-concept.md "
                "with Visual thesis, Content plan, Interaction plan and Evidence sections. "
                "Record confirmed business facts separately from unknown facts; identify assets, "
                "sources and licenses. At finish, independent browser checks inspect the static page in "
                "desktop/tablet/mobile sizes and exercise primary controls; repair reported errors. "
                "Use local assets compatible with the protected preview. Rendered checks do not prove "
                "aesthetic suitability. A configured independent vision reviewer receives the real screenshots "
                "and this concept; repair its actionable findings and rerender before finish. Model opinion is "
                "not human approval. An unavailable vision route remains unassessed and cannot pass its gate.",
            )
        if exact:
            requirements.insert(0, "Create %s with exact content %r" % exact)
        acceptance = list(self._acceptance(family, deliverable, folded, exact))
        for item in parts:
            normalized = _fold(item)
            if any(term in normalized for term in _TEST_TERMS) and item not in acceptance:
                acceptance.append(item)

        return CompiledMission(
            objective=objective[:1000],
            deliverable=deliverable,
            requirements=tuple(requirements[:32]),
            constraints=constraints[:16] + method_constraints,
            acceptance=tuple(acceptance[:20]),
            original_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
            task_family=family,
            required_skills=required,
            supporting_skills=supporting,
            excluded_skills=excluded,
            capability_requirements=capabilities,
            exact_text_artifact=exact,
        )

    @staticmethod
    def _classify(folded: str, exact):
        if exact:
            return "file_operation", "exact_text_file"
        if any(_fold(term) in folded for term in _WEB_TERMS):
            return "web", "static_web"
        if any(_fold(term) in folded for term in _GAME_TERMS):
            return "game", "software_change"
        if any(_fold(term) in folded for term in _APP_TERMS):
            return "application", "software_change"
        if any(_fold(term) in folded for term in _MATH_TERMS):
            return "mathematics", "calculation"
        if any(_fold(term) in folded for term in _DATA_TERMS):
            return "data_analysis", "analysis"
        if any(_fold(term) in folded for term in _RESEARCH_TERMS):
            return "research", "research_result"
        if any(_fold(term) in folded for term in _WRITING_TERMS):
            return "writing", "text_result"
        return "software", "software_change"

    @staticmethod
    def _skills_for(family: str, folded: str):
        if family == "file_operation":
            supporting = ("testing",) if any(term in folded for term in _TEST_TERMS) else ()
            excluded = ("frontend", "product-experience", "visual-design", "accessibility", "ui-ux-pro-max", "web-design-guidelines")
            return ("file-operations",), supporting, excluded, ("structured_output", "tool_use")
        if family == "web":
            return ("frontend",), (), (), ("coding", "tool_use", "structured_output")
        if family == "game":
            return ("game-development", "coding"), ("testing",), (), ("coding", "reasoning", "tool_use")
        if family == "application":
            return ("app-architecture", "coding"), ("testing", "security"), (), ("coding", "reasoning", "tool_use")
        if family == "mathematics":
            return ("mathematics",), (), ("frontend", "visual-design", "accessibility"), ("reasoning", "numerical")
        if family == "data_analysis":
            return ("data-analysis",), ("mathematics",), (), ("reasoning", "data")
        if family == "research":
            return ("research",), (), (), ("reasoning", "long_context")
        if family == "writing":
            return ("writing",), (), (), ("text",)
        return ("coding",), ("testing",), (), ("coding", "tool_use", "structured_output")

    @staticmethod
    def _acceptance(family: str, deliverable: str, folded: str, exact) -> Iterable[str]:
        if exact:
            return (
                "The requested file exists inside the workspace",
                "Its text content exactly equals the requested value",
                "No unrelated file is required to change",
            )
        if deliverable == "static_web":
            checks = [
                "Create a complete runnable web entrypoint in app/index.html",
                "Render meaningful content without external runtime dependencies",
                "Work at desktop and mobile widths",
                "Keep navigation and interactive controls keyboard accessible",
                "Run deterministic web quality verification before finish",
            ]
            if "form" in folded or "contato" in folded:
                checks.append("Make the requested form usable and validate its interaction")
            return checks
        if family == "mathematics":
            return ("Recompute the numerical result deterministically before finish", "Preserve units and stated assumptions")
        return (
            "Preserve existing behavior outside the requested scope",
            "Run the smallest relevant deterministic verification before finish",
            "Finish only after the requested outcome exists in project files",
        )
