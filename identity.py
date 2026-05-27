"""Identity resolution.

Every HTTP request hits resolve_identity() exactly once. It returns the
caller's identity for this agent. Downstream code derives a Scope from
this and never re-checks identity itself.

Identities are mutually exclusive:
  - OWNER:    api_key header present AND matches THIS agent's api_key
  - STRANGER: anything else (missing key, wrong key, key for another agent)
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import db


class Identity(str, Enum):
    OWNER = "OWNER"
    STRANGER = "STRANGER"


@dataclass
class Caller:
    identity: Identity
    agent_id: str


def resolve_identity(agent_id: str, api_key: Optional[str]) -> Caller:
    """Determine whether the caller is the owner of `agent_id`.

    Note: a valid api_key for *another* agent does NOT make the caller
    the owner here. The key must match the api_key column of THIS agent.
    """
    if not api_key:
        return Caller(identity=Identity.STRANGER, agent_id=agent_id)

    agent = db.fetch_agent(agent_id)
    if agent is None:
        # Agent doesn't exist — treat as stranger; the endpoint will 404.
        return Caller(identity=Identity.STRANGER, agent_id=agent_id)

    # Plain string compare is fine for a prototype. Production: hash + constant-time.
    if api_key == agent.get("api_key"):
        return Caller(identity=Identity.OWNER, agent_id=agent_id)

    return Caller(identity=Identity.STRANGER, agent_id=agent_id)
