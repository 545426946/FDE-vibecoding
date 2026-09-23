CREATE TABLE "public"."edge_nulls" (
    "id" INTEGER NOT NULL,
    "title" VARCHAR(64) NULL,
    "note" TEXT NULL,
    "amount" NUMERIC(10,2) NULL,
    "happened_at" TIMESTAMP NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
