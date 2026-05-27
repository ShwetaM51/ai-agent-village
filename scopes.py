"""The trust boundary, expressed as data.

A Scope represents the *situation* an agent is in. Every LLM call happens
in exactly one scope. Permissions (what the prompt may include, what tools
the LLM may call) are derived from the scope — never from who claims to
be whom.

This module is intentionally tiny. If you want to know whether a stranger
can save a memory, read this file. Don't grep for if-statements elsewhere.
"""
from enum import Enum
from typing import Set


class Scope(str, Enum):
    OWNER_CHAT = "OWNER_CHAT"        # owner is messaging their agent
    STRANGER_CHAT = "STRANGER_CHAT"  # anonymous visitor messaging the agent
    SYSTEM_DIARY = "SYSTEM_DIARY"    # scheduler asked the agent to post a diary


# ---------------------------------------------------------------------------
# What may be loaded INTO the prompt for each scope.
# These flags are read by prompts.build_prompt() — see prompts.py.
# ---------------------------------------------------------------------------

PROMPT_INCLUDES_FULL_BIO: Set[Scope] = {
    Scope.OWNER_CHAT,
    Scope.SYSTEM_DIARY,
}

PROMPT_INCLUDES_VISITOR_BIO_ONLY: Set[Scope] = {
    Scope.STRANGER_CHAT,
}

PROMPT_INCLUDES_PRIVATE_FACTS: Set[Scope] = {
    Scope.OWNER_CHAT,
    # SYSTEM_DIARY and STRANGER_CHAT MUST NOT read private facts.
}

PROMPT_INCLUDES_PERSONALITY_NOTES: Set[Scope] = {
    Scope.OWNER_CHAT,
    Scope.SYSTEM_DIARY,
    # Personality notes are abstract themes the agent has internalised.
    # They're safe for the diary (that's the point of the kind='personality_note' split).
    # Strangers don't see them — keeps stranger persona to the public visitor_bio.
}

PROMPT_INCLUDES_OWNER_CHAT_HISTORY: Set[Scope] = {
    Scope.OWNER_CHAT,
}

PROMPT_INCLUDES_RECENT_DIARY: Set[Scope] = {
    Scope.OWNER_CHAT,   # agent may reference what it wrote about
    Scope.SYSTEM_DIARY, # avoid repeating yesterday's entry
}


# ---------------------------------------------------------------------------
# What tools the LLM may call in each scope.
# Read by tools.build_tool_registry() — see tools.py.
# Tool names match the Python function names in tools.py.
# ---------------------------------------------------------------------------

TOOLS_BY_SCOPE: dict[Scope, Set[str]] = {
    Scope.OWNER_CHAT: {
        "save_private_fact",
        "save_personality_note",
        "write_diary_entry",
        "update_status",
    },
    Scope.STRANGER_CHAT: set(),  # strangers may not cause any writes via the LLM
    Scope.SYSTEM_DIARY: {
        "write_diary_entry",
        "update_status",
    },
}


def assert_tool_allowed(tool_name: str, scope: Scope) -> None:
    """Raised by tool implementations as a defense-in-depth check.

    Even if the LLM is somehow handed a tool it shouldn't have access to,
    the tool itself refuses to execute outside its allowed scopes.
    """
    if tool_name not in TOOLS_BY_SCOPE[scope]:
        raise PermissionError(
            f"Tool '{tool_name}' is not permitted in scope {scope.value}"
        )
