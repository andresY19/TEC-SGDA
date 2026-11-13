# TEC-SGDEA · Piloto local de escritorio y sincronización

La web conserva el frontend y la hoja de estilo Institucional Moderno de rc.3. El overlay cambia la marca visible y añade un router FastAPI. Se conserva el identificador técnico GEOLOGY y se reutilizan el cargue, el diario de recuperación, PostgreSQL, Redis y Celery. La mesa de trabajo de Windows usa los colores de ese diseño y controles nativos de Tk.

El piloto está disponible en http://127.0.0.1:18098/app con sus propios volúmenes y una restauración verificada del respaldo local. La instalación de desarrollo anterior continúa en su puerto. Los expedientes de prueba están identificados como sintéticos. La ruta offline exige el rol administradora, activación explícita de desarrollo y autenticación vigente en cada llamada. Las carpetas para crear expedientes deben existir previamente en el inventario. El borrador puede tener un PDF de hasta 16 MiB. Las aprobaciones quedan fuera del protocolo.

## Ejecución Windows

Ejecutar TEC-SGDEA-Setup.exe para instalar en el perfil del usuario o abrir el ejecutable portátil TEC-SGDEA.exe. También se puede ejecutar python desktop/tec_sgdea.py. Usar las credenciales privadas del piloto. La caché reside en %LOCALAPPDATA%/TEC-SGDEA/workspace.sqlite3. La habilitación offline dura 24 horas. Desbloquear con la contraseña usada en la última habilitación y volver a iniciar sesión al reconectar. Las sesiones HTTP residen en memoria.

SQLite contiene blobs protegidos mediante DPAPI del usuario Windows, incluidos PDF, metadatos y cola. Los identificadores técnicos de ranura quedan visibles. La protección depende de la cuenta Windows y no constituye cifrado integral de SQLite. La exportación explícita de un PDF crea un archivo legible en la ruta elegida. La revocación del servidor se comprueba al reconectar. Durante la desconexión se aplica la ventana de habilitación local.

## Implementación y ensayos

Generar el overlay con python build_overlay.py <raiz-rc3/codigo> <contexto-temporal>. Copiar backend/offline_sync.py a geology/rutas/offline_sync.py dentro del contexto. Construir una imagen derivada de FastAPI rc.3 que copie geology a /srv/geology/geology. En la base aislada ejecutar backend/bootstrap.sql con el propietario SQL y configurar GEOLOGY_OFFLINE_DEV=1. El worker certificado conserva sus tareas e imagen. Los servicios SQL y Redis permanecen en la red interna.

Ejecutar tests/e2e_windows.py con la ruta protegida del piloto como argumento. El ensayo detiene y reanuda exclusivamente la web del piloto, crea inventario sintético y deja sus registros para inspección. tests/security_pilot.py comprueba controles HTTP y tests/web_lookup.mjs consulta el resultado en la web mediante Chromium.

El UUID, dispositivo, propietario, versión y SHA-256 identifican el intento. El recibo se inserta en la misma transacción SQL que las filas del cargue. Ante una respuesta perdida, el mismo UUID recupera el recibo. Los conflictos se conservan en la cola y requieren revisión humana. La descarga coteja el SHA-256 en servidor y cliente. La sincronización vuelve a consultar el inventario y permite descargar su versión actual. El piloto abarca altas y descargas, con versiones para detectar cambios concurrentes.

## Evaluación de Tauri 2

Tauri puede reutilizar HTML, CSS y JavaScript mediante WebView2, conservando las operaciones offline en una capa nativa. En Windows requiere Rust y las herramientas C++ de Microsoft. SQLCipher es una opción para cifrar toda la base SQLite. Esta máquina carece del entorno Rust, por lo que el ejecutable entregado usa Python/Tk y DPAPI. La web reutiliza directamente el frontend de rc.3 y el cliente nativo reutiliza su paleta, no sus vistas HTML.

- [Requisitos de Tauri 2](https://v2.tauri.app/start/prerequisites/)
- [Diseño de SQLCipher](https://www.zetetic.net/sqlcipher/design/)
