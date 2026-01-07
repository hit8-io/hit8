


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "extensions";





SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."chunks_proc" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."chunks_proc" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."chunks_proc_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."chunks_proc_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."chunks_proc_id_seq" OWNED BY "public"."chunks_proc"."id";



CREATE TABLE IF NOT EXISTS "public"."chunks_regel" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."chunks_regel" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."chunks_regel_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."chunks_regel_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."chunks_regel_id_seq" OWNED BY "public"."chunks_regel"."id";



CREATE TABLE IF NOT EXISTS "public"."documents_proc" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."documents_proc" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."documents_proc_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."documents_proc_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."documents_proc_id_seq" OWNED BY "public"."documents_proc"."id";



CREATE TABLE IF NOT EXISTS "public"."documents_regel" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "content" "text",
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."documents_regel" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."documents_regel_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."documents_regel_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."documents_regel_id_seq" OWNED BY "public"."documents_regel"."id";



CREATE TABLE IF NOT EXISTS "public"."embeddings_proc" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "embedding" "extensions"."vector"(1536),
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."embeddings_proc" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."embeddings_proc_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."embeddings_proc_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."embeddings_proc_id_seq" OWNED BY "public"."embeddings_proc"."id";



CREATE TABLE IF NOT EXISTS "public"."embeddings_regel" (
    "id" integer NOT NULL,
    "doc" character varying(255) NOT NULL,
    "chunk" integer,
    "content" "text",
    "embedding" "extensions"."vector"(1536),
    "metadata" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."embeddings_regel" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."embeddings_regel_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."embeddings_regel_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."embeddings_regel_id_seq" OWNED BY "public"."embeddings_regel"."id";



CREATE TABLE IF NOT EXISTS "public"."entities" (
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


ALTER TABLE "public"."entities" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."entities_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."entities_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."entities_id_seq" OWNED BY "public"."entities"."id";



CREATE TABLE IF NOT EXISTS "public"."relationships" (
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


ALTER TABLE "public"."relationships" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."relationships_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."relationships_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."relationships_id_seq" OWNED BY "public"."relationships"."id";



ALTER TABLE ONLY "public"."chunks_proc" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."chunks_proc_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."chunks_regel" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."chunks_regel_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."documents_proc" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."documents_proc_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."documents_regel" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."documents_regel_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."embeddings_proc" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."embeddings_proc_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."embeddings_regel" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."embeddings_regel_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."entities" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."entities_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."relationships" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."relationships_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."chunks_proc"
    ADD CONSTRAINT "chunks_proc_doc_chunk_key" UNIQUE ("doc", "chunk");



ALTER TABLE ONLY "public"."chunks_proc"
    ADD CONSTRAINT "chunks_proc_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chunks_regel"
    ADD CONSTRAINT "chunks_regel_doc_chunk_key" UNIQUE ("doc", "chunk");



ALTER TABLE ONLY "public"."chunks_regel"
    ADD CONSTRAINT "chunks_regel_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."documents_proc"
    ADD CONSTRAINT "documents_proc_doc_key" UNIQUE ("doc");



ALTER TABLE ONLY "public"."documents_proc"
    ADD CONSTRAINT "documents_proc_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."documents_regel"
    ADD CONSTRAINT "documents_regel_doc_key" UNIQUE ("doc");



ALTER TABLE ONLY "public"."documents_regel"
    ADD CONSTRAINT "documents_regel_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."embeddings_proc"
    ADD CONSTRAINT "embeddings_proc_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."embeddings_regel"
    ADD CONSTRAINT "embeddings_regel_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."entities"
    ADD CONSTRAINT "entities_name_doc_chunk_doc_type_key" UNIQUE ("name", "doc", "chunk", "doc_type");



ALTER TABLE ONLY "public"."entities"
    ADD CONSTRAINT "entities_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."relationships"
    ADD CONSTRAINT "relationships_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_chunks_proc_chunk" ON "public"."chunks_proc" USING "btree" ("chunk");



CREATE INDEX "idx_chunks_proc_doc" ON "public"."chunks_proc" USING "btree" ("doc");



CREATE INDEX "idx_chunks_regel_chunk" ON "public"."chunks_regel" USING "btree" ("chunk");



CREATE INDEX "idx_chunks_regel_doc" ON "public"."chunks_regel" USING "btree" ("doc");



CREATE INDEX "idx_embeddings_proc_chunk" ON "public"."embeddings_proc" USING "btree" ("chunk");



CREATE INDEX "idx_embeddings_proc_doc" ON "public"."embeddings_proc" USING "btree" ("doc");



CREATE INDEX "idx_embeddings_regel_chunk" ON "public"."embeddings_regel" USING "btree" ("chunk");



CREATE INDEX "idx_embeddings_regel_doc" ON "public"."embeddings_regel" USING "btree" ("doc");



CREATE INDEX "idx_entities_chunk" ON "public"."entities" USING "btree" ("chunk");



CREATE INDEX "idx_entities_doc" ON "public"."entities" USING "btree" ("doc");



CREATE INDEX "idx_entities_doc_type" ON "public"."entities" USING "btree" ("doc_type");



CREATE INDEX "idx_entities_name_doc_chunk_doc_type" ON "public"."entities" USING "btree" ("name", "doc", "chunk", "doc_type");



CREATE INDEX "idx_relationships_source" ON "public"."relationships" USING "btree" ("source_name", "source_doc", "source_chunk", "source_doc_type");



CREATE INDEX "idx_relationships_target" ON "public"."relationships" USING "btree" ("target_name", "target_doc", "target_chunk", "target_doc_type");



ALTER TABLE ONLY "public"."chunks_proc"
    ADD CONSTRAINT "chunks_proc_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_proc"("doc") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chunks_regel"
    ADD CONSTRAINT "chunks_regel_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_regel"("doc") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."embeddings_proc"
    ADD CONSTRAINT "embeddings_proc_doc_chunk_fkey" FOREIGN KEY ("doc", "chunk") REFERENCES "public"."chunks_proc"("doc", "chunk") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."embeddings_proc"
    ADD CONSTRAINT "embeddings_proc_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_proc"("doc") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."embeddings_regel"
    ADD CONSTRAINT "embeddings_regel_doc_chunk_fkey" FOREIGN KEY ("doc", "chunk") REFERENCES "public"."chunks_regel"("doc", "chunk") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."embeddings_regel"
    ADD CONSTRAINT "embeddings_regel_doc_fkey" FOREIGN KEY ("doc") REFERENCES "public"."documents_regel"("doc") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."relationships"
    ADD CONSTRAINT "relationships_source_name_source_doc_source_chunk_source_d_fkey" FOREIGN KEY ("source_name", "source_doc", "source_chunk", "source_doc_type") REFERENCES "public"."entities"("name", "doc", "chunk", "doc_type") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."relationships"
    ADD CONSTRAINT "relationships_target_name_target_doc_target_chunk_target_d_fkey" FOREIGN KEY ("target_name", "target_doc", "target_chunk", "target_doc_type") REFERENCES "public"."entities"("name", "doc", "chunk", "doc_type") ON DELETE CASCADE;



ALTER TABLE "public"."chunks_proc" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chunks_regel" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."documents_proc" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."documents_regel" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."embeddings_proc" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."embeddings_regel" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."entities" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."relationships" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";










































































































































































































































































































































































































































































































































GRANT ALL ON TABLE "public"."chunks_proc" TO "anon";
GRANT ALL ON TABLE "public"."chunks_proc" TO "authenticated";
GRANT ALL ON TABLE "public"."chunks_proc" TO "service_role";



GRANT ALL ON SEQUENCE "public"."chunks_proc_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."chunks_proc_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."chunks_proc_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."chunks_regel" TO "anon";
GRANT ALL ON TABLE "public"."chunks_regel" TO "authenticated";
GRANT ALL ON TABLE "public"."chunks_regel" TO "service_role";



GRANT ALL ON SEQUENCE "public"."chunks_regel_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."chunks_regel_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."chunks_regel_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."documents_proc" TO "anon";
GRANT ALL ON TABLE "public"."documents_proc" TO "authenticated";
GRANT ALL ON TABLE "public"."documents_proc" TO "service_role";



GRANT ALL ON SEQUENCE "public"."documents_proc_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."documents_proc_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."documents_proc_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."documents_regel" TO "anon";
GRANT ALL ON TABLE "public"."documents_regel" TO "authenticated";
GRANT ALL ON TABLE "public"."documents_regel" TO "service_role";



GRANT ALL ON SEQUENCE "public"."documents_regel_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."documents_regel_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."documents_regel_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."embeddings_proc" TO "anon";
GRANT ALL ON TABLE "public"."embeddings_proc" TO "authenticated";
GRANT ALL ON TABLE "public"."embeddings_proc" TO "service_role";



GRANT ALL ON SEQUENCE "public"."embeddings_proc_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."embeddings_proc_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."embeddings_proc_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."embeddings_regel" TO "anon";
GRANT ALL ON TABLE "public"."embeddings_regel" TO "authenticated";
GRANT ALL ON TABLE "public"."embeddings_regel" TO "service_role";



GRANT ALL ON SEQUENCE "public"."embeddings_regel_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."embeddings_regel_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."embeddings_regel_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."entities" TO "anon";
GRANT ALL ON TABLE "public"."entities" TO "authenticated";
GRANT ALL ON TABLE "public"."entities" TO "service_role";



GRANT ALL ON SEQUENCE "public"."entities_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."entities_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."entities_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."relationships" TO "anon";
GRANT ALL ON TABLE "public"."relationships" TO "authenticated";
GRANT ALL ON TABLE "public"."relationships" TO "service_role";



GRANT ALL ON SEQUENCE "public"."relationships_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."relationships_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."relationships_id_seq" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































drop extension if exists "pg_net";


