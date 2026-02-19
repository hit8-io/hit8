// ============================================================================
// LangGraph Checkpoint Tables
// ============================================================================
// Tables for storing LangGraph checkpoint state and history

table "checkpoint_blobs" {
  schema = schema.hit8
  
  column "thread_id" {
    null = false
    type = text
  }
  
  column "checkpoint_ns" {
    null    = false
    type    = text
    default = ""
  }
  
  column "channel" {
    null = false
    type = text
  }
  
  column "version" {
    null = false
    type = text
  }
  
  column "type" {
    null = false
    type = text
  }
  
  column "blob" {
    null = true
    type = bytea
  }
  
  primary_key {
    columns = [column.thread_id, column.checkpoint_ns, column.channel, column.version]
  }
  
  index "checkpoint_blobs_thread_id_idx" {
    columns = [column.thread_id]
  }
}

table "checkpoint_migrations" {
  schema = schema.hit8
  
  column "v" {
    null = false
    type = integer
  }
  
  primary_key {
    columns = [column.v]
  }
}

table "checkpoint_writes" {
  schema = schema.hit8
  
  column "thread_id" {
    null = false
    type = text
  }
  
  column "checkpoint_ns" {
    null    = false
    type    = text
    default = ""
  }
  
  column "checkpoint_id" {
    null = false
    type = text
  }
  
  column "task_id" {
    null = false
    type = text
  }
  
  column "idx" {
    null = false
    type = integer
  }
  
  column "channel" {
    null = false
    type = text
  }
  
  column "type" {
    null = true
    type = text
  }
  
  column "blob" {
    null = false
    type = bytea
  }
  
  column "task_path" {
    null    = false
    type    = text
    default = ""
  }
  
  primary_key {
    columns = [column.thread_id, column.checkpoint_ns, column.checkpoint_id, column.task_id, column.idx]
  }
  
  index "checkpoint_writes_thread_id_idx" {
    columns = [column.thread_id]
  }
}

table "checkpoints" {
  schema = schema.hit8
  
  column "thread_id" {
    null = false
    type = text
  }
  
  column "checkpoint_ns" {
    null    = false
    type    = text
    default = ""
  }
  
  column "checkpoint_id" {
    null = false
    type = text
  }
  
  column "parent_checkpoint_id" {
    null = true
    type = text
  }
  
  column "type" {
    null = true
    type = text
  }
  
  column "checkpoint" {
    null = false
    type = jsonb
  }
  
  column "metadata" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  
  primary_key {
    columns = [column.thread_id, column.checkpoint_ns, column.checkpoint_id]
  }
  
  index "checkpoints_thread_id_idx" {
    columns = [column.thread_id]
  }
}
