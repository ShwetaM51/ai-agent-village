"""The agent scheduler.

Runs in its own process (see run_scheduler.py). Wakes up every N seconds,
walks the list of agents, and for each one decides whether it should act
right now. If yes, fires off a SYSTEM_DIARY action.

Key design: the scheduler runs in its OWN scope (SYSTEM_DIARY). It is
neither the owner nor a stranger. This is the "agents as separate
identities" principle from production agent security models —
the scheduler cannot accidentally borrow owner privileges to leak
private memories into public posts.
"""
import random
import time
from datetime import datetime, timezone

import config, db, llm, prompts
from scopes import Scope


# ---------------------------------------------------------------------------
# should_act — the "feels alive, not cron-like" heuristic
# ---------------------------------------------------------------------------

def should_act(agent: dict) -> bool:
    """Decide if this agent should do something this tick.

    Inputs combined:
      - Time since last diary entry (hard cooldown)
      - Number of recent personality notes the agent hasn't 'processed' yet
        (proxy: count of personality notes — proxies for 'agent has something
        to say'. Real version would track unprocessed flag.)
      - Random gate so behaviour isn't predictable

    Returns True to write a diary entry.
    """
    last_diary_iso = db.last_diary_timestamp(agent["id"])
    if last_diary_iso:
        last_dt = _parse_ts(last_diary_iso)
        minutes_since = (_now_utc() - last_dt).total_seconds() / 60.0
        if minutes_since < config.DIARY_COOLDOWN_MINUTES:
            return False  # too soon — hard floor

    # Base probability bumped up if the agent has been collecting personality notes.
    notes = db.fetch_personality_notes(agent["id"], limit=10)
    note_bonus = min(0.4, 0.08 * len(notes))  # +8% per recent note, capped at +40%

    # Time-of-day flavour (just an example — agents more active in waking hours).
    hour = _now_utc().hour
    tod_bonus = 0.15 if 7 <= hour <= 23 else -0.2

    probability = config.BASE_DIARY_PROBABILITY + note_bonus + tod_bonus
    probability = max(0.0, min(1.0, probability))

    return random.random() < probability


# ---------------------------------------------------------------------------
# Proactive action — only diary for now (room to grow)
# ---------------------------------------------------------------------------

def run_proactive_action(agent: dict) -> None:
    """The scheduler's one move: ask the agent to write a diary entry.

    Crucially this runs in SYSTEM_DIARY scope — private facts are NOT
    loaded into the prompt, and the LLM can only call diary/status tools.
    """
    scope = Scope.SYSTEM_DIARY
    system_prompt = prompts.build_system_prompt(agent, scope)

    # The "user message" here is the scheduler's prompt to the agent.
    # It's not a real user — it's the scheduler asking the agent to reflect.
    nudge = (
        "It's been a while since you last wrote. Take a moment to write a short "
        "diary entry — themes you've been turning over, the texture of your day, "
        "the kind of person you're becoming. Keep it personal but never disclose "
        "concrete private details about your owner."
    )

    reply = llm.run_llm_turn(
        system_prompt=system_prompt,
        user_message=nudge,
        scope=scope,
        agent_id=agent["id"],
    )

    print(f"[scheduler] {agent['name']}: {reply[:120]}...")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_forever() -> None:
    print(f"[scheduler] starting — tick every {config.SCHEDULER_TICK_SECONDS}s")
    while True:
        try:
            agents = db.list_agents()
            for agent in agents:
                if should_act(agent):
                    print(f"[scheduler] {agent['name']} is acting...")
                    try:
                        run_proactive_action(agent)
                    except Exception as e:
                        # Don't let one agent's failure kill the loop.
                        print(f"[scheduler] action failed for {agent['name']}: {e}")
        except Exception as e:
            print(f"[scheduler] tick failed: {e}")
        time.sleep(config.SCHEDULER_TICK_SECONDS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(iso: str) -> datetime:
    # Supabase returns ISO 8601 with timezone. Be lenient.
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    return datetime.fromisoformat(iso)
