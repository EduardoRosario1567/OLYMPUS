"""Official Higgsfield media API adapter.

Higgsfield is intentionally kept outside the text provider fabric. Its API
creates asynchronous image/video jobs and therefore cannot safely participate
in the OpenAI-compatible chat fallback chain.
"""
import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class HiggsfieldError(RuntimeError):
    """A safe, provider-neutral error from the Higgsfield boundary."""


_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


@dataclass(frozen=True)
class HiggsfieldConfig:
    base_url: str = "https://api.higgsfield.ai"
    key_id: str = ""
    key_secret: str = ""
    timeout_seconds: int = 60

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)


class HiggsfieldClient:
    """Small server-side client for submit/status/cancel operations."""

    def __init__(self, config=None):
        self.config = config or HiggsfieldConfig(
            base_url=os.environ.get("OLYMPUS_HIGGSFIELD_URL", "https://api.higgsfield.ai").strip().rstrip("/"),
            key_id=os.environ.get("HIGGSFIELD_API_KEY_ID", "").strip(),
            key_secret=os.environ.get("HIGGSFIELD_API_KEY_SECRET", "").strip(),
            timeout_seconds=max(10, min(300, int(os.environ.get("OLYMPUS_HIGGSFIELD_TIMEOUT", "60")))),
        )

    def _headers(self):
        if not self.config.configured:
            raise HiggsfieldError("Higgsfield não está configurada: informe o ID e o segredo da API.")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "OLYMPUS/2.6.2",
            "Authorization": "Key %s:%s" % (self.config.key_id, self.config.key_secret),
        }

    def _request(self, method, path, payload=None):
        if not path.startswith("/") or ".." in path or path.startswith("//"):
            raise HiggsfieldError("Caminho de API Higgsfield inválido.")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.config.base_url + path,
            data=body,
            headers=self._headers(),
            method=method,
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return response.status, json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise HiggsfieldError("Higgsfield HTTP %s: %s" % (exc.code, raw[:500]))
        except (URLError, TimeoutError, OSError) as exc:
            raise HiggsfieldError("Higgsfield indisponível: %s" % exc)
        except ValueError as exc:
            raise HiggsfieldError("Higgsfield devolveu JSON inválido: %s" % exc)

    @staticmethod
    def _validate_request_id(request_id):
        value = str(request_id or "").strip()
        if not _REQUEST_ID.fullmatch(value):
            raise HiggsfieldError("request_id Higgsfield inválido.")
        return value

    def submit(self, model_path, payload):
        """Submit one generation job and return the provider response."""
        path = str(model_path or "").strip()
        if not path.startswith("/") or ".." in path or len(path) > 300:
            raise HiggsfieldError("model_path Higgsfield inválido.")
        if not isinstance(payload, dict) or not payload:
            raise HiggsfieldError("A solicitação Higgsfield precisa de parâmetros JSON.")
        status, data = self._request("POST", path, payload)
        if status < 200 or status >= 300 or not isinstance(data, dict):
            raise HiggsfieldError("Higgsfield rejeitou a solicitação.")
        request_id = data.get("request_id")
        if request_id:
            self._validate_request_id(request_id)
        return data

    def status(self, request_id):
        value = self._validate_request_id(request_id)
        _status, data = self._request("GET", "/requests/%s/status" % value)
        return data

    def cancel(self, request_id):
        value = self._validate_request_id(request_id)
        _status, data = self._request("POST", "/requests/%s/cancel" % value)
        return data
