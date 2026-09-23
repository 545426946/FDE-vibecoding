CREATE TABLE "demo"."edge_types" (
    "id" BIGINT NOT NULL,
    "tiny_flag" SMALLINT NOT NULL,
    "enum_status" VARCHAR(32) NOT NULL,
    "price" NUMERIC(10,2) NOT NULL,
    "ratio" NUMERIC(18,6) NOT NULL,
    "event_time" TIMESTAMP NOT NULL,
    "ts_col" TIMESTAMP NOT NULL,
    "short_name" VARCHAR(1) NOT NULL,
    PRIMARY KEY ("id")
)
DISTRIBUTED BY ("id");
