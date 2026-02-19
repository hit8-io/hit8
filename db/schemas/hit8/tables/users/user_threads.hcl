// ============================================================================
// User and Thread Management
// ============================================================================
// Tables for managing user threads and chat sessions

table "user_threads" {
  schema = schema.hit8
  
  column "thread_id" {
    null = false
    type = uuid
  }
  
  column "user_id" {
    null = false
    type = text
  }
  
  column "title" {
    null = true
    type = text
  }
  
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  
  column "last_accessed_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  
  column "flow" {
    null = true
    type = text
    comment = "Identifier format: {org}.{project}.{flow} (e.g., 'opgroeien.poc.chat')"
  }
  
  primary_key {
    columns = [column.thread_id]
  }
  
  index "idx_user_threads_last_accessed" {
    on {
      desc   = true
      column = column.last_accessed_at
    }
  }
  
  index "idx_user_threads_user_id" {
    columns = [column.user_id]
  }
  
  index "user_threads_flow_idx" {
    columns = [column.flow]
  }
  
  index "user_threads_user_id_flow_idx" {
    columns = [column.user_id, column.flow]
  }
}
