# Preflight local TEC-ARCHIVA 14B

**NO_GO para promover TEC-ARCHIVA 2.13.0-rc.1.** El preflight se ejecutó en solo lectura sobre el proyecto geology-local-20261106-57a99a. Los cuatro contenedores conservan identificadores, imágenes, hora de inicio y montajes. Las verificaciones de manifiesto cubrieron 166 archivos de la RC y 108 evidencias de 14A.

## Inventario y continuidad

| Servicio | Imagen efectiva | Estado | Publicación |
|---|---|---|---|
| almacen_datos | sha256:1c0580e85dcfdbe28e5a50df25a7ae5a5849184bf5561cefd00de1d63b596a45 | Saludable | Sin puerto publicado |
| mensajeria | sha256:2a51817f79255c8b69f86a974459c2e0359aff81417d80158f2b9e541e6f4b33 | Saludable | Sin puerto publicado |
| servidor | sha256:a77f24483c87e509b9c48d34fe1a76f115ac92688c4156b7ab1d8e049f1e7a10 | Saludable | 127.0.0.1:8080 |
| procesador | sha256:a77f24483c87e509b9c48d34fe1a76f115ac92688c4156b7ab1d8e049f1e7a10 | Ejecutándose; listo según el log del trabajador | Sin puerto publicado |

PostgreSQL y Redis usan volúmenes exclusivos. La red interna reúne los cuatro servicios y la red de entrada pertenece solo al servidor. El original y la RC conservan las 155 operaciones OpenAPI originales con los mismos contratos publicados. La RC añade el cierre de sesión. La cola local registró cero pendientes, cero entregas sin confirmar y cero claves desconocidas en la muestra. Los logs mostraron tres tareas registradas y ningún identificador recibido sin resultado terminal. La muestra no reemplaza el drenaje coordinado en la ventana.

## Integridad y respaldo

- PostgreSQL 15.19 conserva 27 tablas, 26 registros, nueve trazas, 70 índices válidos y una cuenta administradora activa con hash presente. El esquema normalizado coincide con la RC y con la huella de 14A. El catálogo coincide con 10C. La configuración actual no registra todo el DDL, por lo que la evidencia verifica el estado observado y no certifica el historial de sentencias.
- Los 17 archivos certificados del depósito conservan sus hashes. Las nueve referencias SQL a archivos existen y las huellas disponibles coinciden. Expedidos y datos auxiliares se inspeccionaron por metadatos.
- Los tres archivos del respaldo protegido en C: pasan SHA-256. El archivo PostgreSQL cataloga 27 tablas y 27 entradas de datos. El ZIP pasa CRC y verifica 17 hashes. La restauración 9E fue satisfactoria. Los datos SQL actuales coinciden con la restauración histórica.
- La cobertura documental del ZIP no alcanza los 43 archivos de expedidos, que suman 265.029 bytes, ni las tres hojas auxiliares de datos, que suman 430.018 bytes. El conjunto conocido requiere un respaldo nuevo antes de promover. La capacidad libre registrada supera el tamaño de este conjunto, con 183 GiB en C: y 15,3 GiB en D:.

## Bloqueos para autorizar el cambio

1. **Redis y sesiones.** Redis 7.4.10 tiene AOF activo con fsync cada segundo y soporta WAITAOF. Acepta conexiones internas sin autenticación. AUTH_REDIS_URL está ausente y la base lógica 2 está vacía. Preparar un registro de sesiones autenticado y aislado, con durabilidad verificada, antes de promover. Los pases firmados originales carecen de inventario revocable. El total de sesiones activas de autenticación es indeterminado, aunque no hay filas de sesiones de edición. La cuenta administradora se verificó por metadatos. El operador deberá demostrar acceso o recuperación en un ensayo aislado.
2. **PostgreSQL.** El servidor y el trabajador usan el rol operativo auditado, que es superusuario y puede crear objetos. La RC se certificó con un rol de aplicación sin DDL. Preparar y verificar sus permisos sobre datos y secuencias antes de conectar la RC al original.
3. **Contenedores y almacenamiento.** El servidor y el trabajador originales ejecutan PID 1 con UID/GID 0, raíz escribible y montajes de código. La RC usa 10001:10001 y raíz de solo lectura. La comprobación sin escritura indica acceso de lectura y escritura a depósito y expedidos con 10001:10001, y lectura de datos auxiliares. Falta ensayar la configuración definitiva con almacenamiento de prueba.
4. **Cobertura de respaldo.** Consolidar y verificar en C: un respaldo del estado al corte con PostgreSQL, depósito, expedidos, datos auxiliares autorizados y diarios. Mantener el respaldo histórico y probar la restauración fuera del ambiente original.

El perfil PDF/A configurado es 1b, la lectura automática está deshabilitada y las claves de IA están vacías. La clave de firma existe y coincide entre servidor y trabajador. Su valor no se registró. Se propone usar una llave nueva al promover para invalidar pases anteriores.
