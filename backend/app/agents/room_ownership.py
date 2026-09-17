"""In-process ownership so one LiveKit room has one active interview agent.

LiveKit Agents in `dev` / Windows uses a THREAD job executor: each job gets its
own thread and asyncio event loop inside the same worker process. After a room
is deleted, LiveKit may still dispatch another job for the same room name
(reconnect auto-create, agent crash retry, or a second job id). This registry
rejects that second job in the worker's request handler before a second
InterviewAgent can connect and speak.

Claim happens in the AgentServer request handler (main process). Release
happens on genuine job shutdown. Stale claims from a dead job id can be
replaced so a later genuine interview for a new room lifetime is not blocked.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional

_lock = threading.Lock()
_owners: Dict[str, str] = {}


def reset_room_ownership_for_tests() -> None:
    with _lock:
        _owners.clear()


def owner_job_id(room_name: str) -> Optional[str]:
    with _lock:
        return _owners.get(room_name)


def try_claim_room(room_name: str, job_id: str) -> bool:
    """Return True if this job now owns the room, False if another job already does."""
    name = (room_name or "").strip()
    owner = (job_id or "").strip()
    if not name or not owner:
        return False
    with _lock:
        existing = _owners.get(name)
        if existing is not None and existing != owner:
            return False
        _owners[name] = owner
        return True


def release_room(room_name: str, job_id: str) -> None:
    name = (room_name or "").strip()
    owner = (job_id or "").strip()
    if not name or not owner:
        return
    with _lock:
        if _owners.get(name) == owner:
            del _owners[name]


def room_already_has_interview_agent(room, local_identity: str) -> bool:
    """True when another agent participant is already connected to this room."""
    local = (local_identity or "").strip()
    remote = getattr(room, "remote_participants", None) or {}
    participants = remote.values() if hasattr(remote, "values") else remote
    for participant in participants:
        identity = (getattr(participant, "identity", None) or "").strip()
        if not identity or identity == local:
            continue
        if identity.startswith("agent-") or identity.startswith("interview-agent"):
            return True
    return False
