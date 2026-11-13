# TEC-ARCHIVA 14C

**PASS en el entorno sintético tec-archiva-14c-291a6071.** La RC de FastAPI y Celery conservó sus identificadores certificados. PostgreSQL, Redis y los volúmenes se crearon para este ensayo. Los servicios solo se conectaron a la red interna y ningún puerto se publicó. Se verificaron los hashes de la RC, de las evidencias 14B y del respaldo protegido.

Los cuatro contenedores originales se encontraron detenidos con código 255 y quedaron con los mismos identificadores, imágenes, montajes y marcas de inicio y fin. La causa de la detención queda sin determinar. El original permaneció fuera del ensayo. Las instalaciones exploratorias de 14C quedaron detenidas y con sus volúmenes conservados.

## Evidencia

- **ACL.** Usuario predeterminado deshabilitado, credenciales independientes y permisos explícitos por comando, prefijo y canal. Se rechazaron conexiones sin credenciales antes y después del reinicio y diez operaciones entre roles o de administración. Broker en DB 0, resultados en DB 1, sesiones candidatas en DB 2. DB 3 y su usuario solo simularon el registro anterior.
- **FastAPI y Celery.** La aplicación usó AUTH_REDIS_URL desde configuración privada. El trabajador registró tres tareas y ejecutó únicamente ping. Se recuperó un resultado persistido de Celery después de reiniciar Redis. No se utilizaron documentos ni cuentas reales, ni se activó IA.
- **Sesiones.** Un usuario sintético inició sesión con la llave anterior del ensayo. Tras activar una llave nueva y un registro limpio, el pase anterior devolvió 401 y el nuevo ingreso funcionó. El TTL observado fue de hasta 3600 segundos. Logout, desactivación/reactivación y cambio de contraseña invalidaron los pases correspondientes. Tras reiniciar Redis, una sesión válida sobrevivió y el pase revocado siguió rechazado.
- **Fallo seguro.** Durante la indisponibilidad de Redis, identidad protegida, login, logout y desactivación devolvieron 503. La desactivación fallida no alteró la cuenta. Tras recuperar el servicio se revalidó el acceso y se comprobó el rechazo de los pases anteriores.
- **Secretos.** Configuración generada en un directorio de acceso restringido y ACL con hashes de contraseña. La auditoría encontró cero coincidencias de pases y de los secretos generados en los logs revisados.

## Hallazgo de persistencia y ajuste

En un primer ensayo, Redis 7.4.10 confirmó las escrituras, pero al reiniciar registró NOPERM en el cliente interno de carga AOF y descartó transacciones. Una sesión que debía sobrevivir devolvió 401. La variante final mantuvo al usuario default en off y sin contraseña, y agregó permisos acotados al prefijo y a los comandos de reproducción. La autenticación de los clientes sigue requiriendo un usuario ACL nominal. El reinicio final verificó la sesión válida, la revocación y un resultado Celery persistido, con cero errores del cliente de carga AOF. [Incidencia del proyecto Redis](https://github.com/redis/redis/issues/14541) · [Documentación oficial de ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)

También se acotaron las claves internas de transporte de Celery y sus canales, incluidos los patrones literales que usa PSUBSCRIBE, tras observar denegaciones de arranque y resultados. La referencia ACL es documental y contiene marcadores. Los usuarios probe y oldauth son auxiliares del ensayo y quedan fuera del plan de promoción.

Se aprobaron 9 escenarios y 31 comprobaciones HTTP. El ensayo cubre reinicio normal con AOF y caída controlada. No certifica pérdida abrupta del host, restauración de AOF antiguo ni cargas de trabajo distintas de ping.
