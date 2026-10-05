from __future__ import annotations

from typing import Mapping, Protocol

from .platform import BillingEvent, SaaSPlatform


class BillingVerificationError(PermissionError):
    pass


class BillingProvider(Protocol):
    """Provider boundary: implementations must authenticate before parsing."""

    name: str

    def verify_and_parse(self, body: bytes, headers: Mapping[str, str]) -> BillingEvent:
        ...


class BillingEventReceiver:
    def __init__(self, platform: SaaSPlatform, providers: tuple[BillingProvider, ...]):
        self.platform = platform
        self.providers = {provider.name: provider for provider in providers}

    def receive(self, provider_name: str, body: bytes, headers: Mapping[str, str]) -> bool:
        provider = self.providers.get(str(provider_name).strip().lower())
        if provider is None:
            raise BillingVerificationError("billing provider is not configured")
        if len(body) > 1024 * 1024:
            raise BillingVerificationError("billing event exceeds size limit")
        event = provider.verify_and_parse(body, headers)
        if event.provider != provider.name:
            raise BillingVerificationError("billing provider identity mismatch")
        return self.platform.apply_verified_billing_event(event)
