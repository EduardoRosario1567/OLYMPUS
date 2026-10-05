import os
from pathlib import Path
from typing import Any, Dict

def _validate_context_name(name: str) -> None:
    """Validate the context name to prevent path traversal attacks."""
    if not name:
        raise ValueError("Context name must not be empty")
    # Disallow directory traversal sequences
    if ".." in name or name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"Invalid context name: {name}. Path traversal not allowed.")
    # Allow only alphanumeric characters, underscores, and hyphens
    if not all(c.isalnum() or c in "_-" for c in name):
        raise ValueError(f"Context name contains invalid characters: {name}")

def load_context(context_name: str) -> Dict[str, Any]:
    """
    Load a YAML context manifest from the `contexts` directory.

    Args:
        context_name: The name of the context (without the .yaml extension).

    Returns:
        A dictionary containing the keys:
            - required
            - tests
            - dependencies
            - optional
            - forbidden

        Each key maps to a list (empty list if the key is missing or null in the YAML).

    Raises:
        ValueError: If the context name fails validation.
        FileNotFoundError: If the corresponding YAML file does not exist.
    """
    _validate_context_name(context_name)

    # Determine the directory where this module resides
    base_dir = Path(__file__).parent
    contexts_dir = base_dir / "contexts"
    yaml_path = contexts_dir / f"{context_name}.yaml"

    if not yaml_path.is_file():
        raise FileNotFoundError(f"Context manifest not found: {yaml_path}")

    # Use the standard library's yaml module (PyYAML) to parse the manifest.
    # The module is assumed to be installed as part of the project dependencies.
    import yaml

    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Extract the desired keys, defaulting to empty lists if missing
    result: Dict[str, Any] = {
        "required": data.get("required", []),
        "tests": data.get("tests", []),
        "dependencies": data.get("dependencies", []),
        "optional": data.get("optional", []),
        "forbidden": data.get("forbidden", []),
    }

    return result
