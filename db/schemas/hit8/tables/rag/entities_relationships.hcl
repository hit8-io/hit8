// ============================================================================
// Entity and Relationship Tables
// ============================================================================
// Tables for storing extracted entities and their relationships

table "entities" {
  schema = schema.hit8
  
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
  schema = schema.hit8
  
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
