# Plan de actualización y reversión

Estado NO_GO. Ventana por acordar después del cierre de los bloqueos. El propietario del sistema aprueba la ventana, el criterio de reapertura y la reversión. El operador Docker ejecuta la intervención; el responsable de PostgreSQL verifica el respaldo, el catálogo y los privilegios. El custodio del acceso verifica la recuperación administrativa.

## Antes de aprobar la ventana

1. Ensayar una variante separada de Compose con los identificadores completos del manifiesto RC. Configurar FastAPI en localhost y mantener PostgreSQL y Redis internos. Preparar un rol de operación PostgreSQL con los privilegios de datos y secuencias que requieren las rutas, sin propiedad del esquema, superusuario ni DDL. Verificar la variante con datos sintéticos, UID/GID 10001, raíz de solo lectura, sin montajes de código y con los montajes de almacenamiento autorizados.
2. Preparar Redis autenticado con AOF. Separar broker, resultados y sesiones en bases lógicas distintas y usar cola exclusiva. Replicar la política de durabilidad ensayada en la RC o certificar la alternativa con WAITAOF y reinicio. Mantener IA y lectura automática deshabilitadas y conservar el perfil operativo PDF/A-1b.
3. Confirmar con el custodio acceso administrativo o el procedimiento autorizado de restablecimiento. Probarlo con una cuenta sintética en el ensayo. Preparar una llave de firma independiente, registro de sesiones vacío y comunicación de nuevo ingreso. Guardar secretos fuera de artefactos y logs.

## Secuencia en la ventana aprobada

1. Suspender nuevos ingresos y escrituras por el mecanismo aprobado. Drenar el trabajador y repetir las comprobaciones de pendientes, entregas sin confirmar y operaciones inciertas. Registrar los cuatro IDs, imágenes, redes, volúmenes, parámetros no sensibles y huellas.
2. Respaldar PostgreSQL, depósito, expedidos, datos auxiliares autorizados y diarios. Proteger una copia fuera de D:. Verificar catálogo, rutas, SHA-256 y restauración aislada con consistencia SQL y documental. Confirmar que el respaldo representa la línea base al corte.
3. Validar esquema y permisos de los nuevos servicios sobre la configuración preparada. Mantener preservados los contenedores e imágenes anteriores, junto con sus parámetros y volúmenes. Instalar la nueva configuración de autenticación y activar la llave nueva durante el cambio. Evitar usar el registro de sesiones anterior para la RC.
4. Con PostgreSQL y Redis saludables, activar FastAPI y después Celery según la variante aprobada. Confirmar los IDs de imagen, el estado HTTP, el puerto local y la ausencia de DDL registrado. Verificar conteos, restricciones, referencias, hashes y diarios.
5. Probar con credenciales custodiadas el acceso administrativo, el rechazo de pases anteriores, la revocación y los roles. Comprobar consulta restringida, cola, PDF/A y conciliación con datos sintéticos autorizados. Registrar evidencia sin credenciales. Reabrir únicamente tras el visto bueno del propietario.

Suspender si la cola no drena, el respaldo no corresponde al corte, falla el acceso administrativo, difiere el catálogo, aparecen archivos o referencias inconsistentes, el UID carece de permisos o las sesiones no se invalidan como se esperaba.

## Reversión segura

1. Suspender escrituras y registrar tareas y operaciones posteriores al cambio. Preservar las imágenes y configuraciones de ambas versiones, todos los documentos y diarios.
2. Volver a los identificadores y configuración anteriores solo tras comprobar compatibilidad e integridad. Antes de volver a abrir, generar una llave de firma distinta de la original y de la RC si se retorna a código sin revocación o a un Redis anterior. Forzar nuevo ingreso. Mantener aisladas las tareas generadas por la versión revertida.
3. Si se necesita restauración, solicitar aprobación separada y conciliar las escrituras posteriores. Restaurar primero en un entorno independiente y comparar catálogo, referencias y hashes. Reabrir tras verificar salud, datos, sesiones y cola.
