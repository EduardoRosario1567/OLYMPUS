import json
from typing import Any, Dict, Iterable, Optional, Tuple

from olympus.agent.actions import ActionType, AgentAction


_ACTION_KEYS = ("type", "action", "tool", "operation", "name")
_TARGET_KEYS = (
    "target", "path", "file", "filename", "file_path", "filepath",
    "target_path", "destination", "module",
)
_PAYLOAD_KEYS = (
    "payload", "arguments", "args", "params", "parameters", "content", "input",
)

_PATCH_OPERATIONS = {
    "replace_lines",
    "insert_after_symbol",
    "insert_before_symbol",
    "replace_function",
    "append_block",
    "replace_text",
}

_PATCH_PAYLOAD_KEYS = {
    "operation",
    "new_content",
    "symbol",
    "start_line",
    "end_line",
    "old_text",
}

_ALIASES = {
    "research_sources": ActionType.RESEARCH_SOURCES,
    "read": ActionType.READ_FILE,
    "open_file": ActionType.READ_FILE,
    "open": ActionType.READ_FILE,
    "read_file": ActionType.READ_FILE,
    "readfile": ActionType.READ_FILE,
    "search": ActionType.SEARCH_CODE,
    "search_code": ActionType.SEARCH_CODE,
    "grep": ActionType.SEARCH_CODE,
    "create": ActionType.CREATE_FILE,
    "create_file": ActionType.CREATE_FILE,
    "write": ActionType.CREATE_FILE,
    "write_file": ActionType.CREATE_FILE,
    "patch": ActionType.PATCH_FILE,
    "patch_file": ActionType.PATCH_FILE,
    "edit": ActionType.PATCH_FILE,
    "edit_file": ActionType.PATCH_FILE,
    "update": ActionType.PATCH_FILE,
    "run_test": ActionType.RUN_TEST,
    "run_tests": ActionType.RUN_TEST,
    "test": ActionType.RUN_TEST,
    "execute_test": ActionType.RUN_TEST,
    "inspect": ActionType.INSPECT_RESULT,
    "inspect_result": ActionType.INSPECT_RESULT,
    "finish": ActionType.FINISH,
    "done": ActionType.FINISH,
    "complete": ActionType.FINISH,
}


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def _unwrap(data: Any) -> Dict[str, Any]:
    if isinstance(data, list):
        # Free models occasionally return a whole action plan even though the
        # protocol asks for one action. Execute only the first object; the next
        # planning cycle will receive the updated state before doing more work.
        data = next((item for item in data if isinstance(item, dict)), data)
    if not isinstance(data, dict):
        raise ValueError("action payload must be an object")

    tool_calls = data.get("tool_calls")
    if isinstance(tool_calls, list) and len(tool_calls) == 1 and isinstance(tool_calls[0], dict):
        merged = dict(data)
        merged.update(_unwrap(tool_calls[0]))
        return merged

    for key in ("action", "tool_call", "tool_request", "command", "function"):
        nested = data.get(key)
        if isinstance(nested, dict):
            merged = dict(data)
            merged.update(_unwrap(nested))
            if key in _ACTION_KEYS:
                merged.pop(key, None)
            return merged
    return dict(data)


def _normalize_type(value: Any) -> ActionType:
    if isinstance(value, ActionType):
        return value
    text = str(value or "").strip().lower()
    for separator in (".", "/"):
        if separator in text:
            candidate = text.rsplit(separator, 1)[-1]
            if candidate in _ALIASES:
                text = candidate
    if text in _ALIASES:
        return _ALIASES[text]
    try:
        return ActionType(text)
    except ValueError:
        raise ValueError("unknown action type: %s" % value)


def _pick(data: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def normalize_patch_payload(payload: Any) -> Dict[str, Any]:
    """Canonicalize and validate model-supplied patch_file arguments.

    Invalid model output must be rejected while still inside the planner
    contract so the normal repair pass can ask the same model for a corrected
    action. The executor calls this function again as defense in depth.
    """
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, dict):
            payload = decoded

    if not isinstance(payload, dict):
        raise ValueError("patch_file payload must be an object")

    data = dict(payload)

    if "new_content" not in data and "content" in data:
        data["new_content"] = data["content"]

    if "new_content" not in data and "new_text" in data:
        data["new_content"] = data["new_text"]

    if (
        "operation" not in data
        and "old_text" in data
        and "new_content" in data
    ):
        data["operation"] = "replace_text"

    if "operation" not in data and "edit" in data:
        data["operation"] = data["edit"]
    if "symbol" not in data and "function" in data:
        data["symbol"] = data["function"]

    # A model may repeat the file destination inside its argument object.
    # target is already canonicalized separately and must never leak into
    # PatchRequest as an unexpected keyword.
    for key in _TARGET_KEYS:
        data.pop(key, None)

    for alias in ("content", "new_text", "edit", "function"):
        data.pop(alias, None)

    unknown = sorted(set(data) - _PATCH_PAYLOAD_KEYS)
    if unknown:
        raise ValueError(
            "patch_file payload has unsupported fields: %s"
            % ", ".join(unknown)
        )

    operation = str(data.get("operation") or "").strip()
    if operation not in _PATCH_OPERATIONS:
        raise ValueError("patch_file requires a supported operation")
    data["operation"] = operation

    if (
        "new_content" not in data
        or not isinstance(data["new_content"], str)
    ):
        raise ValueError("patch_file requires string new_content")

    if operation == "replace_text":
        old_text = data.get("old_text")
        if not isinstance(old_text, str) or not old_text:
            raise ValueError(
                "patch_file replace_text requires non-empty old_text"
            )

    if operation == "replace_lines":
        start = data.get("start_line")
        end = data.get("end_line")
        if (
            type(start) is not int
            or type(end) is not int
            or start < 1
            or end < start
        ):
            raise ValueError(
                "patch_file replace_lines requires valid start_line/end_line"
            )

    if operation in {
        "insert_after_symbol",
        "insert_before_symbol",
        "replace_function",
    }:
        symbol = data.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(
                "patch_file symbol operation requires symbol"
            )

    return data


def normalize_action_data(data: Any) -> AgentAction:
    obj = _unwrap(_compact(data))
    arguments = obj.get("arguments")
    if isinstance(arguments, str):
        try:
            decoded_arguments = json.loads(arguments)
            if isinstance(decoded_arguments, dict):
                obj["arguments"] = decoded_arguments
        except (TypeError, ValueError):
            pass
    raw_types = [obj[key] for key in _ACTION_KEYS if key in obj and obj[key] is not None]
    if not raw_types:
        raise ValueError("missing action type")

    normalized = [_normalize_type(value) for value in raw_types]
    action_type = normalized[0]
    if any(item != action_type for item in normalized[1:]):
        raise ValueError("conflicting action types")

    target = _pick(obj, _TARGET_KEYS)
    payload = _pick(obj, _PAYLOAD_KEYS)
    reason = obj.get("reason") or obj.get("why") or obj.get("description") or ""
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {"raw_metadata": metadata}

    # Models commonly place the file path beside the content inside payload.
    # Promote that path to the canonical target instead of rejecting an
    # otherwise safe and unambiguous action.
    if target is None and isinstance(payload, dict):
        target = _pick(payload, _TARGET_KEYS)
    if isinstance(target, dict):
        target = _pick(target, _TARGET_KEYS)

    if action_type == ActionType.CREATE_FILE:
        if payload is None and "body" in obj:
            payload = obj["body"]
        elif isinstance(payload, dict):
            content = _pick(
                payload,
                ("content", "body", "text", "code", "new_content"),
            )
            if content is not None:
                payload = content
    if action_type == ActionType.PATCH_FILE:
        payload = normalize_patch_payload(payload)

    return AgentAction(
        action_type,
        str(target) if target is not None else None,
        payload,
        str(reason),
        metadata,
    )


def extract_json_candidates(text: str) -> Tuple[str, ...]:
    raw = str(text or "").strip()
    if not raw:
        return ()

    candidates = []
    candidates.append(raw)

    lines = raw.splitlines()
    if lines and lines[0].strip().startswith("```"):
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        candidates.append("\n".join(inner).strip())

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])

    seen = set()
    unique = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return tuple(unique)


def normalize_action_text(text: str) -> AgentAction:
    last_error: Optional[Exception] = None
    for candidate in extract_json_candidates(text):
        try:
            return normalize_action_data(json.loads(candidate))
        except Exception as exc:
            last_error = exc
    raise ValueError("malformed action: %s" % last_error)
