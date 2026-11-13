# Actualización local y reversión de TEC-ARCHIVA 2.13.0-rc.1

Procedimiento pendiente de autorización. La ventana se aplica exclusivamente al proyecto local geology-local-20261106-57a99a.

## Preparación y respaldo

1. Registrar identificadores de imágenes vigentes, puertos, redes, volumen PostgreSQL, almacenamiento Redis y montajes documentales. Registrar rutas de datos autorizadas y configuración efectiva sin imprimir secretos.
2. Confirmar espacio, cerrar el ingreso a escrituras y esperar que terminen tareas y transacciones. Registrar operaciones pendientes, conciliaciones y diarios. Las tareas ajenas permanecen fuera de la ventana.
3. Crear un respaldo nuevo de PostgreSQL, del depósito, de expedidos y de los diarios. Conservar copia protegida fuera del disco operativo. Verificar SHA-256, catálogo PostgreSQL y restauración aislada. Capturar referencias SQL y hashes antes del cambio.
4. Comparar el catálogo del destino con la huella del manifiesto. 14A verificó igualdad de tablas, columnas, restricciones e índices mediante el esquema normalizado. Si aparece una diferencia, suspender la promoción y evaluar su causa. La RC carece de migraciones para el original.

## Configuración y promoción

5. Preparar una variante local aparte del Compose original. Fijar los identificadores de FastAPI y Celery, verificar UID/GID 10001, raíz de solo lectura y ausencia de montajes de código. Validar acceso de lectura y escritura al depósito y expedidos con los permisos mínimos. Mantener PostgreSQL y Redis internos y FastAPI en 127.0.0.1. Conservar imágenes, configuraciones y volúmenes previos.
6. Usar un rol PostgreSQL de operación sin DDL. Preparar Redis autenticado con AOF habilitado. Asignar bases lógicas distintas a broker, resultados y sesiones, con una cola exclusiva de proyecto. Verificar conectividad interna y persistencia AOF con un reinicio en un ensayo aislado. Mantener proveedores IA y lectura automática deshabilitados. Confirmar el perfil PDF/A operativo por separado.
7. Invalidar las sesiones anteriores durante la ventana mediante una llave de firma nueva y un registro de sesiones limpio e independiente. No vaciar Redis ni reutilizar una base que contenga tareas. Retirar la llave antigua de la configuración activa y conservar los secretos según la política local. Informar a los usuarios que deben volver a ingresar.
8. Durante la ventana aprobada, activar primero PostgreSQL y Redis, luego FastAPI y Celery. Validar salud, código incorporado y ausencia de DDL. Verificar esquema, conteos, referencias y hashes contra la línea base. Usar usuarios y documentos sintéticos autorizados para login, revocación, permisos, consulta, Celery, PDF/A y conciliación. Reabrir solo después de comprobar el estado de colas, sesiones y documentos.

## Reversión

1. Ante fallo de arranque, diferencias de esquema, integridad o revocación, suspender escrituras. Registrar las operaciones nuevas y esperar o aislar las tareas en curso. Preservar documentos, versiones, manifiestos y diarios.
2. Restablecer imágenes y configuración anterior con los mismos datos si el catálogo y la integridad lo permiten. Si el retorno usa código sin revocación o Redis restaurado, generar otra llave de firma antes de habilitar el acceso y forzar nuevo ingreso. Mantener las tareas de la versión revertida aisladas hasta su conciliación.
3. Una restauración del respaldo requiere autorización y evaluación de las escrituras posteriores. Ensayarla fuera del ambiente activo y reconciliar archivos y registros antes de restaurar o reabrir.
4. Verificar salud, sesiones, roles, conteos, hashes, documentos y colas. Documentar el resultado y reabrir solo con autorización.
