import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from olympus.agent.safe_apply import _is_allowed


class PatchEngineError(ValueError):
    pass


@dataclass(frozen=True)
class PatchRequest:
    file: str
    operation: str
    new_content: str
    symbol: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None


@dataclass(frozen=True)
class PatchResult:
    file: str
    operation: str
    changed_lines: int


class PatchEngine:
    OPERATIONS = {"replace_lines", "insert_after_symbol", "insert_before_symbol", "replace_function", "append_block"}

    def __init__(self, root: str, allowed_paths=(), max_changed_lines: int = 200) -> None:
        self.root = Path(root).resolve()
        self.allowed_paths = tuple(allowed_paths)
        self.max_changed_lines = max_changed_lines

    def _path(self, relative: str) -> Path:
        if self.allowed_paths and not _is_allowed(relative, self.allowed_paths):
            raise PatchEngineError("path not allowed")
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            raise PatchEngineError("path escapes workspace")
        if not path.is_file():
            raise PatchEngineError("target file not found")
        return path

    @staticmethod
    def _symbol_range(source: str, symbol: str):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                return node.lineno, getattr(node, "end_lineno", node.lineno)
        raise PatchEngineError("symbol not found: %s" % symbol)

    def apply(self, request: PatchRequest) -> PatchResult:
        if request.operation not in self.OPERATIONS:
            raise PatchEngineError("unsupported operation")
        path = self._path(request.file)
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        new_lines = request.new_content.splitlines()
        if len(new_lines) > self.max_changed_lines:
            raise PatchEngineError("patch exceeds changed-line limit")

        if request.operation == "append_block":
            updated = lines + ([""] if lines and lines[-1] else []) + new_lines
        elif request.operation == "replace_lines":
            if not request.start_line or not request.end_line or request.start_line > request.end_line:
                raise PatchEngineError("invalid line range")
            updated = lines[:request.start_line - 1] + new_lines + lines[request.end_line:]
        else:
            if not request.symbol:
                raise PatchEngineError("symbol is required")
            start, end = self._symbol_range(source, request.symbol)
            if request.operation == "replace_function":
                updated = lines[:start - 1] + new_lines + lines[end:]
            elif request.operation == "insert_before_symbol":
                updated = lines[:start - 1] + new_lines + lines[start - 1:]
            else:
                updated = lines[:end] + new_lines + lines[end:]

        text = "\n".join(updated).rstrip() + "\n"
        if path.suffix == ".py":
            try:
                ast.parse(text)
            except SyntaxError as exc:
                raise PatchEngineError("patched Python is invalid: %s" % exc)
        path.write_text(text, encoding="utf-8")
        return PatchResult(request.file, request.operation, max(len(new_lines), 1))
