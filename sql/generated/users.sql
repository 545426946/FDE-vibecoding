CREATE TABLE "public"."users" (
    "id" INTEGER NOT NULL,
    "name" VARCHAR(64) NOT NULL,
    "email" VARCHAR(128) NULL,
    "bio" TEXT NULL,
    "created_at" TIMESTAMP NOT NULL,
    "updated_at" TIMESTAMP NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
