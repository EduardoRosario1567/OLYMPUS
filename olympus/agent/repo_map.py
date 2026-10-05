import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class SymbolInfo:
    name: str
    kind: str
    path: str
    lineno: int
    end_lineno: int


@dataclass(frozen=True)
class FileInfo:
    path: str
    module: str
    classes: Tuple[str, ...]
    functions: Tuple[str, ...]
    imports: Tuple[str, ...]
    symbols: Tuple[SymbolInfo, ...]
    is_test: bool


@dataclass(frozen=True)
class RankedFile:
    path: str
    score: float
    reasons: Tuple[str, ...]


class RepoMap:
    def __init__(self, root: str, files: Dict[str, FileInfo]) -> None:
        self.root = str(Path(root).resolve())
        self.files = dict(files)
        self._module_paths = {
            info.module: path for path, info in self.files.items() if info.module
        }
        self._reverse_imports: Dict[str, Set[str]] = {}
        for path, info in self.files.items():
            for imported in info.imports:
                target = self._resolve_import(imported)
                if target:
                    self._reverse_imports.setdefault(target, set()).add(path)

    def _resolve_import(self, imported: str) -> Optional[str]:
        if imported in self._module_paths:
            return self._module_paths[imported]
        candidates = [
            (module, path)
            for module, path in self._module_paths.items()
            if module == imported or module.startswith(imported + ".") or imported.startswith(module + ".")
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (abs(len(item[0]) - len(imported)), item[0]))[0][1]

    def find_symbol(self, name: str) -> List[SymbolInfo]:
        lowered = name.lower()
        exact = [s for info in self.files.values() for s in info.symbols if s.name == name]
        if exact:
            return exact
        return [s for info in self.files.values() for s in info.symbols if s.name.lower() == lowered]

    def find_test_for_file(self, path: str) -> Optional[str]:
        stem = Path(path).stem
        candidate = "tests/test_%s.py" % stem
        if candidate in self.files:
            return candidate
        module_tail = self.files.get(path).module.split(".")[-1] if path in self.files else stem
        for other_path, other in self.files.items():
            if other.is_test and (stem in other_path or module_tail in " ".join(other.imports)):
                return other_path
        return None

    def dependencies(self, path: str) -> List[str]:
        info = self.files.get(path)
        if not info:
            return []
        result = []
        for imported in info.imports:
            target = self._resolve_import(imported)
            if target and target != path and target not in result:
                result.append(target)
        return result

    def dependents(self, path: str) -> List[str]:
        return sorted(self._reverse_imports.get(path, set()))

    def find_related_files(self, path: str) -> List[str]:
        if path not in self.files:
            return []
        related: List[str] = []
        for candidate in [self.find_test_for_file(path)] + self.dependencies(path) + self.dependents(path):
            if candidate and candidate != path and candidate not in related:
                related.append(candidate)
        return related

    @staticmethod
    def _task_terms(task: str) -> Tuple[Set[str], Set[str]]:
        tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9_.-]{2,}", task)
            if token.lower() not in {
                "para", "com", "uma", "que", "the", "and", "this", "that", "from",
                "preserve", "apenas", "somente", "faça", "faca", "atual", "quero",
            }
        }
        symbols = {
            token for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", task)
            if "_" in token or any(ch.isupper() for ch in token[1:])
        }
        return tokens, symbols

    def rank_relevant(self, task: str, limit: int = 8) -> List[RankedFile]:
        terms, symbol_terms = self._task_terms(task)
        task_lower = task.lower()
        explicit_paths = {
            match.rstrip(".,;:)")
            for match in re.findall(r"(?:olympus|tests|scripts|backend|frontend|contexts|attachments|imports)/[A-Za-z0-9_./-]+", task)
        }
        scores: Dict[str, float] = {}
        reasons: Dict[str, List[str]] = {}

        def add(path: str, amount: float, reason: str) -> None:
            if path not in self.files:
                return
            scores[path] = scores.get(path, 0.0) + amount
            if reason not in reasons.setdefault(path, []):
                reasons[path].append(reason)

        # Direct evidence: explicit paths, symbol names, filenames and module names.
        for path, info in self.files.items():
            normalized = " ".join([path, info.module] + list(info.classes) + list(info.functions)).lower().replace("_", " ")
            if path in explicit_paths or path in task:
                add(path, 120.0, "explicit_path")
            path_terms = set(re.findall(r"[a-z0-9]+", normalized))
            overlap = terms.intersection(path_terms)
            if overlap:
                add(path, 7.0 * len(overlap), "name_match")
            for symbol in info.symbols:
                if symbol.name in symbol_terms or symbol.name.lower() in {t.lower() for t in symbol_terms}:
                    add(path, 55.0, "symbol_match:%s" % symbol.name)

        # Content evidence is bounded; it helps discover shell/UI entrypoints and prose-named behavior.
        for path in self.files:
            try:
                content = (Path(self.root) / path).read_text(encoding="utf-8", errors="ignore")[:16000].lower()
            except OSError:
                continue
            hits = [term for term in terms if term in content]
            if hits:
                add(path, min(18.0, 2.0 * len(hits)), "content_match")
            if "dev agent" in task_lower and "dev agent" in content:
                add(path, 45.0, "entrypoint_phrase")
            if "omniroute" in task_lower and "omniroute" in content:
                add(path, 20.0, "provider_phrase")

        # Graph expansion: direct matches pull in tests, dependencies and dependents.
        seeds = sorted(scores, key=lambda p: (-scores[p], p))[: max(limit, 6)]
        for seed in seeds:
            base = scores.get(seed, 0.0)
            test = self.find_test_for_file(seed)
            if test:
                add(test, max(10.0, base * 0.28), "test_of:%s" % seed)
            for dep in self.dependencies(seed):
                add(dep, max(6.0, base * 0.16), "dependency_of:%s" % seed)
            for dependent in self.dependents(seed):
                add(dependent, max(5.0, base * 0.12), "dependent_of:%s" % seed)

        ranked = [RankedFile(path, scores[path], tuple(reasons.get(path, ()))) for path in scores]
        ranked.sort(key=lambda item: (-item.score, item.path))
        return ranked[:limit]

    def rank_relevant_files(self, task: str, limit: int = 8) -> List[str]:
        return [item.path for item in self.rank_relevant(task, limit=limit)]


def _module_name(relative: Path) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def build_repo_map(root: str, exclude_dirs: Iterable[str] = (".git", ".olympus", ".venv", "venv", "node_modules", "__pycache__"), max_files: int = 5000) -> RepoMap:
    root_path = Path(root).resolve()
    files: Dict[str, FileInfo] = {}
    excluded = set(exclude_dirs)
    source_suffixes = {".py", ".sh", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".json", ".md", ".txt", ".csv", ".xml", ".yaml", ".yml", ".sql"}
    paths = sorted(path for path in root_path.rglob("*") if path.is_file() and path.suffix.lower() in source_suffixes)
    for path in paths:
        rel = path.relative_to(root_path)
        if any(part in excluded for part in rel.parts):
            continue
        if len(files) >= max_files:
            break
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        classes, functions, imports, symbols = [], [], [], []
        if path.suffix == ".py":
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                    symbols.append(SymbolInfo(node.name, "function", rel.as_posix(), node.lineno, getattr(node, "end_lineno", node.lineno)))
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                    symbols.append(SymbolInfo(node.name, "class", rel.as_posix(), node.lineno, getattr(node, "end_lineno", node.lineno)))
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
        elif path.suffix == ".sh":
            for number, line in enumerate(source.splitlines(), 1):
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", line.strip())
                if match:
                    name = match.group(1)
                    functions.append(name)
                    symbols.append(SymbolInfo(name, "shell_function", rel.as_posix(), number, number))
        rel_s = rel.as_posix()
        is_test = rel_s.startswith("tests/test_") or ".test." in rel_s or ".spec." in rel_s
        files[rel_s] = FileInfo(rel_s, _module_name(rel), tuple(sorted(set(classes))), tuple(sorted(set(functions))), tuple(sorted(set(imports))), tuple(symbols), is_test)
    return RepoMap(str(root_path), files)
