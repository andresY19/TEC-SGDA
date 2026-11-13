# Política de sesiones y reversión

1. Acordar cierre general y nuevo ingreso. El procedimiento no depende de contar ni migrar los pases originales, cuyo inventario es indeterminado.
2. Generar credenciales PostgreSQL y Redis y una llave de firma nuevas para el destino. Las credenciales usadas en certificación quedan excluidas del cambio real.
3. Preparar Redis privado autenticado con ACL por función, AOF, volumen propio y comprobación de durabilidad. AUTH_REDIS_URL debe apuntar al usuario de sesiones y a su espacio de claves, separado del broker y los resultados Celery.
4. Activar conjuntamente la configuración nueva, la llave nueva y un registro de sesiones limpio. Validar que los pases anteriores son rechazados, que el custodio puede ingresar y que logout, cambio de contraseña y desactivación revocan sesiones.
5. Verificar que el reinicio conserva las revocaciones y que una indisponibilidad de Redis produce un rechazo seguro. Suspender la reapertura si el registro persistente o el acceso administrativo falla.
6. Si se revierte a GEOLOGY anterior o se recupera Redis antiguo, usar otra llave de firma y un Redis limpio. Probar explícitamente que los pases previos y revocados siguen rechazados antes de permitir nuevos ingresos.

La versión anterior carece de revocación individual. La rotación global mitigó la reactivación durante el ensayo 14E. Una reversión prolongada exige controlar esa limitación en la operación y mantener registro de la decisión. La política no autoriza rotar las llaves originales en 14F.
