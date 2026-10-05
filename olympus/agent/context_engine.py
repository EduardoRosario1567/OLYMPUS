import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from olympus.agent.repo_map import RepoMap


@dataclass(frozen=True)
class AgentContext:
    selected_files: Tuple[str, ...]
    snippets: Dict[str, str]
    symbols: Tuple[str, ...]
    tests: Tuple[str, ...]
    selection_reasons: Dict[str, str]
    budget_usage: dict


class ContextEngine:
    def __init__(self, root: str, max_files: int = 6, max_chars: int = 12000, max_lines: int = 240) -> None:
        self.root = str(Path(root).resolve())
        self.max_files = max_files
        self.max_chars = max_chars
        self.max_lines = max_lines

    @staticmethod
    def _terms(task: str) -> List[str]:
        return [
            token.lower()
            for token in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9_]{2,}", task)
            if token.lower() not in {"para", "uma", "com", "que", "the", "and", "this", "atual", "quero"}
        ]

    def _focused_snippet(self, path: str, task: str, repo_map: RepoMap, line_budget: int, char_budget: int) -> str:
        full = Path(self.root) / path
        try:
            lines = full.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return ""
        if not lines or line_budget <= 0 or char_budget <= 0:
            return ""

        anchors = set()
        terms = self._terms(task)
        info = repo_map.files.get(path)
        if info:
            for symbol in info.symbols:
                if symbol.name.lower() in task.lower() or any(term in symbol.name.lower() for term in terms):
                    anchors.add(max(0, symbol.lineno - 1))
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if any(term in lowered for term in terms):
                anchors.add(idx)
                if len(anchors) >= 8:
                    break

        # No semantic anchor: keep file header for imports/contracts.
        if not anchors:
            chosen = list(range(min(len(lines), line_budget)))
        else:
            chosen_set = set()
            radius = 3
            for anchor in sorted(anchors):
                for idx in range(max(0, anchor - radius), min(len(lines), anchor + radius + 1)):
                    chosen_set.add(idx)
                    if len(chosen_set) >= line_budget:
                        break
                if len(chosen_set) >= line_budget:
                    break
            # Preserve a small header for imports/shebang/context.
            chosen_set.update(range(min(5, len(lines))))
            chosen = sorted(chosen_set)[:line_budget]

        parts = []
        last = None
        for idx in chosen:
            if last is not None and idx > last + 1:
                parts.append("... [lines omitted] ...")
            parts.append("%d: %s" % (idx + 1, lines[idx]))
            last = idx
        snippet = "\n".join(parts)
        return snippet[:char_budget]

    def resolve(self, task: str, repo_map: RepoMap) -> AgentContext:
        explicit = re.findall(r"(?<![\w])((?:olympus|tests|scripts|backend|frontend|contexts|app|src|public|docs|assets|styles|attachments|imports)/[A-Za-z0-9_./-]+)", task)
        candidates: List[Tuple[str, str]] = []
        seen = set()

        def add(path: str, reason: str) -> None:
            path = path.rstrip(".,;:)")
            if path in repo_map.files and path not in seen:
                seen.add(path)
                candidates.append((path, reason))

        for path in explicit:
            add(path, "explicit_path")

        for ranked in repo_map.rank_relevant(task, limit=self.max_files * 3):
            reason = "ranked:%.1f:%s" % (ranked.score, ",".join(ranked.reasons[:3]))
            add(ranked.path, reason)

        # Opaque update requests still need an initial view of actual source
        # files. An empty relevance score must not make a nonempty project look
        # empty to the planner. The usual file/line/character budgets apply.
        if not candidates:
            for path in sorted(repo_map.files)[:self.max_files]:
                add(path, "workspace_inventory")

        # Expand graph-neighbor context without flooding the budget.
        for path, _ in list(candidates[:3]):
            test = repo_map.find_test_for_file(path)
            if test:
                add(test, "related_test:%s" % path)
            for related in repo_map.find_related_files(path)[:2]:
                add(related, "graph_related:%s" % path)

        snippets: Dict[str, str] = {}
        reasons: Dict[str, str] = {}
        selected, used_chars, used_lines = [], 0, 0
        for path, reason in candidates:
            if len(selected) >= self.max_files:
                break
            remaining_lines = max(0, self.max_lines - used_lines)
            remaining_chars = max(0, self.max_chars - used_chars)
            if remaining_lines == 0 or remaining_chars == 0:
                break
            slots = max(1, self.max_files - len(selected))
            per_file_chars = min(remaining_chars, max(1, self.max_chars // max(1, self.max_files)), max(1, remaining_chars // slots if slots else remaining_chars))
            per_file_lines = min(remaining_lines, max(1, self.max_lines // max(1, self.max_files)), max(1, remaining_lines // slots if slots else remaining_lines))
            chunk = self._focused_snippet(path, task, repo_map, per_file_lines, per_file_chars)
            if not chunk:
                continue
            selected.append(path)
            snippets[path] = chunk
            reasons[path] = reason
            used_chars += len(chunk)
            used_lines += chunk.count("\n") + 1

        symbols = []
        tests = []
        for path in selected:
            info = repo_map.files.get(path)
            if info:
                symbols.extend(info.classes)
                symbols.extend(info.functions)
                if info.is_test:
                    tests.append(path)
        return AgentContext(
            tuple(selected), snippets, tuple(dict.fromkeys(symbols)), tuple(tests), reasons,
            {"files": len(selected), "chars": used_chars, "lines": used_lines,
             "max_files": self.max_files, "max_chars": self.max_chars, "max_lines": self.max_lines},
        )
