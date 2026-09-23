CREATE TABLE "demo"."payments" (
    "id" INTEGER NOT NULL,
    "order_id" INTEGER NOT NULL,
    "paid_amount" NUMERIC(12,2) NOT NULL,
    "paid_at" TIMESTAMP NOT NULL,
    "channel" VARCHAR(32) NOT NULL,
    "remark" TEXT NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
