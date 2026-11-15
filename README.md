# TEC-SGDEA

Código fuente de la aplicación web, el cliente Windows y la configuración de despliegue de demostración.

- [Código web y FastAPI publicado](distribution/tec-archiva-2.13.0-rc.3-14h/codigo), con las pruebas de la distribución.
- [Cliente Windows y API de sincronización](distribution/tec-sgdea-offline-dev), con SQLite, DPAPI y pruebas.
- [Despliegue de demostración](distribution/tec-sgdea-hostinger-demo), con Compose y renovación TLS.

## Versión publicada

Este commit sincroniza el código web `2.13.0-estable-local-a01` con el manifiesto OCI publicado en Hostinger `sha256:b62b12e6c71420d725d808a7ab73e83b199f8f8ff1701742c38d0ac45777c3b2`. El manifiesto referencia la configuración de imagen local `sha256:8ce4b4c9ee169ba8a9c04502f7e8f39f0a479a3cf8998275040c152d0ce9dbc6`.

El directorio `codigo/geology` incorpora Localización, Inventarios, Excel multicarpeta, los dos indicadores P3 verificados, Reubicación y las seis rutas offline. Se puede usar directamente como fuente de la aplicación con las dependencias de `codigo/requirements.autonomous.lock`. Los scripts `build_overlay.py` y `backend/patch_sheet.py` corresponden al montaje histórico sobre una base anterior.

Para activar offline se requieren las dos tablas de recibos. Sus scripts SQL están en [backend offline](distribution/tec-sgdea-offline-dev/backend). Las pruebas `integration_stable_*.py` se ejecutan como scripts independientes contra una base PostgreSQL sintética y vacía por prueba. Crean tablas y fixtures, incluida una falla SQL controlada en Excel. Las pruebas unitarias se ejecutan desde `codigo` con `python -m unittest discover -s tests -p "test_*.py"`.

El Compose de demostración requiere imágenes verificadas, configuración privada y una base exclusiva. El repositorio contiene el código y las plantillas de despliegue.

El árbol de la raíz conserva el código GEOLOGY, la configuración Docker original y local, las pruebas y los scripts. `distribution/` incluye el código y las configuraciones de las candidatas históricas. `docs/` reúne la documentación textual. Los archivos de evidencia generados, instaladores y datos operativos permanecen en el equipo.
