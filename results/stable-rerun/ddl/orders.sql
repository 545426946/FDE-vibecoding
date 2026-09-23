CREATE TABLE "demo"."orders" (
    "id" INTEGER NOT NULL,
    "user_id" INTEGER NOT NULL,
    "status" VARCHAR(16) NOT NULL,
    "amount" NUMERIC(12,2) NOT NULL,
    "ordered_at" TIMESTAMP NOT NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
