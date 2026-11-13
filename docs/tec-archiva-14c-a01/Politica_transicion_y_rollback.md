# Política de transición de sesiones

## Preparación para el cambio real

1. Acordar la ventana y confirmar acceso administrativo o un procedimiento de recuperación custodiado. Informar que todas las personas deberán volver a ingresar. El sistema original no proporciona un inventario fiable de pases activos.
2. Preparar Redis privado, con autenticación ACL, AOF en un volumen persistente y comprobación de WAITAOF. Fijar el perfil ACL ensayado para la versión exacta de Redis. Usar usuarios distintos para broker, resultados y sesiones, con sus claves y canales delimitados. Proteger secretos y validar arranque y recarga de AOF en el ensayo de promoción.
3. Disponer de un registro de sesiones limpio. Preparar una llave de firma nueva e independiente mediante configuración protegida. No reutilizar ni copiar los pases o el registro anterior. Los roles de prueba y la base 3 solo existen en la certificación.

## Durante la ventana

1. Cerrar el ingreso y drenar la cola según el plan 14B. Confirmar respaldo completo y restaurable.
2. Activar juntos el AUTH_REDIS_URL nuevo y la llave nueva en la configuración aprobada. Antes de reabrir, confirmar acceso administrativo y login sintético, rechazo de un pase anterior, logout, revocación y funcionamiento de Celery. Ante un fallo de persistencia o respuestas 503, mantener la ventana cerrada.
3. Registrar estados y conteos agregados. Mantener fuera del informe pases, contraseñas y URLs completas.

## Reversión

Conservar las evidencias, AOF y volúmenes. Si se restaura un Redis anterior o se vuelve a código sin revocación, usar otra llave de firma antes de reabrir y exigir un nuevo ingreso. Verificar explícitamente que los pases previos y los revocados sigan rechazados. Una restauración que recupere generaciones o sesiones antiguas requiere invalidación global.

El cambio real sigue pendiente. El cierre de esta prueba no resuelve la cobertura del respaldo ni los demás bloqueos de 14B.
