// Database Schema Definition
// This file defines the desired state of the database using Atlas HCL format.
// 
// To extract the current schema: ./extract-schema.sh [dev|stg|prd]
// To apply schema changes: atlas schema apply --to file://schema.hcl --url "<connection-string>"

schema "public" {
}

// ============================================================================
// LangGraph Checkpoint Tables
// ============================================================================
// Tables for storing LangGraph checkpoint state and history

table "checkpoint_blobs" {
  schema = schema.public
  
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
  schema = schema.public
  
  column "v" {
    null = false
    type = integer
  }
  
  primary_key {
    columns = [column.v]
  }
}

table "checkpoint_writes" {
  schema = schema.public
  
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
  schema = schema.public
  
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

// ============================================================================
// Document Processing Tables (Proc)
// ============================================================================
// Tables for storing and processing procedure documents

table "documents_proc" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "content" {
    null = true
    type = text
  }
  
  column "metadata" {
    null = true
    type = jsonb
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  unique "documents_proc_doc_key" {
    columns = [column.doc]
  }
}

table "chunks_proc" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "chunk" {
    null = true
    type = integer
  }
  
  column "content" {
    null = true
    type = text
  }
  
  column "metadata" {
    null = true
    type = jsonb
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  foreign_key "chunks_proc_doc_fkey" {
    columns     = [column.doc]
    ref_columns = [table.documents_proc.column.doc]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  index "idx_chunks_proc_chunk" {
    columns = [column.chunk]
  }
  
  index "idx_chunks_proc_doc" {
    columns = [column.doc]
  }
  
  unique "chunks_proc_doc_chunk_key" {
    columns = [column.doc, column.chunk]
  }
}

table "embeddings_proc" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "chunk" {
    null = true
    type = integer
  }
  
  column "content" {
    null = true
    type = text
  }
  
  column "embedding" {
    null = true
    type = sql("extensions.vector(1536)")
  }
  
  column "metadata" {
    null = true
    type = jsonb
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  foreign_key "embeddings_proc_doc_chunk_fkey" {
    columns     = [column.doc, column.chunk]
    ref_columns = [table.chunks_proc.column.doc, table.chunks_proc.column.chunk]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  foreign_key "embeddings_proc_doc_fkey" {
    columns     = [column.doc]
    ref_columns = [table.documents_proc.column.doc]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  index "idx_embeddings_proc_chunk" {
    columns = [column.chunk]
  }
  
  index "idx_embeddings_proc_doc" {
    columns = [column.doc]
  }
}

// ============================================================================
// Document Processing Tables (Regel)
// ============================================================================
// Tables for storing and processing regulation documents

table "documents_regel" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "content" {
    null = true
    type = text
  }
  
  column "metadata" {
    null = true
    type = jsonb
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  unique "documents_regel_doc_key" {
    columns = [column.doc]
  }
}

table "chunks_regel" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "chunk" {
    null = true
    type = integer
  }
  
  column "content" {
    null = true
    type = text
  }
  
  column "metadata" {
    null = true
    type = jsonb
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  foreign_key "chunks_regel_doc_fkey" {
    columns     = [column.doc]
    ref_columns = [table.documents_regel.column.doc]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  index "idx_chunks_regel_chunk" {
    columns = [column.chunk]
  }
  
  index "idx_chunks_regel_doc" {
    columns = [column.doc]
  }
  
  unique "chunks_regel_doc_chunk_key" {
    columns = [column.doc, column.chunk]
  }
}

table "embeddings_regel" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "chunk" {
    null = true
    type = integer
  }
  
  column "content" {
    null = true
    type = text
  }
  
  column "embedding" {
    null = true
    type = sql("extensions.vector(1536)")
  }
  
  column "metadata" {
    null = true
    type = jsonb
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  foreign_key "embeddings_regel_doc_chunk_fkey" {
    columns     = [column.doc, column.chunk]
    ref_columns = [table.chunks_regel.column.doc, table.chunks_regel.column.chunk]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  foreign_key "embeddings_regel_doc_fkey" {
    columns     = [column.doc]
    ref_columns = [table.documents_regel.column.doc]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  index "idx_embeddings_regel_chunk" {
    columns = [column.chunk]
  }
  
  index "idx_embeddings_regel_doc" {
    columns = [column.doc]
  }
}

// ============================================================================
// Entity and Relationship Tables
// ============================================================================
// Tables for storing extracted entities and their relationships

table "entities" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "doc_type" {
    null = false
    type = character_varying(50)
  }
  
  column "doc" {
    null = false
    type = character_varying(255)
  }
  
  column "chunk" {
    null = true
    type = integer
  }
  
  column "name" {
    null = false
    type = character_varying(255)
  }
  
  column "type" {
    null = true
    type = character_varying(255)
  }
  
  column "description" {
    null = true
    type = text
  }
  
  column "confidence" {
    null = true
    type = numeric(3, 2)
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  index "idx_entities_chunk" {
    columns = [column.chunk]
  }
  
  index "idx_entities_doc" {
    columns = [column.doc]
  }
  
  index "idx_entities_doc_type" {
    columns = [column.doc_type]
  }
  
  index "idx_entities_name_doc_chunk_doc_type" {
    columns = [column.name, column.doc, column.chunk, column.doc_type]
  }
  
  unique "entities_name_doc_chunk_doc_type_key" {
    columns = [column.name, column.doc, column.chunk, column.doc_type]
  }
}

table "relationships" {
  schema = schema.public
  
  column "id" {
    null = false
    type = serial
  }
  
  column "source_name" {
    null = false
    type = character_varying(255)
  }
  
  column "source_doc" {
    null = false
    type = character_varying(255)
  }
  
  column "source_chunk" {
    null = false
    type = integer
  }
  
  column "source_doc_type" {
    null = false
    type = character_varying(50)
  }
  
  column "target_name" {
    null = false
    type = character_varying(255)
  }
  
  column "target_doc" {
    null = false
    type = character_varying(255)
  }
  
  column "target_chunk" {
    null = false
    type = integer
  }
  
  column "target_doc_type" {
    null = false
    type = character_varying(50)
  }
  
  column "description" {
    null = true
    type = character_varying(255)
  }
  
  column "confidence" {
    null = true
    type = numeric(3, 2)
  }
  
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  
  foreign_key "relationships_source_name_source_doc_source_chunk_source_d_fkey" {
    columns     = [column.source_name, column.source_doc, column.source_chunk, column.source_doc_type]
    ref_columns = [table.entities.column.name, table.entities.column.doc, table.entities.column.chunk, table.entities.column.doc_type]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  foreign_key "relationships_target_name_target_doc_target_chunk_target_d_fkey" {
    columns     = [column.target_name, column.target_doc, column.target_chunk, column.target_doc_type]
    ref_columns = [table.entities.column.name, table.entities.column.doc, table.entities.column.chunk, table.entities.column.doc_type]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  
  index "idx_relationships_source" {
    columns = [column.source_name, column.source_doc, column.source_chunk, column.source_doc_type]
  }
  
  index "idx_relationships_target" {
    columns = [column.target_name, column.target_doc, column.target_chunk, column.target_doc_type]
  }
}

// ============================================================================
// User and Thread Management
// ============================================================================
// Tables for managing user threads and chat sessions

table "user_threads" {
  schema = schema.public
  
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
    comment = "Flow identifier in format: {org}.{project}.{flow} (e.g., 'opgroeien.poc.chat')"
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
