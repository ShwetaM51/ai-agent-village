"""Configuration loaded from environment variables.

Centralised so the rest of the app never reads os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# --- Groq ---
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# llama-3.3-70b-versatile supports tool calling and is free on Groq.
# llama-3.1-8b-instant is faster if you hit rate limits.
LLM_MODEL = "llama-3.3-70b-versatile"

# Generation limits. Diary entries are short; chats medium.
LLM_MAX_TOKENS = 1024


# --- Supabase ---
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]


# --- Scheduler ---
SCHEDULER_TICK_SECONDS = int(os.environ.get("SCHEDULER_TICK_SECONDS", "30"))

# Heuristic thresholds for should_act() — small numbers for demo visibility.
DIARY_COOLDOWN_MINUTES = 5      # don't post diary entries closer together than this
BASE_DIARY_PROBABILITY = 0.4    # baseline chance per tick (after cooldown)


# --- Retrieval limits (how much history to feed the LLM) ---
OWNER_CHAT_HISTORY_LIMIT = 10   # last N messages of owner ↔ agent conversation
RECENT_DIARY_LIMIT = 5          # last N diary entries (for SYSTEM_DIARY context)
PERSONALITY_NOTES_LIMIT = 10    # last N personality notes
PRIVATE_FACTS_LIMIT = 20        # last N private facts (only owner sees)
