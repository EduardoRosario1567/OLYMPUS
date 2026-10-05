"""Deterministic command-output compaction for bounded agent context.

No model call is used.  Diagnostic lines and the beginning/end of an output
are preserved so the next model can repair work without receiving thousands
of repetitive progress lines.
"""
from dataclasses import dataclass
import re


_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_DIAGNOSTIC = re.compile(
    r"(error|failed|failure|traceback|exception|warning|assert|expected|actual|"
    r"not found|timeout|summary|exit code|npm err|syntax)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompactedOutput:
    text: str
    original_chars: int
    compacted_chars: int
    omitted_lines: int


def compact_output(value: object, max_chars: int = 6000, max_lines: int = 120) -> CompactedOutput:
    original = _ANSI.sub("", str(value or "")).replace("\r\n", "\n")
    lines = original.splitlines()
    deduped = []
    for line in lines:
        if deduped and line == deduped[-1]:
            continue
        deduped.append(line)
    if len(original) <= max_chars and len(deduped) <= max_lines:
        return CompactedOutput(original, len(original), len(original), len(lines) - len(deduped))

    head = set(range(min(20, len(deduped))))
    tail = set(range(max(0, len(deduped) - 35), len(deduped)))
    reserved = head | tail
    diagnostic_slots = max(0, max_lines - len(reserved))
    diagnostics = [
        index for index, line in enumerate(deduped)
        if index not in reserved and _DIAGNOSTIC.search(line)
    ][:diagnostic_slots]
    indexes = reserved | set(diagnostics)
    selected = []
    last = -2
    for index in sorted(indexes):
        if index > last + 1:
            selected.append("… [saída repetitiva omitida pelo Olympus] …")
        selected.append(deduped[index])
        last = index
    text = "\n".join(selected)
    if len(text) > max_chars:
        half = max(200, (max_chars - 80) // 2)
        text = text[:half] + "\n… [saída compactada] …\n" + text[-half:]
    omitted = max(0, len(lines) - len(selected))
    return CompactedOutput(text, len(original), len(text), omitted)
