# TEC-ARCHIVA 2.13.0-rc.1 · Certificación operativa 14D

La certificación utilizó el proyecto sintético `geology-auto11e-a11y14d-full-6f10a8df`, PostgreSQL y Redis exclusivos, red backend interna, red frontend exclusiva para las pruebas HTTP en loopback y volúmenes propios. Se verificaron 166 hashes de la RC, los identificadores de las imágenes, las evidencias de 14C y los hashes de los respaldos protegidos fuera de D:. El preflight midió aproximadamente 180,7 GiB libres en C:, 15,2 GiB en D: y 24,0 GiB en F:.

## Resultados

- PostgreSQL concedió permisos por tabla y USAGE sobre las secuencias justificadas. FastAPI y Celery se conectaron como `geology_runtime`, sin pertenencia al rol administrador, sin propiedad del esquema y sin facultades de elevación. Las 13 operaciones prohibidas devolvieron SQLSTATE 42501. También se verificó la prohibición de conexión a `postgres` y `template1` y se ejercitaron las escrituras autorizadas con rollback.
- FastAPI y Celery se ejecutaron con UID/GID 10001:10001, raíz de solo lectura, capacidades efectivas vacías y `no-new-privileges`. `/estado`, `/app` y `/openapi.json` devolvieron 200. El worker procesó ping, digitalización y PDF/A-1b y 2b. Después del reinicio coincidieron el catálogo, los datos y las huellas de los archivos del ensayo. No se detectó DDL de arranque.
- Redis rechazó conexiones sin autenticar. Las conexiones de broker, resultados y sesiones usaron ACL y bases lógicas separadas. El reinicio conservó resultados y revocaciones. Con Redis indisponible, la autenticación falló de forma cerrada.
- Se comprobó escritura en depósito, expedidos y temporales, lectura de hojas auxiliares y rechazo de escritura sobre la raíz, `/etc` y el volumen auxiliar de solo lectura. Se verificaron referencias SQL y huellas de originales o partes, derivados e informes XML. veraPDF confirmó ambos perfiles.
- La regresión funcional incluyó inicio de sesión, administración, dashboard, inventario, expedientes, cargue, duplicados, división, revisión humana, consulta restringida, reportes, conciliación y rollback. Las operaciones con commit incierto conservaron los archivos y el diario.

## Regresión

Se ejecutaron 783 de 783 pruebas de referencia, con 783 aprobadas, 0 fallidas, 0 omitidas y 0 bloqueadas. Se aprobaron además 21 controles de SQL y almacenamiento, para 804 aprobaciones. No se contabilizaron evidencias históricas.

Durante la preparación se corrigió el descubrimiento de secuencias en tablas cuya clave no se llama `id` y se creó la hoja sintética auxiliar en el volumen propio. En el primer pase operativo, una comprobación del TTL usó un usuario Redis sin permiso de auditoría. Se repitió esa comprobación con un usuario de solo lectura y pasó. Los servicios conservaron sus ACL operativas.

## Integridad del original y decisión

Los cuatro IDs originales conservaron sus imágenes, montajes, puertos, códigos de salida y marcas de tiempo. Ya estaban detenidos al inicio y permanecieron detenidos. Un contenedor auxiliar de 14D heredó de la imagen de certificación las etiquetas del proyecto original. Se identificó por ID, quedó detenido y solo montó el volumen sintético de hojas auxiliares, con red deshabilitada. Queda registrado para una limpieza futura autorizada.

**NO_GO para actualizar.** La fase certifica la configuración aislada. La comprobación sobre una copia restaurada del estado actual del destino, la transición de sesiones y el ensayo de rollback quedan sujetos a aprobación de 14E.

