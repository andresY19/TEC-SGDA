# Configuración operativa de referencia

Esta configuración describe el entorno sintético 14D para TEC-ARCHIVA 2.13.0-rc.1. Los valores secretos se generaron de nuevo para el ensayo y permanecen en archivos privados fuera del repositorio.

| Configuración | Finalidad y valor de referencia |
|---|---|
| `DATABASE_URL` | PostgreSQL 15 por red interna, usuario `geology_runtime`, base sintética y host `pg:5432`. URL con contraseña codificada, suministrada desde configuración protegida. |
| `CELERY_BROKER_URL` | Redis interno autenticado, usuario de broker, base lógica 0. |
| `CELERY_RESULT_BACKEND` | Redis interno autenticado, usuario de resultados, base lógica 1. |
| `AUTH_REDIS_URL` | Redis interno autenticado, usuario de sesiones, base lógica 2. |
| `GEOLOGY_CLAVE` | Llave de firma independiente, generada localmente y separada de las claves de PostgreSQL y Redis. |
| `GEOLOGY_HORAS_SESION` | Duración de sesión. Conservar la política aprobada en el destino. |
| `GEOLOGY_COLA` | Cola exclusiva del entorno. El valor del ensayo es el nombre del proyecto seguido de -tasks. |
| `GEOLOGY_LOCAL_PROJECT` | Identificador de aislamiento y comprobación del entorno sintético. |
| `PDFA_PERFIL` | Mantener el valor operativo del destino. La certificación explícita cubre 1b y 2b. |
| Claves de proveedores | Vacías. Con LEVANTAR_AL_CARGAR=no, la lectura automática y los proveedores externos permanecen deshabilitados. |

El puerto de pruebas se publicó en 127.0.0.1:18081 exclusivamente. PostgreSQL y Redis quedaron en la red interna sin publicar puertos. Redis usa ACL con usuario por función, usuario por defecto deshabilitado y AOF con appendfsync always en volumen propio. Las bases lógicas no son un aislamiento de seguridad por sí solas. La separación de comandos y patrones de claves se aplica mediante ACL.

FastAPI y Celery usan imágenes autónomas, UID/GID 10001:10001, raíz de solo lectura, todas las capacidades eliminadas y `no-new-privileges`. Depósito y expedidos usan volúmenes propios. Las hojas auxiliares se montan en solo lectura y los temporales residen en tmpfs. El directorio `/cert`, los usuarios de auditoría Redis y el rol de fixtures pertenecen al arnés aislado y deben excluirse del despliegue normal.


