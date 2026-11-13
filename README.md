# TEC-SGDEA

Código fuente de la aplicación web, el cliente Windows y la configuración de despliegue de demostración.

- [Base web y FastAPI](distribution/tec-archiva-2.13.0-rc.3-14h/codigo), con las pruebas de la distribución.
- [Cliente Windows y API de sincronización](distribution/tec-sgdea-offline-dev), con SQLite, DPAPI y pruebas.
- [Despliegue de demostración](distribution/tec-sgdea-hostinger-demo), con Compose y renovación TLS.

La web TEC-SGDEA parte de la distribución rc.3. Para preparar su código, copie el directorio base a un contexto de trabajo y ejecute `build_overlay.py <base> <contexto>`. Ejecute `backend/patch_sheet.py <contexto>/geology/rutas/unidades.py` sobre esa copia limpia y copie `backend/offline_sync.py` a `<contexto>/geology/rutas/offline_sync.py`. Los scripts SQL de sincronización están en `backend/`.

El Compose de demostración requiere imágenes verificadas, configuración privada y una base exclusiva. El repositorio contiene el código y las plantillas de despliegue.
