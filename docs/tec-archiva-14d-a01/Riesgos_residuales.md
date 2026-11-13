# Riesgos residuales

- Los servicios originales estaban detenidos antes del ensayo. La comprobación de integridad de esta fase compara su identidad, estado, imágenes, montajes y los respaldos protegidos. La consulta directa del estado actual de la base y los archivos desde los servicios originales queda pendiente de una intervención autorizada.
- PostgreSQL requiere privilegio UPDATE sobre alguna columna para SELECT FOR UPDATE. El rol puede modificar técnicamente `inventario_origen.codigo_carpeta`. Se concedió únicamente esa columna para los bloqueos de cargue y conciliación. Verificar los casos de uso del inventario antes de promover la política. [Privilegios PostgreSQL 15](https://www.postgresql.org/docs/15/ddl-priv.html)
- Las tablas con escrituras autorizadas conservan sus permisos para los flujos conocidos, incluidos contratos, cronograma y disposición. La regresión general no cubre cada operación institucional ni todas las variaciones de datos históricos.
- AOF debe acompañarse de respaldo y política de rotación de la llave de firma. Un rollback que recupere sesiones desde Redis antiguo o restaure código sin revocación requiere rotar esa llave antes de aceptar tráfico.
- Los volúmenes Linux sintéticos validan UID/GID y modos. Antes de transferir datos existentes hay que comprobar permisos efectivos de los montajes de Windows del destino con una copia verificable.
- La lectura IA y la validación archivística institucional quedan fuera de este ensayo. El uso de navegador automatizado tampoco certifica WCAG 2.2 AA integral.
