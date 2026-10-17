import ast
import json
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence, Tuple

from olympus.agent.test_runner import TargetedTestRunner
from olympus.agent.browser_delivery import WebDeliveryVerifier
from olympus.agent.verification_engine import (
    CheckStatus,
    VerificationCheck,
    VerificationEngine,
    VerificationEvidence,
    VerificationPlan,
    VerificationReport,
)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: Tuple[str, ...]
    errors: Tuple[str, ...]
    report: VerificationReport


class _WebQualityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags = []
        self.text = []
        self.attributes = []
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag.lower())
        self.nodes.append((tag.lower(), {str(name).lower(): str(value or "").lower() for name, value in attrs}))
        self.attributes.extend(
            (str(name).lower(), str(value or "").lower()) for name, value in attrs
        )

    def handle_data(self, data):
        clean = str(data or "").strip()
        if clean:
            self.text.append(clean)


class AgentVerifier:
    def __init__(self, root: str, visual_reviewer=None) -> None:
        self.root = Path(root).resolve()
        self.test_runner = TargetedTestRunner(str(self.root))
        self.engine = VerificationEngine()
        self.browser_verifier = WebDeliveryVerifier(self.root)
        self.delivery_review = None
        self.visual_reviewer = visual_reviewer

    def verify_task_deliverable(
        self,
        task: str,
        files_modified: Sequence[str],
        active_skills: Sequence[str] = (),
    ) -> Tuple[str, ...]:
        """Reject syntactically valid web placeholders that do not satisfy the request."""
        self.delivery_review = None
        objective = str(task or "").lower()
        requires_concept = "olympus_web_delivery_v1" in objective
        if objective.startswith("olympus_execution_contract\n"):
            try:
                contract=json.loads(str(task).split("\n",1)[1])
                objective=" ".join(
                    [str(contract.get("objective") or "")]
                    + [str(item) for item in contract.get("requirements") or ()]
                    + [str(item) for item in contract.get("constraints") or ()
                       if not str(item).startswith("OLYMPUS_WEB_DELIVERY_V1:")]
                    + [str(contract.get("deliverable") or "")]
                ).lower()
            except (ValueError,TypeError,AttributeError):
                pass
        web_tokens = (
            "landing page", "página", "pagina", "site", "website",
            "interface web", "aplicativo web", "aplicação web", "aplicacao web",
            "frontend", "botão", "botao", "button", "ao clicar",
        )
        if not any(token in objective for token in web_tokens):
            return ()
        html_files = [
            relative for relative in files_modified
            if Path(relative).suffix.lower() in {".html", ".htm"}
        ]
        if not html_files:
            return ("deliverable quality: the requested web page was not created",)

        if requires_concept:
            concept_path = self.root / "docs/delivery-concept.md"
            try:
                if concept_path.is_symlink() or concept_path.parent.is_symlink():
                    raise ValueError("linked delivery concept")
                concept = concept_path.read_text(encoding="utf-8").lower()
                required_sections = ("visual thesis", "content plan", "interaction plan", "evidence")
                if len(concept.strip()) < 160 or any(section not in concept for section in required_sections):
                    raise ValueError("incomplete delivery concept")
            except (OSError, ValueError):
                return ("deliverable quality: create docs/delivery-concept.md with Visual thesis, Content plan, Interaction plan and Evidence; include confirmed facts, unknown facts and review limits",)

        primary = "app/index.html" if "app/index.html" in html_files else html_files[0]
        path = (self.root / primary).resolve()
        try:
            path.relative_to(self.root)
            source = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return ("deliverable quality: the main web page cannot be inspected",)

        parser = _WebQualityParser()
        try:
            parser.feed(source)
            parser.close()
        except (ValueError, TypeError):
            return ("deliverable quality: the main web page is malformed",)

        visible = " ".join(parser.text).strip()
        visible_words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", visible)
        tags = set(parser.tags)
        attrs = parser.attributes
        errors = []
        skill_ids = set(active_skills)
        detailed_request = len(re.findall(r"[A-Za-zÀ-ÿ0-9]+", objective)) >= 12

        if visible.lower() in {"welcome", "hello", "hello world", "olympus"} or len(visible_words) < 4:
            errors.append("replace the placeholder with the complete requested page")
        elif detailed_request and (len(source) < 600 or len(visible_words) < 18):
            errors.append("the page is too incomplete for the detailed request")
        if "olympus" in objective and "olympus" not in source.lower():
            pass  # OLYMPUS 3.0.7: legacy global Olympus identity gate disabled
        if "menu" in objective and "nav" not in tags:
            errors.append("include the requested navigation menu")
        if "responsiv" in objective:
            has_viewport = any(
                name == "name" and value == "viewport" for name, value in attrs
            )
            if not has_viewport:
                errors.append("include a responsive viewport")
        if any(token in objective for token in ("botão", "botao", "button")) and not ({"button", "a"} & tags):
            errors.append("include the requested action button")
        if any(token in objective for token in ("fundo", "destaque", "design", "profissional")):
            has_styles = "style" in tags or any(
                name == "rel" and value == "stylesheet" for name, value in attrs
            )
            if not has_styles:
                errors.append("include the requested visual styling")

        def fold(value: str) -> str:
            return "".join(
                character for character in unicodedata.normalize("NFKD", value)
                if not unicodedata.combining(character)
            ).lower()

        # Inspect the whole static application, not only index.html.  A page
        # can be syntactically valid while its linked data and behavior never
        # initialize in the browser.
        text_sources = {}
        for relative in files_modified:
            if Path(relative).suffix.lower() not in {".html", ".htm", ".css", ".js"}:
                continue
            candidate = (self.root / relative).resolve()
            try:
                candidate.relative_to(self.root)
                text_sources[relative] = candidate.read_text(encoding="utf-8")
            except (OSError, ValueError, UnicodeError):
                continue
        combined_source = "\n".join(text_sources.values())
        folded_objective = fold(objective)
        folded_source = fold(combined_source)

        # A static HTML parse is not enough for an interactive deliverable.
        # When the request explicitly asks for a click result, reject pages
        # that merely contain a button but have no browser-side click path.
        # This is intentionally conservative: it accepts either an inline
        # onclick handler or a JS event listener/delegated click handler.
        interaction_requested = (
            ("ao clicar" in folded_objective or "ao click" in folded_objective
             or "quando clicar" in folded_objective or "on click" in folded_objective)
            and ("botao" in folded_objective or "button" in folded_objective)
        )
        if interaction_requested:
            has_click_path = bool(re.search(
                r"(?is)(?:onclick\s*=|addEventListener\s*\(\s*['\"]click['\"]|\.onclick\s*=|\bon\s*click\b)",
                combined_source,
            ))
            if not has_click_path:
                errors.append("implement the requested click interaction before finishing")
            expected_result = tuple(dict.fromkeys(
                re.findall(r"(?:exibir|mostrar|demonstrar|apresentar)\s+[\"'“”]?([^\"'“”\.\n]+)", objective)
            ))
            for expected in expected_result:
                clean_expected = expected.strip()
                if len(clean_expected) >= 3 and fold(clean_expected) not in folded_source:
                    errors.append("include the requested click result: %s" % clean_expected)

        required_paths = tuple(dict.fromkeys(re.findall(
            r"\b(?:[a-z0-9_.-]+/)*[a-z0-9_.-]+\.(?:html?|css|js)\b",
            objective,
            flags=re.IGNORECASE,
        )))
        missing_paths = tuple(
            relative for relative in required_paths
            if not (self.root / relative).is_file()
        )
        if missing_paths:
            errors.append("create every explicitly requested file: %s" % ", ".join(missing_paths))

        javascript = "\n".join(
            content for relative, content in text_sources.items()
            if Path(relative).suffix.lower() == ".js"
        )
        declarations = set(re.findall(
            r"(?m)^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)",
            javascript,
        ))
        inaccessible_globals = tuple(sorted(
            name for name in declarations
            if re.search(r"\bwindow\.%s\b" % re.escape(name), javascript)
            and not re.search(r"\bwindow\.%s\s*=(?!=)" % re.escape(name), javascript)
        ))
        if inaccessible_globals:
            errors.append(
                "repair JavaScript initialization: lexical globals are read through window (%s)"
                % ", ".join(inaccessible_globals)
            )

        linked_scripts = set(re.findall(
            r"(?is)<script[^>]+src\s*=\s*['\"]([^'\"]+\.js)['\"]",
            source,
        ))
        dynamically_loaded = set(re.findall(
            r"\.src\s*=\s*['\"]([^'\"]+\.js)['\"]",
            javascript,
        ))
        duplicated_scripts = tuple(sorted(linked_scripts & dynamically_loaded))
        if duplicated_scripts:
            errors.append(
                "load each JavaScript resource only once: %s"
                % ", ".join(duplicated_scripts)
            )

        if "mobile" in folded_objective and "responsiv" in folded_objective:
            styles = "\n".join(
                content for relative, content in text_sources.items()
                if Path(relative).suffix.lower() == ".css"
            ) + "\n" + "\n".join(re.findall(r"(?is)<style[^>]*>(.*?)</style>", source))
            if "@media" not in styles.lower():
                errors.append("add the requested explicit mobile responsive layout")

        if ("pesquis" in folded_objective and "filtr" in folded_objective):
            search_control = re.search(
                r"(?is)<input[^>]+(?:type\s*=\s*['\"]search['\"]|(?:id|name|class)\s*=\s*['\"][^'\"]*(?:search|pesquis)[^'\"]*['\"])",
                source,
            )
            if not search_control:
                errors.append("implement the requested search control and filters")

        if "restaurar dados" in folded_objective and "restaur" not in folded_source:
            errors.append("implement the requested restore demonstration data control")

        group_operations = (
            ("criar grupo", "criar"),
            ("editar nome", "editar"),
            ("ativar ou desativar", "desativ"),
            ("excluir somente", "exclu"),
            ("arquivar", "arquiv"),
        )
        if "grupo" in folded_objective:
            missing_operations = tuple(
                label for requirement, label in group_operations
                if requirement in folded_objective and label not in folded_source
            )
            if missing_operations:
                errors.append(
                    "implement the requested group management operations: %s"
                    % ", ".join(missing_operations)
                )

        placeholder_patterns = (
            r"\blorem ipsum\b",
            r"\bcoming soon\b",
            r"\bem breve\b",
        )
        if "product-experience" in skill_ids:
            has_placeholder = any(
                re.search(pattern, visible, flags=re.IGNORECASE)
                for pattern in placeholder_patterns
            ) or bool(re.search(r"\bTODO\b", visible))
            if has_placeholder:
                errors.append("remove placeholder or unfinished content")
            if detailed_request and len(visible_words) < 45:
                errors.append("add complete, specific content for the professional experience")
            if "main" not in tags or "h1" not in tags:
                errors.append("provide a semantic main area with one clear primary heading")
            content_blocks = parser.tags.count("section") + parser.tags.count("article")
            if detailed_request and content_blocks < 3:
                errors.append("build a complete information hierarchy with meaningful sections")

        if "visual-design" in skill_ids:
            inline_styles = " ".join(re.findall(r"(?is)<style[^>]*>(.*?)</style>", source))
            external_styles = []
            for relative in files_modified:
                if Path(relative).suffix.lower() != ".css":
                    continue
                candidate = (self.root / relative).resolve()
                try:
                    candidate.relative_to(self.root)
                    external_styles.append(candidate.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
            styles = inline_styles + "\n" + "\n".join(external_styles)
            if len(re.sub(r"\s+", "", styles)) < 300:
                errors.append("replace default styling with a deliberate visual system")
            if "responsiv" in objective and "@media" not in styles.lower():
                errors.append("add an intentional mobile layout, not only a viewport declaration")

        if "accessibility" in skill_ids:
            html_nodes = [attrs for tag, attrs in parser.nodes if tag == "html"]
            if not html_nodes or not html_nodes[0].get("lang"):
                errors.append("declare the document language")
            if "title" not in tags:
                errors.append("provide a descriptive document title")
            images = [attrs for tag, attrs in parser.nodes if tag == "img"]
            if any("alt" not in attrs for attrs in images):
                errors.append("provide alt text for every image")

        if not errors:
            if requires_concept:
                browser_errors, self.delivery_review = self.browser_verifier.verify(primary)
                if not browser_errors and self.visual_reviewer is not None:
                    try:
                        images = self.browser_verifier.evidence_images(self.delivery_review['content_sha256'])
                        concept = (self.root/'docs/delivery-concept.md').read_text(encoding='utf-8')
                        visual_errors, opinion = self.visual_reviewer.review(task,concept,self.delivery_review,images)
                        if not self.browser_verifier.content_matches(primary,self.delivery_review['content_sha256']):
                            visual_errors, opinion = self.visual_reviewer.unavailable('delivery_changed during visual inspection')
                    except (OSError,ValueError,KeyError):
                        visual_errors, opinion = self.visual_reviewer.unavailable('screenshot evidence could not be verified')
                    self.delivery_review = dict(self.delivery_review, visual=opinion['status'],visual_review=opinion)
                    return visual_errors
                return browser_errors
            return ()
        return ("deliverable quality: " + "; ".join(errors),)

    def verify(self, files_modified: Sequence[str], tests: Sequence[str] = ()) -> VerificationResult:
        legacy_checks, errors, structured = [], [], []
        for relative in files_modified:
            path = (self.root / relative).resolve()
            integrity_name = "file:%s" % relative
            legacy_checks.append(integrity_name)
            try:
                path.relative_to(self.root)
                exists_and_nonempty = path.is_file() and path.stat().st_size > 0
            except (OSError, ValueError):
                exists_and_nonempty = False
            if exists_and_nonempty:
                structured.append(VerificationCheck(integrity_name, CheckStatus.PASS, (
                    VerificationEvidence("file", "%s exists and is non-empty" % relative),
                )))
            else:
                message = "%s is missing or empty" % relative
                errors.append(message)
                structured.append(VerificationCheck(integrity_name, CheckStatus.FAIL, (
                    VerificationEvidence("file", message),
                )))
                continue

            if path.suffix == ".py" and path.is_file():
                name = "syntax:%s" % relative
                legacy_checks.append(name)
                try:
                    ast.parse(path.read_text(encoding="utf-8"))
                    structured.append(VerificationCheck(name, CheckStatus.PASS, (
                        VerificationEvidence("syntax", "%s parsed successfully" % relative),
                    )))
                except SyntaxError as exc:
                    message = "%s: %s" % (relative, exc)
                    errors.append(message)
                    structured.append(VerificationCheck(name, CheckStatus.FAIL, (
                        VerificationEvidence("syntax", message),
                    )))
            elif path.suffix == ".json" and path.is_file():
                name = "json:%s" % relative
                legacy_checks.append(name)
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                    structured.append(VerificationCheck(name, CheckStatus.PASS, (
                        VerificationEvidence("syntax", "%s contains valid JSON" % relative),
                    )))
                except (OSError, ValueError) as exc:
                    message = "%s: %s" % (relative, exc)
                    errors.append(message)
                    structured.append(VerificationCheck(name, CheckStatus.FAIL, (
                        VerificationEvidence("syntax", message),
                    )))
            elif path.suffix in {".html", ".htm"} and path.is_file():
                name = "html:%s" % relative
                legacy_checks.append(name)
                try:
                    parser = HTMLParser()
                    parser.feed(path.read_text(encoding="utf-8"))
                    parser.close()
                    structured.append(VerificationCheck(name, CheckStatus.PASS, (
                        VerificationEvidence("syntax", "%s parsed as HTML" % relative),
                    )))
                except (OSError, ValueError) as exc:
                    message = "%s: %s" % (relative, exc)
                    errors.append(message)
                    structured.append(VerificationCheck(name, CheckStatus.FAIL, (
                        VerificationEvidence("syntax", message),
                    )))
        if tests:
            name = "tests:%s" % ",".join(tests)
            legacy_checks.append(name)
            try:
                result = self.test_runner.run_unittest(tests)
            except (TypeError, ValueError) as exc:
                # Invalid model-supplied validation targets must produce a
                # normal failed check.  They must never escape and convert the
                # complete mission into an opaque runtime block.
                message = "invalid test target: %s" % exc
                errors.append(message)
                structured.append(VerificationCheck(name, CheckStatus.FAIL, (
                    VerificationEvidence("tests", message, {"modules": list(tests)}),
                )))
            else:
                if result.success:
                    structured.append(VerificationCheck(name, CheckStatus.PASS, (
                        VerificationEvidence("tests", "tests passed", {"modules": list(tests)}),
                    )))
                else:
                    message = result.stderr or result.stdout or "tests failed"
                    errors.append(message)
                    structured.append(VerificationCheck(name, CheckStatus.FAIL, (
                        VerificationEvidence("tests", message, {"modules": list(tests)}),
                    )))
        report = self.engine.evaluate(VerificationPlan(tuple(structured)))
        return VerificationResult(report.completed, tuple(legacy_checks), tuple(errors) + report.errors, report)
