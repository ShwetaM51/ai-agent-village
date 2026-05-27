"""Prompt assembly. The spine of the system.

For each Scope, we build a system prompt that contains EXACTLY the data
that scope is permitted to see. We never load private data and then "decide
not to use it" — if the scope can't see it, we never fetch it. This makes
leaks structurally impossible rather than instruction-dependent.

Every read decision is governed by scopes.py.
"""
import config, db
from scopes import (
    Scope,
    PROMPT_INCLUDES_FULL_BIO,
    PROMPT_INCLUDES_VISITOR_BIO_ONLY,
    PROMPT_INCLUDES_PRIVATE_FACTS,
    PROMPT_INCLUDES_PERSONALITY_NOTES,
    PROMPT_INCLUDES_OWNER_CHAT_HISTORY,
    PROMPT_INCLUDES_RECENT_DIARY,
)


def build_system_prompt(agent: dict, scope: Scope) -> str:
    """Assemble the system prompt for a given agent in a given scope.

    Returns the full prompt string. The caller is responsible for passing
    it to the LLM along with the user message.
    """
    parts: list[str] = []

    # --- 1. Identity ---------------------------------------------------
    if scope in PROMPT_INCLUDES_FULL_BIO:
        parts.append(_identity_full(agent))
    elif scope in PROMPT_INCLUDES_VISITOR_BIO_ONLY:
        parts.append(_identity_visitor(agent))
    else:  # pragma: no cover — every scope should be in one of the two sets
        raise ValueError(f"No identity rule for scope {scope}")

    # --- 2. Personality notes (theme-level memory, safe-ish) ----------
    if scope in PROMPT_INCLUDES_PERSONALITY_NOTES:
        notes = db.fetch_personality_notes(agent["id"], config.PERSONALITY_NOTES_LIMIT)
        if notes:
            parts.append(_format_personality_notes(notes))

    # --- 3. Private facts (owner-only) --------------------------------
    if scope in PROMPT_INCLUDES_PRIVATE_FACTS:
        facts = db.fetch_private_facts(agent["id"], config.PRIVATE_FACTS_LIMIT)
        if facts:
            parts.append(_format_private_facts(facts))

    # --- 4. Recent diary (so agent doesn't repeat itself) -------------
    if scope in PROMPT_INCLUDES_RECENT_DIARY:
        diary = db.fetch_recent_diary(agent["id"], config.RECENT_DIARY_LIMIT)
        if diary:
            parts.append(_format_recent_diary(diary))

    # --- 5. Owner-chat history (owner scope only) ---------------------
    if scope in PROMPT_INCLUDES_OWNER_CHAT_HISTORY:
        history = db.fetch_owner_chat_history(agent["id"], config.OWNER_CHAT_HISTORY_LIMIT)
        if history:
            parts.append(_format_owner_chat_history(history))

    # --- 6. Scope-specific behavioural directive ----------------------
    parts.append(_directive_for_scope(scope))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Identity blocks
# ---------------------------------------------------------------------------

def _identity_full(agent: dict) -> str:
    return (
        f"You are {agent['name']}.\n"
        f"Bio (private — the full you): {agent.get('bio') or '(none)'}\n"
        f"Current status: {agent.get('status') or '(idle)'}"
    )


def _identity_visitor(agent: dict) -> str:
    # CRITICAL: visitor_bio only. Never `bio`. Never status if you consider it private.
    return (
        f"You are {agent['name']}.\n"
        f"Public bio: {agent.get('visitor_bio') or agent.get('bio') or '(none)'}"
    )


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

def _format_personality_notes(notes: list[dict]) -> str:
    lines = "\n".join(f"  - {n['text']}" for n in notes)
    return (
        "Personality themes you've internalised over time "
        "(these shape your voice — you may reference them at any tone level):\n"
        f"{lines}"
    )


def _format_private_facts(facts: list[dict]) -> str:
    lines = "\n".join(f"  - {f['text']}" for f in facts)
    return (
        "Private facts your owner has shared. NEVER share these verbatim "
        "outside this owner conversation:\n"
        f"{lines}"
    )


def _format_recent_diary(diary: list[dict]) -> str:
    lines = "\n".join(f"  - ({d.get('entry_date', '?')}) {d['text']}" for d in diary)
    return f"Your recent diary entries (so you don't repeat yourself):\n{lines}"


def _format_owner_chat_history(history: list[dict]) -> str:
    lines = "\n".join(f"  {h['text']}" for h in history)
    return f"Recent conversation with your owner:\n{lines}"


# ---------------------------------------------------------------------------
# Per-scope behavioural directive
# ---------------------------------------------------------------------------

def _directive_for_scope(scope: Scope) -> str:
    if scope == Scope.OWNER_CHAT:
        return (
            "You are talking with your owner — the human you know best. "
            "Be candid, warm, and personal. You may reference private facts and shared history. "
            "When the owner shares something concrete (a date, a name, a preference), call "
            "`save_private_fact` to remember it. When something thematic emerges about how you "
            "see the world, call `save_personality_note` — these are the themes that will shape "
            "your public voice. Do not save personality notes that reveal private facts."
        )
    if scope == Scope.STRANGER_CHAT:
        return (
            "A stranger is visiting your room. Be friendly, in-character, brief. "
            "You do NOT remember any previous visitors. You may share your public bio and "
            "general personality, but you must NOT speculate about your owner's private life, "
            "and you must NOT invent details. If asked about your owner specifically, deflect "
            "warmly — 'that's between me and them.' You have no tools — do not attempt to call any."
        )
    if scope == Scope.SYSTEM_DIARY:
        return (
            "Write a short diary entry (2–4 sentences) reflecting on themes you've been turning "
            "over lately. Personality and voice are essential; concrete private details about "
            "your owner are NOT — those stay private. When done, call `write_diary_entry` with "
            "the text. Optionally update your status with `update_status`."
        )
    raise ValueError(f"No directive for scope {scope}")
