--
-- PostgreSQL database dump
--


-- Dumped from database version 15.15 (Debian 15.15-1.pgdg12+1)
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
CREATE EXTENSION IF NOT EXISTS vector;
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET search_path = public;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY "public"."relationships" DROP CONSTRAINT IF EXISTS "relationships_target_name_target_doc_target_chunk_target_d_fkey";
ALTER TABLE IF EXISTS ONLY "public"."relationships" DROP CONSTRAINT IF EXISTS "relationships_source_name_source_doc_source_chunk_source_d_fkey";
ALTER TABLE IF EXISTS ONLY "public"."embeddings_regel" DROP CONSTRAINT IF EXISTS "embeddings_regel_doc_fkey";
ALTER TABLE IF EXISTS ONLY "public"."embeddings_regel" DROP CONSTRAINT IF EXISTS "embeddings_regel_doc_chunk_fkey";
ALTER TABLE IF EXISTS ONLY "public"."embeddings_proc" DROP CONSTRAINT IF EXISTS "embeddings_proc_doc_fkey";
ALTER TABLE IF EXISTS ONLY "public"."embeddings_proc" DROP CONSTRAINT IF EXISTS "embeddings_proc_doc_chunk_fkey";
ALTER TABLE IF EXISTS ONLY "public"."chunks_regel" DROP CONSTRAINT IF EXISTS "chunks_regel_doc_fkey";
ALTER TABLE IF EXISTS ONLY "public"."chunks_proc" DROP CONSTRAINT IF EXISTS "chunks_proc_doc_fkey";
DROP INDEX IF EXISTS "public"."idx_relationships_target";
DROP INDEX IF EXISTS "public"."idx_relationships_source";
DROP INDEX IF EXISTS "public"."idx_entities_name_doc_chunk_doc_type";
DROP INDEX IF EXISTS "public"."idx_entities_doc_type";
DROP INDEX IF EXISTS "public"."idx_entities_doc";
DROP INDEX IF EXISTS "public"."idx_entities_chunk";
DROP INDEX IF EXISTS "public"."idx_embeddings_regel_doc";
DROP INDEX IF EXISTS "public"."idx_embeddings_regel_chunk";
DROP INDEX IF EXISTS "public"."idx_embeddings_proc_doc";
DROP INDEX IF EXISTS "public"."idx_embeddings_proc_chunk";
DROP INDEX IF EXISTS "public"."idx_chunks_regel_doc";
DROP INDEX IF EXISTS "public"."idx_chunks_regel_chunk";
DROP INDEX IF EXISTS "public"."idx_chunks_proc_doc";
DROP INDEX IF EXISTS "public"."idx_chunks_proc_chunk";
DROP INDEX IF EXISTS "public"."checkpoints_thread_id_idx";
DROP INDEX IF EXISTS "public"."checkpoint_writes_thread_id_idx";
DROP INDEX IF EXISTS "public"."checkpoint_blobs_thread_id_idx";
ALTER TABLE IF EXISTS ONLY "public"."relationships" DROP CONSTRAINT IF EXISTS "relationships_pkey";
ALTER TABLE IF EXISTS ONLY "public"."entities" DROP CONSTRAINT IF EXISTS "entities_pkey";
ALTER TABLE IF EXISTS ONLY "public"."entities" DROP CONSTRAINT IF EXISTS "entities_name_doc_chunk_doc_type_key";
ALTER TABLE IF EXISTS ONLY "public"."embeddings_regel" DROP CONSTRAINT IF EXISTS "embeddings_regel_pkey";
ALTER TABLE IF EXISTS ONLY "public"."embeddings_proc" DROP CONSTRAINT IF EXISTS "embeddings_proc_pkey";
ALTER TABLE IF EXISTS ONLY "public"."documents_regel" DROP CONSTRAINT IF EXISTS "documents_regel_pkey";
ALTER TABLE IF EXISTS ONLY "public"."documents_regel" DROP CONSTRAINT IF EXISTS "documents_regel_doc_key";
ALTER TABLE IF EXISTS ONLY "public"."documents_proc" DROP CONSTRAINT IF EXISTS "documents_proc_pkey";
ALTER TABLE IF EXISTS ONLY "public"."documents_proc" DROP CONSTRAINT IF EXISTS "documents_proc_doc_key";
ALTER TABLE IF EXISTS ONLY "public"."chunks_regel" DROP CONSTRAINT IF EXISTS "chunks_regel_pkey";
ALTER TABLE IF EXISTS ONLY "public"."chunks_regel" DROP CONSTRAINT IF EXISTS "chunks_regel_doc_chunk_key";
ALTER TABLE IF EXISTS ONLY "public"."chunks_proc" DROP CONSTRAINT IF EXISTS "chunks_proc_pkey";
ALTER TABLE IF EXISTS ONLY "public"."chunks_proc" DROP CONSTRAINT IF EXISTS "chunks_proc_doc_chunk_key";
ALTER TABLE IF EXISTS ONLY "public"."checkpoints" DROP CONSTRAINT IF EXISTS "checkpoints_pkey";
ALTER TABLE IF EXISTS ONLY "public"."checkpoint_writes" DROP CONSTRAINT IF EXISTS "checkpoint_writes_pkey";
ALTER TABLE IF EXISTS ONLY "public"."checkpoint_migrations" DROP CONSTRAINT IF EXISTS "checkpoint_migrations_pkey";
ALTER TABLE IF EXISTS ONLY "public"."checkpoint_blobs" DROP CONSTRAINT IF EXISTS "checkpoint_blobs_pkey";
ALTER TABLE IF EXISTS "public"."relationships" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."entities" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."embeddings_regel" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."embeddings_proc" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."documents_regel" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."documents_proc" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."chunks_regel" ALTER COLUMN "id" DROP DEFAULT;
ALTER TABLE IF EXISTS "public"."chunks_proc" ALTER COLUMN "id" DROP DEFAULT;
DROP SEQUENCE IF EXISTS "public"."relationships_id_seq";
DROP TABLE IF EXISTS "public"."relationships";
DROP SEQUENCE IF EXISTS "public"."entities_id_seq";
DROP TABLE IF EXISTS "public"."entities";
DROP SEQUENCE IF EXISTS "public"."embeddings_regel_id_seq";
DROP TABLE IF EXISTS "public"."embeddings_regel";
DROP SEQUENCE IF EXISTS "public"."embeddings_proc_id_seq";
DROP TABLE IF EXISTS "public"."embeddings_proc";
DROP SEQUENCE IF EXISTS "public"."documents_regel_id_seq";
DROP TABLE IF EXISTS "public"."documents_regel";
DROP SEQUENCE IF EXISTS "public"."documents_proc_id_seq";
DROP TABLE IF EXISTS "public"."documents_proc";
DROP SEQUENCE IF EXISTS "public"."chunks_regel_id_seq";
DROP TABLE IF EXISTS "public"."chunks_regel";
DROP SEQUENCE IF EXISTS "public"."chunks_proc_id_seq";
DROP TABLE IF EXISTS "public"."chunks_proc";
DROP TABLE IF EXISTS "public"."checkpoints";
DROP TABLE IF EXISTS "public"."checkpoint_writes";
DROP TABLE IF EXISTS "public"."checkpoint_migrations";
DROP TABLE IF EXISTS "public"."checkpoint_blobs";
--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--



--
-- Name: SCHEMA "public"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA "public" IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = "heap";

--
-- Name: checkpoint_blobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."checkpoint_blobs" (
    "thread_id" "text" NOT NULL,
    "checkpoint_ns" "text" DEFAULT ''::"text" NOT NULL,
    "channel" "text" NOT NULL,
    "version" "text" NOT NULL,
    "type" "text" NOT NULL,
    "blob" "bytea"
);


--
-- Name: checkpoint_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."checkpoint_migrations" (
    "v" integer NOT NULL
);


--
-- Name: checkpoint_writes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."checkpoint_writes" (
    "thread_id" "text" NOT NULL,
    "checkpoint_ns" "text" DEFAULT ''::"text" NOT NULL,
    "checkpoint_id" "text" NOT NULL,
    "task_id" "text" NOT NULL,
    "idx" integer NOT NULL,
    "channel" "text" NOT NULL,
    "type" "text",
    "blob" "bytea" NOT NULL,
    "task_path" "text" DEFAULT ''::"text" NOT NULL
);


--
-- Name: checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."checkpoints" (
    "thread_id" "text" NOT NULL,
    "checkpoint_ns" "text" DEFAULT ''::"text" NOT NULL,
    "checkpoint_id" "text" NOT NULL,
    "parent_checkpoint_id" "text",
    "type" "text",
    "checkpoint" "jsonb" NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL
);


--
-- Name: chunks_proc; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."chunks_proc" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: chunks_proc_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."chunks_proc_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunks_proc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."chunks_proc_id_seq" OWNED BY "public"."chunks_proc"."id";


--
-- Name: chunks_regel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."chunks_regel" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: chunks_regel_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."chunks_regel_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunks_regel_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."chunks_regel_id_seq" OWNED BY "public"."chunks_regel"."id";


--
-- Name: documents_proc; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."documents_proc" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: documents_proc_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."documents_proc_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: documents_proc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."documents_proc_id_seq" OWNED BY "public"."documents_proc"."id";


--
-- Name: documents_regel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."documents_regel" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: documents_regel_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."documents_regel_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: documents_regel_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."documents_regel_id_seq" OWNED BY "public"."documents_regel"."id";


--
-- Name: embeddings_proc; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."embeddings_proc" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "embedding" vector(1536),
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: embeddings_proc_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."embeddings_proc_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: embeddings_proc_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."embeddings_proc_id_seq" OWNED BY "public"."embeddings_proc"."id";


--
-- Name: embeddings_regel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."embeddings_regel" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "embedding" vector(1536),
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: embeddings_regel_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."embeddings_regel_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: embeddings_regel_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."embeddings_regel_id_seq" OWNED BY "public"."embeddings_regel"."id";


--
-- Name: entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."entities" (
    "id" integer NOT NULL,
    "doc_type" character varying(50) NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "name" character varying(255) NOT NULL,
    "type" character varying(255),
    "description" "text",
    "confidence" numeric(3,2),
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: entities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."entities_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: entities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."entities_id_seq" OWNED BY "public"."entities"."id";


--
-- Name: relationships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE "public"."relationships" (
    "id" integer NOT NULL,
    "source_name" character varying(255) NOT NULL,
    "source_doc" character varying(255) NOT NULL,
    "source_chunk" integer NOT NULL,
    "source_doc_type" character varying(50) NOT NULL,
    "target_name" character varying(255) NOT NULL,
    "target_doc" character varying(255) NOT NULL,
    "target_chunk" integer NOT NULL,
    "target_doc_type" character varying(50) NOT NULL,
    "description" character varying(255),
    "confidence" numeric(3,2),
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: relationships_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE "public"."relationships_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: relationships_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE "public"."relationships_id_seq" OWNED BY "public"."relationships"."id";


--
-- Name: chunks_proc id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_proc" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."chunks_proc_id_seq"'::"regclass");


--
-- Name: chunks_regel id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_regel" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."chunks_regel_id_seq"'::"regclass");


--
-- Name: documents_proc id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."documents_proc" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."documents_proc_id_seq"'::"regclass");


--
-- Name: documents_regel id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."documents_regel" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."documents_regel_id_seq"'::"regclass");


--
-- Name: embeddings_proc id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_proc" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."embeddings_proc_id_seq"'::"regclass");


--
-- Name: embeddings_regel id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_regel" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."embeddings_regel_id_seq"'::"regclass");


--
-- Name: entities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."entities" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."entities_id_seq"'::"regclass");


--
-- Name: relationships id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."relationships" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."relationships_id_seq"'::"regclass");


--
-- Name: checkpoint_blobs checkpoint_blobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."checkpoint_blobs"
    ADD CONSTRAINT "checkpoint_blobs_pkey" PRIMARY KEY ("thread_id", "checkpoint_ns", "channel", "version");


--
-- Name: checkpoint_migrations checkpoint_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."checkpoint_migrations"
    ADD CONSTRAINT "checkpoint_migrations_pkey" PRIMARY KEY ("v");


--
-- Name: checkpoint_writes checkpoint_writes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."checkpoint_writes"
    ADD CONSTRAINT "checkpoint_writes_pkey" PRIMARY KEY ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx");


--
-- Name: checkpoints checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."checkpoints"
    ADD CONSTRAINT "checkpoints_pkey" PRIMARY KEY ("thread_id", "checkpoint_ns", "checkpoint_id");


--
-- Name: chunks_proc chunks_proc_doc_chunk_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_proc"
    ADD CONSTRAINT "chunks_proc_doc_chunk_key" UNIQUE ("doc", "chunk");


--
-- Name: chunks_proc chunks_proc_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_proc"
    ADD CONSTRAINT "chunks_proc_pkey" PRIMARY KEY ("id");


--
-- Name: chunks_regel chunks_regel_doc_chunk_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_regel"
    ADD CONSTRAINT "chunks_regel_doc_chunk_key" UNIQUE ("doc", "chunk");


--
-- Name: chunks_regel chunks_regel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_regel"
    ADD CONSTRAINT "chunks_regel_pkey" PRIMARY KEY ("id");


--
-- Name: documents_proc documents_proc_doc_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."documents_proc"
    ADD CONSTRAINT "documents_proc_doc_key" UNIQUE ("doc");


--
-- Name: documents_proc documents_proc_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."documents_proc"
    ADD CONSTRAINT "documents_proc_pkey" PRIMARY KEY ("id");


--
-- Name: documents_regel documents_regel_doc_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."documents_regel"
    ADD CONSTRAINT "documents_regel_doc_key" UNIQUE ("doc");


--
-- Name: documents_regel documents_regel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."documents_regel"
    ADD CONSTRAINT "documents_regel_pkey" PRIMARY KEY ("id");


--
-- Name: embeddings_proc embeddings_proc_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_proc"
    ADD CONSTRAINT "embeddings_proc_pkey" PRIMARY KEY ("id");


--
-- Name: embeddings_regel embeddings_regel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_regel"
    ADD CONSTRAINT "embeddings_regel_pkey" PRIMARY KEY ("id");


--
-- Name: entities entities_name_doc_chunk_doc_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."entities"
    ADD CONSTRAINT "entities_name_doc_chunk_doc_type_key" UNIQUE ("name", "doc", "chunk", "doc_type");


--
-- Name: entities entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."entities"
    ADD CONSTRAINT "entities_pkey" PRIMARY KEY ("id");


--
-- Name: relationships relationships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."relationships"
    ADD CONSTRAINT "relationships_pkey" PRIMARY KEY ("id");


--
-- Name: checkpoint_blobs_thread_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "checkpoint_blobs_thread_id_idx" ON "public"."checkpoint_blobs" USING "btree" ("thread_id");


--
-- Name: checkpoint_writes_thread_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "checkpoint_writes_thread_id_idx" ON "public"."checkpoint_writes" USING "btree" ("thread_id");


--
-- Name: checkpoints_thread_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "checkpoints_thread_id_idx" ON "public"."checkpoints" USING "btree" ("thread_id");


--
-- Name: idx_chunks_proc_chunk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_chunks_proc_chunk" ON "public"."chunks_proc" USING "btree" ("chunk");


--
-- Name: idx_chunks_proc_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_chunks_proc_doc" ON "public"."chunks_proc" USING "btree" ("doc");


--
-- Name: idx_chunks_regel_chunk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_chunks_regel_chunk" ON "public"."chunks_regel" USING "btree" ("chunk");


--
-- Name: idx_chunks_regel_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_chunks_regel_doc" ON "public"."chunks_regel" USING "btree" ("doc");


--
-- Name: idx_embeddings_proc_chunk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_embeddings_proc_chunk" ON "public"."embeddings_proc" USING "btree" ("chunk");


--
-- Name: idx_embeddings_proc_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_embeddings_proc_doc" ON "public"."embeddings_proc" USING "btree" ("doc");


--
-- Name: idx_embeddings_regel_chunk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_embeddings_regel_chunk" ON "public"."embeddings_regel" USING "btree" ("chunk");


--
-- Name: idx_embeddings_regel_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_embeddings_regel_doc" ON "public"."embeddings_regel" USING "btree" ("doc");


--
-- Name: idx_entities_chunk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_entities_chunk" ON "public"."entities" USING "btree" ("chunk");


--
-- Name: idx_entities_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_entities_doc" ON "public"."entities" USING "btree" ("doc");


--
-- Name: idx_entities_doc_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_entities_doc_type" ON "public"."entities" USING "btree" ("doc_type");


--
-- Name: idx_entities_name_doc_chunk_doc_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_entities_name_doc_chunk_doc_type" ON "public"."entities" USING "btree" ("name", "doc", "chunk", "doc_type");


--
-- Name: idx_relationships_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_relationships_source" ON "public"."relationships" USING "btree" ("source_name", "source_doc", "source_chunk", "source_doc_type");


--
-- Name: idx_relationships_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX "idx_relationships_target" ON "public"."relationships" USING "btree" ("target_name", "target_doc", "target_chunk", "target_doc_type");


--
-- Name: chunks_proc chunks_proc_doc_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_proc"
    ADD CONSTRAINT "chunks_proc_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_proc"("doc") ON DELETE CASCADE;


--
-- Name: chunks_regel chunks_regel_doc_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."chunks_regel"
    ADD CONSTRAINT "chunks_regel_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_regel"("doc") ON DELETE CASCADE;


--
-- Name: embeddings_proc embeddings_proc_doc_chunk_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_proc"
    ADD CONSTRAINT "embeddings_proc_doc_chunk_fkey" FOREIGN KEY ("doc", "chunk") REFERENCES "public"."chunks_proc"("doc", "chunk") ON DELETE CASCADE;


--
-- Name: embeddings_proc embeddings_proc_doc_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_proc"
    ADD CONSTRAINT "embeddings_proc_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_proc"("doc") ON DELETE CASCADE;


--
-- Name: embeddings_regel embeddings_regel_doc_chunk_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_regel"
    ADD CONSTRAINT "embeddings_regel_doc_chunk_fkey" FOREIGN KEY ("doc", "chunk") REFERENCES "public"."chunks_regel"("doc", "chunk") ON DELETE CASCADE;


--
-- Name: embeddings_regel embeddings_regel_doc_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."embeddings_regel"
    ADD CONSTRAINT "embeddings_regel_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_regel"("doc") ON DELETE CASCADE;


--
-- Name: relationships relationships_source_name_source_doc_source_chunk_source_d_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."relationships"
    ADD CONSTRAINT "relationships_source_name_source_doc_source_chunk_source_d_fkey" FOREIGN KEY ("source_name", "source_doc", "source_chunk", "source_doc_type") REFERENCES "public"."entities"("name", "doc", "chunk", "doc_type") ON DELETE CASCADE;


--
-- Name: relationships relationships_target_name_target_doc_target_chunk_target_d_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY "public"."relationships"
    ADD CONSTRAINT "relationships_target_name_target_doc_target_chunk_target_d_fkey" FOREIGN KEY ("target_name", "target_doc", "target_chunk", "target_doc_type") REFERENCES "public"."entities"("name", "doc", "chunk", "doc_type") ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


