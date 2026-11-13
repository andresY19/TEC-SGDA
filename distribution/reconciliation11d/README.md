# Entrega fuente 11D

Módulo y pruebas certificados sobre copia aislada de 11C. No instalar sobre la distribución certificada ni ejecutar sobre recursos originales. Véase `docs/FASE_11D_CONCILIACION_DOCUMENTAL.md` en la raíz del repositorio para estados, pruebas, límites y plan de integración.

Entrada: `python /opt/geology-cert/reconcile_documents_11d.py --storage-root /cert --operation /cert/<operacion-sintetica>` solo cuando el script esté montado en esa ubicación en el proyecto aislado autorizado. El directorio debe existir y corresponder a una operación con diario. El CLI exige prefijo `geology-recon11d-` e IA deshabilitada. Salida 0: RECONCILED; salida 2: revisión humana. No reintentar automáticamente ni interpretar el recibo como autorización para eliminar o reentregar documentos.

Los archivos fuente entregados coinciden con los ejecutados; hashes en `phase11d-source-manifest.json`. No contiene credenciales. El despliegue y la automatización permanecen pendientes de aprobación.
