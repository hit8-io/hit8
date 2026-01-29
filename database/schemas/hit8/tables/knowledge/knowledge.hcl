table "batches" {
  schema = schema.hit8
  column "id" {
    null = false
    type = uuid
    default = sql("gen_random_uuid()")
  }
  
  # Multi-Tenancy & Versioning
  column "org" {
    null = false
    type = character_varying(100)
  }
  column "project" {
    null = false
    type = character_varying(100)
  }
  column "name" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = character_varying(50)
  } # 'proc', 'regel'
  column "version" {
    null = false
    type = character_varying(50)
  } # 'v1', 'v2'
  
  # Status lives ONLY in DB (Hot/Cold state)
  column "status" {
    null = false
    type = character_varying(20)
    default = "active"
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "created_at" {
    null = true
    type = timestamptz
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  index "idx_batches_status_type" {
    columns = [column.status, column.type]
  }
  index "idx_batches_org_project" {
    columns = [column.org, column.project]
  }
}

table "documents" {
  schema = schema.hit8
  column "id" {
    null = false
    type = uuid
    default = sql("gen_random_uuid()")
  }
  column "batch_id" {
    null = false
    type = uuid
  }
  column "doc_key" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(50)
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
    null = true
    type = timestamptz
    default = sql("CURRENT_TIMESTAMP")
  }
  
  primary_key {
    columns = [column.id]
  }
  foreign_key "documents_batch_fkey" {
    columns = [column.batch_id]
    ref_columns = [table.batches.column.id]
    on_delete = CASCADE
  }
  unique "documents_batch_doc_key" {
    columns = [column.batch_id, column.doc_key]
  }
}

table "chunks" {
  schema = schema.hit8
  column "id" {
    null = false
    type = uuid
    default = sql("gen_random_uuid()")
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "chunk_index" {
    null = false
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
  
  primary_key {
    columns = [column.id]
  }
  foreign_key "chunks_document_fkey" {
    columns = [column.document_id]
    ref_columns = [table.documents.column.id]
    on_delete = CASCADE
  }
}

table "embeddings" {
  schema = schema.hit8
  column "id" {
    null = false
    type = uuid
    default = sql("gen_random_uuid()")
  }
  column "chunk_id" {
    null = false
    type = uuid
  }
  column "embedding" {
    null = true
    type = sql("extensions.vector(1536)")
  }
  column "batch_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  
  primary_key {
    columns = [column.id]
  }
  foreign_key "embeddings_chunk_fkey" {
    columns = [column.chunk_id]
    ref_columns = [table.chunks.column.id]
    on_delete = CASCADE
  }
  
  # HNSW Index (Unmanaged params)
  index "idx_embeddings_unified_vector" {
    type = "HNSW"
    on {
      column = column.embedding
      ops = "vector_l2_ops"
    }
  }
  # Filter Index (Critical for RAG)
  index "idx_embeddings_filter" {
    columns = [column.batch_id, column.type]
  }
}
