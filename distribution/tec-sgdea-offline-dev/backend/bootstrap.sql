CREATE TABLE IF NOT EXISTS offline_sync_operation (
    operation_id uuid PRIMARY KEY,
    device_id uuid NOT NULL,
    owner_email varchar(150) NOT NULL,
    codigo_carpeta varchar(20) NOT NULL UNIQUE,
    base_version char(64) NOT NULL,
    pdf_sha256 char(64) NOT NULL UNIQUE,
    expediente_id integer NOT NULL REFERENCES unidad_documental(id)
);
GRANT SELECT, INSERT ON offline_sync_operation TO geology_runtime;
