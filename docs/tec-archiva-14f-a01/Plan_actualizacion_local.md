# Plan de actualización local pendiente de autorización

1. Resolver el checklist del custodio y aprobar ventana, responsables y criterios de suspensión. Seleccionar por digest la candidata derivada 14F y conservar los digests anteriores.
2. Ejecutar el respaldo al corte según el procedimiento, verificar su restauración e integridad y confirmar el acceso administrativo custodiado.
3. Preparar credenciales nuevas, Redis con ACL y AOF, AUTH_REDIS_URL, llave de firma nueva y registro de sesiones limpio. Excluir secretos sintéticos y usuarios del arnés.
4. Aplicar en el destino aprobado el rol PostgreSQL restringido y verificar permisos por tabla, secuencias y columna de bloqueo. Separar administración del esquema y ejecución de aplicación. Confirmar que la compatibilidad no requiere DDL de arranque.
5. Verificar UID/GID 10001:10001, permisos de volúmenes, raíz de solo lectura y ausencia de montajes del código. Arrancar las imágenes autorizadas y probar salud, login, permisos, revocación, cola, hashes, PDF/A y conciliación CLI con --local-project coincidente con el proyecto local aprobado.
6. Abrir acceso únicamente tras completar las comprobaciones y el visto bueno registrado. Suspender ante datos o hashes inexplicados, DDL inesperado, dependencia de superusuario, reactivación de pases o pérdida de acceso administrativo.

UPGRADE_AUTHORIZATION=NOT_GRANTED. El procedimiento se prepara para revisión. Los ensayos de 14F permanecen aislados.
