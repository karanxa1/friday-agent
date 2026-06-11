"""Auth toolset: the agent requests credentials from the user via the UI.

Flow:
  1. ``request_credential(service, key_name, instructions)`` stages a pending
     credential request (an approval-queue item of type ``credential``) and
     tells the human what to provide.
  2. The human supplies the value (UI / CLI) which calls ``vault.set_credential``.
  3. Tools later read it through ``auth.vault.get_credential`` only at the call
     site -- the value never enters the model's context.

This keeps secrets human-in-the-loop and out of the LLM, matching the reference
secret-handling posture.
"""

from __future__ import annotations

from core import audit
from core.registry import tool
from control_plane import approvals
from auth import vault


@tool("auth", description="Request a credential/API key from the user for a service.")
def request_credential(service: str, key_name: str, instructions: str = "") -> str:
    """Ask the human to provide a secret for an external service.

    Args:
        service: human-readable service name (e.g. 'X / Twitter').
        key_name: the vault key under which it will be stored (e.g. 'X_API_KEY').
        instructions: where/how the user can obtain the credential.

    Returns:
        An approval id; once the user supplies the value it is stored encrypted.
    """
    if vault.has_credential(key_name):
        return f"credential {key_name!r} already present in the vault (no action needed)."
    entry = approvals.submit(
        "credential",
        summary=f"provide {key_name} for {service}",
        payload={"service": service, "key_name": key_name, "instructions": instructions},
    )
    audit.log("auth.request", service=service, key_name=key_name, id=entry["id"])
    return (
        f"requested credential {key_name!r} for {service} (request {entry['id']}). "
        f"Ask the user to supply it; it will be stored encrypted. {instructions}"
    )


@tool("auth", description="Check whether a named credential exists in the vault (never reveals value).")
def credential_status(key_name: str) -> str:
    """Report whether a credential is available.

    Args:
        key_name: the vault key to check.
    """
    return f"{key_name}: {'present' if vault.has_credential(key_name) else 'missing'}"


@tool("auth", description="List the names of credentials stored in the vault (names only).")
def list_credentials() -> str:
    """List stored credential names (values are never returned)."""
    names = vault.list_credentials()
    return ", ".join(names) if names else "(vault empty)"
