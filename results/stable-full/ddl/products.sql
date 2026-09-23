CREATE TABLE "demo"."products" (
    "id" BIGINT NOT NULL,
    "sku" VARCHAR(32) NOT NULL,
    "name" VARCHAR(128) NOT NULL,
    "description" TEXT NULL,
    "price" NUMERIC(10,2) NOT NULL,
    "cost" NUMERIC(18,6) NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
