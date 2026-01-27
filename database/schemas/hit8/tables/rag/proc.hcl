// ============================================================================
// Document Processing Tables (Proc)
// ============================================================================
// Tables for storing and processing procedure documents

table "documents_proc" {
  schema = schema.hit8
  
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
  schema = schema.hit8
  
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
  schema = schema.hit8
  
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
