table "documents_regel" {
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
  
  unique "documents_regel_doc_key" {
    columns = [column.doc]
  }
}

table "chunks_regel" {
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

  index "idx_embeddings_regel_vector" {
    type = "HNSW"
    on {
      column = column.embedding
      ops    = "vector_l2_ops"
    }
  }
}
