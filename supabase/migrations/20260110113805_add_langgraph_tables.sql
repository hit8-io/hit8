CREATE EXTENSION "pgjwt" WITH SCHEMA "extensions" VERSION "0.2.0";

CREATE TABLE "public"."checkpoint_blobs" (
	"thread_id" text COLLATE "pg_catalog"."default" NOT NULL,
	"checkpoint_ns" text COLLATE "pg_catalog"."default" DEFAULT ''::text NOT NULL,
	"channel" text COLLATE "pg_catalog"."default" NOT NULL,
	"version" text COLLATE "pg_catalog"."default" NOT NULL,
	"type" text COLLATE "pg_catalog"."default" NOT NULL,
	"blob" bytea
);

CREATE UNIQUE INDEX checkpoint_blobs_pkey ON public.checkpoint_blobs USING btree (thread_id, checkpoint_ns, channel, version);

ALTER TABLE "public"."checkpoint_blobs" ADD CONSTRAINT "checkpoint_blobs_pkey" PRIMARY KEY USING INDEX "checkpoint_blobs_pkey";

CREATE INDEX checkpoint_blobs_thread_id_idx ON public.checkpoint_blobs USING btree (thread_id);

CREATE TABLE "public"."checkpoint_migrations" (
	"v" integer NOT NULL
);

CREATE UNIQUE INDEX checkpoint_migrations_pkey ON public.checkpoint_migrations USING btree (v);

ALTER TABLE "public"."checkpoint_migrations" ADD CONSTRAINT "checkpoint_migrations_pkey" PRIMARY KEY USING INDEX "checkpoint_migrations_pkey";

CREATE TABLE "public"."checkpoint_writes" (
	"thread_id" text COLLATE "pg_catalog"."default" NOT NULL,
	"checkpoint_ns" text COLLATE "pg_catalog"."default" DEFAULT ''::text NOT NULL,
	"checkpoint_id" text COLLATE "pg_catalog"."default" NOT NULL,
	"task_id" text COLLATE "pg_catalog"."default" NOT NULL,
	"idx" integer NOT NULL,
	"channel" text COLLATE "pg_catalog"."default" NOT NULL,
	"type" text COLLATE "pg_catalog"."default",
	"blob" bytea NOT NULL,
	"task_path" text COLLATE "pg_catalog"."default" DEFAULT ''::text NOT NULL
);

CREATE UNIQUE INDEX checkpoint_writes_pkey ON public.checkpoint_writes USING btree (thread_id, checkpoint_ns, checkpoint_id, task_id, idx);

ALTER TABLE "public"."checkpoint_writes" ADD CONSTRAINT "checkpoint_writes_pkey" PRIMARY KEY USING INDEX "checkpoint_writes_pkey";

CREATE INDEX checkpoint_writes_thread_id_idx ON public.checkpoint_writes USING btree (thread_id);

CREATE TABLE "public"."checkpoints" (
	"thread_id" text COLLATE "pg_catalog"."default" NOT NULL,
	"checkpoint_ns" text COLLATE "pg_catalog"."default" DEFAULT ''::text NOT NULL,
	"checkpoint_id" text COLLATE "pg_catalog"."default" NOT NULL,
	"parent_checkpoint_id" text COLLATE "pg_catalog"."default",
	"type" text COLLATE "pg_catalog"."default",
	"checkpoint" jsonb NOT NULL,
	"metadata" jsonb DEFAULT '{}'::jsonb NOT NULL
);

CREATE UNIQUE INDEX checkpoints_pkey ON public.checkpoints USING btree (thread_id, checkpoint_ns, checkpoint_id);

ALTER TABLE "public"."checkpoints" ADD CONSTRAINT "checkpoints_pkey" PRIMARY KEY USING INDEX "checkpoints_pkey";

CREATE INDEX checkpoints_thread_id_idx ON public.checkpoints USING btree (thread_id);

