"""LLM chat integration for FinAlly (PLAN.md §9).

Framework-free where possible: schema, prompt construction, parsing, and the
LLM_MOCK path live here and are unit-testable without FastAPI. The /api/chat
route (api/chat.py) orchestrates DB reads/writes and trade execution around
this module.
"""
