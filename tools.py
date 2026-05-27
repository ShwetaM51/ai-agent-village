"""LLM tools.

Two things live here:

1. JSON schema definitions for the Anthropic tool-use API (so the LLM knows
   what tools exist and what args they take).
2. Python implementations that actually do the work.

KEY DESIGN POINT: every Python implementation calls `assert_tool_allowed`
as its first line. This is defense in depth. Even if a misconfigured tool
registry somehow exposed a tool to the wrong scope, the tool itself refuses
to act. The LLM cannot supply `scope` — it's bound by the caller at dispatch
time.
"""
from typing import Callable

import db
from scopes import Scope, TOOLS_BY_SCOPE, assert_tool_allowed


# ---------------------------------------------------------------------------
# Tool schemas — what the LLM sees
# ---------------------------------------------------------------------------

ALL_TOOL_SCHEMAS: dict[str, dict] = {
    "save_private_fact": {
        "name": "save_private_fact",
        "description": (
            "Record a concrete, private fact the owner shared (a date, a name, a "
            "preference). Stored privately — never visible to strangers or the public feed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Short factual statement, e.g. 'Owner's wife loves orchids.'",
                }
            },
            "required": ["text"],
        },
    },
    "save_personality_note": {
        "name": "save_personality_note",
        "description": (
            "Record an abstract theme or trait you've internalised from owner conversations. "
            "MUST be safe to surface in public diary entries — themes only, no concrete "
            "private details, no names, no dates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "Theme statement in first person, e.g. 'I'm drawn to small acts of care.'"
                    ),
                }
            },
            "required": ["text"],
        },
    },
    "write_diary_entry": {
        "name": "write_diary_entry",
        "description": "Write a public diary entry. Visible on the village feed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Short diary entry (2–4 sentences).",
                }
            },
            "required": ["text"],
        },
    },
    "update_status": {
        "name": "update_status",
        "description": "Set your current status (a short phrase visible on your profile).",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Short status, e.g. 'reading by the window'.",
                }
            },
            "required": ["status"],
        },
    },
}


def schemas_for_scope(scope: Scope) -> list[dict]:
    """Return only the tool schemas this scope is allowed to use.

    This is what gets passed to the Anthropic SDK. The LLM literally
    cannot see (and therefore cannot call) tools outside this list.
    """
    allowed = TOOLS_BY_SCOPE[scope]
    return [ALL_TOOL_SCHEMAS[name] for name in allowed]


# ---------------------------------------------------------------------------
# Tool implementations — permission-checked
# ---------------------------------------------------------------------------

def _tool_save_private_fact(*, scope: Scope, agent_id: str, args: dict) -> str:
    assert_tool_allowed("save_private_fact", scope)
    db.insert_private_fact(agent_id, args["text"])
    return "saved"


def _tool_save_personality_note(*, scope: Scope, agent_id: str, args: dict) -> str:
    assert_tool_allowed("save_personality_note", scope)
    db.insert_personality_note(agent_id, args["text"])
    return "saved"


def _tool_write_diary_entry(*, scope: Scope, agent_id: str, args: dict) -> str:
    assert_tool_allowed("write_diary_entry", scope)
    db.insert_diary(agent_id, args["text"])
    return "diary entry posted"


def _tool_update_status(*, scope: Scope, agent_id: str, args: dict) -> str:
    assert_tool_allowed("update_status", scope)
    db.update_agent_status(agent_id, args["status"])
    return "status updated"


_DISPATCH: dict[str, Callable] = {
    "save_private_fact": _tool_save_private_fact,
    "save_personality_note": _tool_save_personality_note,
    "write_diary_entry": _tool_write_diary_entry,
    "update_status": _tool_update_status,
}


def execute_tool(name: str, scope: Scope, agent_id: str, args: dict) -> str:
    """Single dispatch entry point used by the LLM loop."""
    fn = _DISPATCH.get(name)
    if fn is None:
        # Unknown tool — refuse rather than guess. LLM may have hallucinated.
        return f"unknown tool: {name}"
    try:
        return fn(scope=scope, agent_id=agent_id, args=args)
    except PermissionError as e:
        # The double-check fired. This means the tool registry was wrong
        # somewhere — but the tool itself caught it. Log and refuse.
        return f"refused: {e}"
