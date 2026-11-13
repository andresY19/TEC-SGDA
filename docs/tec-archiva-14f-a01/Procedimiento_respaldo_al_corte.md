# Procedimiento del respaldo al corte

Estado PREPARADO, SIN EJECUTAR. El respaldo de 14E es una referencia previa. El respaldo al corte deberá realizarse inmediatamente antes de la actualización expresamente autorizada.

## Preparación de la ventana

Confirmar los cuatro IDs originales en el inventario de 14F y sus digests, redes y montajes. Excluir el auxiliar cf8d1b36802853f87747b0efb92e25a943bfb88727e8d7b8155827b9491ffeb5. Obtener aprobación de ventana y recuperación administrativa. Medir tamaño actual de PostgreSQL, Redis, depósito, expedidos, datos, código montado y configuraciones. La reserva debe cubrir captura física, recuperación de copia, dump lógico, segunda restauración y evidencias, con margen para WAL y crecimiento medido. Si falta capacidad, suspender.

Crear un directorio nuevo en C:\Users\andre\TEC_ARCHIVA_Cutover\<ventana> y restringirlo al operador y SYSTEM con ACL protegida. Mantener los secretos en ese almacenamiento. El destino debe estar fuera de los volúmenes de origen. No reutilizar un directorio anterior ni sobrescribir archivos.

## Captura cuando el original esté detenido

1. Confirmar que ninguno de los volúmenes originales está montado en un contenedor activo. Registrar docker inspect de los cuatro IDs en almacenamiento protegido y producir un inventario saneado. Verificar que no haya procesos que escriban sobre depósito, expedidos y datos.
2. Para cada volumen pgdata y redisdata, ejecutar un contenedor auxiliar con ID e imagen comprobados, etiquetas propias de respaldo, --network none, --read-only y --mount type=volume,src=<volumen-original>,dst=/capture,readonly,volume-nocopy. Ejecutar tar -C /capture -cpf - . y capturar stdout como bytes con subprocess de Python. Usar stderr separado y exigir código 0. No canalizar el archivo binario a través de salida textual de PowerShell.
3. Capturar depósito, expedidos, datos, configuraciones y código montado en archivos nuevos. Preservar las rutas relativas, metadatos necesarios y ACL de los archivos del host. Rechazar rutas que salgan del origen, enlaces y reparse points sin revisar. Guardar los secretos de configuración en un paquete privado separado.
4. Calcular SHA-256, tamaño y rutas relativas del origen y del contenido archivado. Volver a medir el origen al terminar. Exigir coincidencia, conservar los originales y registrar el inventario de volúmenes, redes y digests.

## Verificación obligatoria en copia

5. Crear recursos nuevos con nombres únicos. Restaurar el tar de PostgreSQL sobre un volumen nuevo usando la misma versión exacta. Iniciar únicamente esa copia con --network none y sin puertos. Verificar recuperación WAL y estado disponible. Una copia física por sí sola no se considera respaldo lógico certificado.
6. Sobre la copia recuperada ejecutar pg_dump -Fc --no-owner --no-acl con el rol de respaldo autorizado. Verificar pg_restore -l y las tablas catalogadas. Registrar la versión y el hash del dump.
7. Crear otro PostgreSQL aislado y restaurar con pg_restore --exit-on-error --single-transaction --no-owner --no-acl. Comparar tablas, columnas, restricciones, índices, secuencias, conteos y huellas de filas con la primera copia. Verificar la cuenta histórica por metadatos y huella, sin publicar datos de autenticación.
8. Extraer depósito, expedidos y datos a destinos nuevos. Verificar cada hash, hojas auxiliares legibles y correspondencia SQL de originales, partes, derivados y diarios. Revisar diferencias respecto de los conteos actuales. Los números 27/26/9 y 17/43/3 son referencias históricas, no criterios que deban imponerse al estado al corte.
9. Probar la recuperación AOF de Redis únicamente sobre otra copia aislada. Mantenerla fuera de la transición de sesiones. El despliegue nuevo usa registro limpio y credenciales nuevas.
10. Revalidar IDs y estado del original. Entregar manifiesto saneado, catálogo, hashes, resultados de restauración, control de diferencias y ubicación protegida. Una diferencia sin explicación, error de restauración o pérdida de acceso impide continuar.

## Si el destino cambia antes de la ventana

Replanificar una parada coherente aprobada, drenaje de colas y congelación de escrituras antes de capturar. No aplicar el método de volumen detenido a una base que esté escribiendo. El preflight final debe confirmar la vigencia temporal del respaldo inmediatamente antes del cambio.
