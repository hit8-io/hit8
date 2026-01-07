# Technical Debt

## Checkpointer Selection: MemorySaver vs PostgresSaver

**Location**: `backend/app/flows/opgroeien/poc/chat/graph.py`

We use `MemorySaver` instead of `PostgresSaver` because:

1. **PostgresSaver doesn't fully support async checkpoint operations**
   - `aget_tuple()` raises `NotImplementedError`
   - This forced us to use sync `stream()` in background threads

2. **MemorySaver supports both sync and async operations**
   - Enables future migration to async streaming if needed
   - Simpler architecture without database dependencies

3. **Trade-off: State is not persisted across restarts**
   - Acceptable for current use case (stateless conversations)
   - Can migrate back to PostgresSaver when async support is added

**Action Items**:
- Monitor LangGraph updates for PostgresSaver async support
- Consider migration path when `aget_tuple()` is implemented
- Document any state persistence requirements that emerge

