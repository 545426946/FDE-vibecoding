CREATE TABLE "demo"."edge_empty" (
    "id" INTEGER NOT NULL,
    "payload" VARCHAR(32) NOT NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
