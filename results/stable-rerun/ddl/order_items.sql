CREATE TABLE "demo"."order_items" (
    "id" INTEGER NOT NULL,
    "order_id" INTEGER NOT NULL,
    "product_id" BIGINT NOT NULL,
    "qty" INTEGER NOT NULL,
    "unit_price" NUMERIC(10,2) NOT NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
