-- Create user_threads table if it doesn't exist
-- This table tracks chat threads per user
CREATE TABLE IF NOT EXISTS public.user_threads (
    thread_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.user_threads ENABLE ROW LEVEL SECURITY;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_user_threads_last_accessed 
ON public.user_threads USING btree (last_accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_threads_user_id 
ON public.user_threads USING btree (user_id);

-- Add flow column to user_threads table
-- Flow identifies which LangGraph instance (chat/report) a thread belongs to
-- Format: "{org}.{project}.{flow}" (e.g., "opgroeien.poc.chat")

-- Add flow column (nullable initially for backward compatibility)
ALTER TABLE public.user_threads
ADD COLUMN IF NOT EXISTS flow TEXT;

-- Migrate existing threads: set flow = 'opgroeien.poc.chat' for all existing threads
-- (Assumption: existing threads are chat threads)
UPDATE public.user_threads
SET flow = 'opgroeien.poc.chat'
WHERE flow IS NULL;

-- Add index on (user_id, flow) for efficient filtering
CREATE INDEX IF NOT EXISTS user_threads_user_id_flow_idx 
ON public.user_threads(user_id, flow);

-- Add index on flow for cleanup script queries
CREATE INDEX IF NOT EXISTS user_threads_flow_idx 
ON public.user_threads(flow);
