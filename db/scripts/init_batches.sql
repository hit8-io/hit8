BEGIN;

-- 0. Empty existing data (child tables first due to FK constraints)
TRUNCATE hit8.embeddings, hit8.chunks, hit8.documents, hit8.batches;

-- 1. Create Placeholder Batches for Legacy Data
WITH new_batches AS (
  INSERT INTO hit8.batches (org, project, name, type, version, status, metadata) 
  VALUES 
    ('opgroeien', 'poc', 'proc_migration', 'proc', 'v1', 'active', '{"migrated": true}'),
    ('opgroeien', 'poc', 'regel_migration', 'regel', 'v1', 'active', '{"migrated": true}')
  RETURNING id, type
),

-- 2. Migrate Documents (Generate UUIDs)
migrated_docs AS (
  INSERT INTO hit8.documents (id, batch_id, doc_key, type, content, metadata, created_at)
  SELECT 
    gen_random_uuid(), (SELECT id FROM new_batches WHERE type = 'proc'),
    doc, 'proc', content, metadata, created_at::timestamptz
  FROM hit8.documents_proc
  UNION ALL
  SELECT 
    gen_random_uuid(), (SELECT id FROM new_batches WHERE type = 'regel'),
    doc, 'regel', content, metadata, created_at::timestamptz
  FROM hit8.documents_regel
  RETURNING id, doc_key, type
),

-- 3. Migrate Chunks (Link to new Doc UUIDs)
migrated_chunks AS (
  INSERT INTO hit8.chunks (id, document_id, chunk_index, content, metadata)
  SELECT 
    gen_random_uuid(), md.id, old.chunk, old.content, old.metadata
  FROM hit8.chunks_proc old JOIN migrated_docs md ON md.doc_key = old.doc AND md.type = 'proc'
  UNION ALL
  SELECT 
    gen_random_uuid(), md.id, old.chunk, old.content, old.metadata
  FROM hit8.chunks_regel old JOIN migrated_docs md ON md.doc_key = old.doc AND md.type = 'regel'
  RETURNING id, document_id, chunk_index
)

-- 4. Migrate Embeddings (Link to new Chunk UUIDs)
INSERT INTO hit8.embeddings (id, chunk_id, embedding, type, batch_id)
SELECT 
  gen_random_uuid(), mc.id, old.embedding, 'proc', (SELECT id FROM new_batches WHERE type = 'proc')
FROM hit8.embeddings_proc old
JOIN hit8.chunks_proc old_c ON old.doc = old_c.doc AND old.chunk = old_c.chunk
JOIN migrated_docs md ON md.doc_key = old.doc AND md.type = 'proc'
JOIN migrated_chunks mc ON mc.document_id = md.id AND mc.chunk_index = old.chunk
UNION ALL
SELECT 
  gen_random_uuid(), mc.id, old.embedding, 'regel', (SELECT id FROM new_batches WHERE type = 'regel')
FROM hit8.embeddings_regel old
JOIN hit8.chunks_regel old_c ON old.doc = old_c.doc AND old.chunk = old_c.chunk
JOIN migrated_docs md ON md.doc_key = old.doc AND md.type = 'regel'
JOIN migrated_chunks mc ON mc.document_id = md.id AND mc.chunk_index = old.chunk;

COMMIT;
