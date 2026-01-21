# Technical Debt

## Checkpointer: AsyncPostgresSaver and Sync-Only Paths

**Current state**: The app uses **AsyncPostgresSaver** from [`app/api/checkpointer.py`](backend/app/api/checkpointer.py) for persistent checkpoint storage. Graphs (e.g. `backend/app/flows/opgroeien/poc/chat/graph.py`) use the shared checkpointer from `get_checkpointer()`.

**Historical note**: Previously, MemorySaver was used in some flows due to async limitations in PostgresSaver (e.g. `aget_tuple()` raising `NotImplementedError`). Those have been addressed; the app now uses AsyncPostgresSaver.

**Remaining sync-only paths**: Some code paths still wrap sync checkpoint (or state) access in `asyncio.to_thread` to avoid blocking the event loop (e.g. in `app/api/routes/report.py`, `app/api/routes/graph.py`). These are documented in-code. If LangGraph improves async coverage for PostgresSaver, those wrappers could be revisited.
