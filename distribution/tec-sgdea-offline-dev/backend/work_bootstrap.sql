BEGIN;
CREATE TABLE IF NOT EXISTS offline_sheet_receipt (
    operation_id uuid PRIMARY KEY,
    fingerprint char(64) NOT NULL,
    estado text NOT NULL
);
DO $verify$
BEGIN
    IF (SELECT array_agg(attname::text || ':' || format_type(atttypid, atttypmod)
                         ORDER BY attnum)
        FROM pg_attribute
        WHERE attrelid = 'offline_sheet_receipt'::regclass AND attnum > 0 AND NOT attisdropped
          AND attnotnull) IS DISTINCT FROM
       ARRAY['operation_id:uuid', 'fingerprint:character(64)', 'estado:text']
       OR (SELECT count(*) FROM pg_attribute
           WHERE attrelid = 'offline_sheet_receipt'::regclass AND attnum > 0 AND NOT attisdropped) <> 3
       OR NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid = 'offline_sheet_receipt'::regclass
                      AND contype = 'p' AND conkey = ARRAY[1::smallint]) THEN
        RAISE EXCEPTION 'Estructura incompatible para offline_sheet_receipt';
    END IF;
END
$verify$;
GRANT SELECT, INSERT ON offline_sheet_receipt TO geology_runtime;
COMMIT;
