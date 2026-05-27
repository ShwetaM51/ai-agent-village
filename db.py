"""All Supabase access. Every other module talks to the DB through here.

Why a single module:
- One place to swap providers (Postgres directly, SQLite, etc.)
- One place to apply query limits, ordering, filtering
- The trust boundary is enforced higher up (in prompts.py and tools.py);
  this module is a dumb data access layer.
"""
from typing import Optional
from supabase import create_client, Client

import config

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    return _client


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def fetch_agent(agent_id: str) -> Optional[dict]:
    res = get_client().table("living_agents").select("*").eq("id", agent_id).execute()
    return res.data[0] if res.data else None


def fetch_agent_by_api_key(api_key: str) -> Optional[dict]:
    """Used by identity resolution to verify owner."""
    res = (
        get_client()
        .table("living_agents")
        .select("*")
        .eq("api_key", api_key)
        .execute()
    )
    return res.data[0] if res.data else None


def list_agents() -> list[dict]:
    res = get_client().table("living_agents").select("*").execute()
    return res.data or []


def update_agent_status(agent_id: str, status: str) -> None:
    get_client().table("living_agents").update({"status": status}).eq("id", agent_id).execute()


# ---------------------------------------------------------------------------
# Memory (split by `kind` — see schema_addition.sql)
# ---------------------------------------------------------------------------

def fetch_private_facts(agent_id: str, limit: int) -> list[dict]:
    res = (
        get_client()
        .table("living_memory")
        .select("text, created_at")
        .eq("agent_id", agent_id)
        .eq("kind", "private_fact")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def fetch_personality_notes(agent_id: str, limit: int) -> list[dict]:
    res = (
        get_client()
        .table("living_memory")
        .select("text, created_at")
        .eq("agent_id", agent_id)
        .eq("kind", "personality_note")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def insert_private_fact(agent_id: str, text: str) -> None:
    get_client().table("living_memory").insert({
        "agent_id": agent_id,
        "text": text,
        "kind": "private_fact",
    }).execute()


def insert_personality_note(agent_id: str, text: str) -> None:
    get_client().table("living_memory").insert({
        "agent_id": agent_id,
        "text": text,
        "kind": "personality_note",
    }).execute()


# ---------------------------------------------------------------------------
# Diary
# ---------------------------------------------------------------------------

def fetch_recent_diary(agent_id: str, limit: int) -> list[dict]:
    res = (
        get_client()
        .table("living_diary")
        .select("text, entry_date, created_at")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def insert_diary(agent_id: str, text: str) -> None:
    get_client().table("living_diary").insert({
        "agent_id": agent_id,
        "text": text,
    }).execute()


def last_diary_timestamp(agent_id: str) -> Optional[str]:
    res = (
        get_client()
        .table("living_diary")
        .select("created_at")
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["created_at"] if res.data else None


# ---------------------------------------------------------------------------
# Owner chat history
#
# We reuse living_log to store conversation history (one row per message)
# tagged with emoji '💬' so it's distinguishable. In a fuller build this
# would be its own table with role/speaker columns; the brief told us not
# to over-design the schema, so we piggy-back.
#
# NB: only owner-side history is stored. Stranger conversations are stateless
# by design (see ARCHITECTURE.md §4).
# ---------------------------------------------------------------------------

_OWNER_CHAT_EMOJI = "💬"


def fetch_owner_chat_history(agent_id: str, limit: int) -> list[dict]:
    res = (
        get_client()
        .table("living_log")
        .select("text, created_at")
        .eq("agent_id", agent_id)
        .eq("emoji", _OWNER_CHAT_EMOJI)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    # Return in chronological order (oldest first) so prompts read naturally.
    return list(reversed(res.data or []))


def insert_owner_chat_turn(agent_id: str, role: str, content: str) -> None:
    """role is 'owner' or 'agent'. Stored as a prefix in text for simplicity."""
    get_client().table("living_log").insert({
        "agent_id": agent_id,
        "text": f"{role}: {content}",
        "emoji": _OWNER_CHAT_EMOJI,
    }).execute()


# ---------------------------------------------------------------------------
# Activity events (stranger visits etc.)
# ---------------------------------------------------------------------------

def insert_visit_event(agent_id: str, content: str) -> None:
    get_client().table("living_activity_events").insert({
        "agent_id": str(agent_id),
        "event_type": "visit",
        "content": content,
    }).execute()
