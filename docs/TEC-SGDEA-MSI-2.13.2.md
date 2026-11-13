# TEC-SGDEA Desktop 2.13.2

**Actualización MSI 2.13.1 → 2.13.2 · PENDIENTE DE CERTIFICACIÓN**

**Estado operativo · Piloto funcional de desarrollo local** con backend en `http://127.0.0.1:18099`.

Se verificaron la familia de actualización de los MSI, la extracción de sus ejecutables y la apertura de ambas versiones con un perfil de prueba cuyo SQLite conservó su SHA-256. El ensayo funcional independiente verificó DPAPI, reapertura offline, SHA-256 de derivados, UUID y recibo único, conservación del borrador en conflicto y consulta web.

## Pendientes para distribución institucional

1. Ejecutar la actualización real de los MSI 2.13.1 → 2.13.2 en un entorno Windows aislado y comprobar la conservación de pendientes, PDF, UUID, recibos y conflictos. En el ensayo anterior Windows Sandbox no estaba disponible y el acceso a Hyper-V fue denegado.
2. Validar la compilación institucional y la política administrada de servidor contra un backend HTTPS de ensayo, con certificado confiable y sin fallback a localhost.
3. Firmar y verificar el paquete institucional con Authenticode. El MSI local disponible figura como `NotSigned`.

## Evidencias conservadas

- [Identidad y hashes de los paquetes](C:/Users/andre/TEC_SGDEA_Dev/upgrade-verification-2132/paquetes.json)
- [Apertura de binarios e integridad de SQLite](C:/Users/andre/TEC_SGDEA_Dev/upgrade-verification-2132/binarios.json)
- [DPAPI, SHA-256, sincronización y conflictos](C:/Users/andre/TEC_SGDEA_Dev/upgrade-verification-2132/flujo/result.json)
- [Reconexión automática del cliente](C:/Users/andre/TEC_SGDEA_Dev/desktop-login-a01/capturas/result.json)
- [Estado de firma y hashes del MSI 2.13.2](C:/Users/andre/TEC_SGDEA_Dev/desktop-login-a01/paquete.json)
- [Configuración institucional HTTPS](C:/Users/andre/TEC_SGDEA_Dev/upgrade-verification-2132/HTTPS-institucional.md)
