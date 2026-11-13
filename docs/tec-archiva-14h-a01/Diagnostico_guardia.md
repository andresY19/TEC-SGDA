# Diagnóstico del guardia anterior

La rc.2 decidía por GEOLOGY_LOCAL_PROJECT, --local-project y GEOLOGY_ENTORNO. Sin confirmación, aceptaba el prefijo geology-auto11e-. Con confirmación, exigía coincidencia del texto y rechazaba explícitamente geology-local-20261106-57a99a. También exigía LEVANTAR_AL_CARGAR=no.

Ese guardia no consultaba al motor Docker. No verificaba IDs completos de contenedor, volúmenes, redes, cluster PostgreSQL, inodos de almacenamiento ni identidad del proceso. Las rutas admitidas se restringían al argumento storage-root y el módulo de dominio aplicaba comprobaciones de rutas, hashes, bloqueo y transacciones de lectura.

Eliminar solo la comparación del nombre permitiría que una confirmación textual habilitara una operación sobre recursos distintos de los imaginados por el operador. Conservarla como único criterio también impediría operar legítimamente sobre ese identificador después de una actualización autorizada. Cambiar GEOLOGY_LOCAL_PROJECT alteraba la decisión aunque no cambiara los recursos reales.

La rc.3 elimina la autorización implícita por nombre. --local-project queda como contexto informativo. La CLI exige un permiso firmado, la comprobación externa de los recursos y una atestación ligada a su proceso. El ambiente original mantiene su protección mediante sus IDs reales y la ausencia de una política y autorización operativas provisionadas para él.

Las barreras del dominio se conservan: validación de rutas y hashes, exclusión concurrente, recibos inmutables, conservación de archivos y rollback de las transacciones de lectura. El código de conciliación archivística no se modificó.
