# TEC-ARCHIVA 13E

Candidata aislada en http://127.0.0.1:18093/app. Proyecto geology-auto11e-a11y13e-full-789554db. FastAPI y Celery se ejecutan como 10001:10001 con código incorporado y raíz de solo lectura.

- **Administración.** Directorio con búsqueda, filtros por rol y estado, paginación local, formulario validado y confirmación para activar o desactivar. Se conservan la administración y auditoría disponibles. La interfaz impide activar una excepción nueva de aprobación propia y permite revocar una que ya estuviera activa. La política del servidor, incluida la excepción heredada de Administradora, conserva los contratos de 13D.
- **Reportes.** El Centro de control y Seguimiento reutilizan datos, cálculos y exportaciones existentes. Las estimaciones y conteos de actividad se presentan como informativos. El alcance visual incluye Contrato, Instrumentos, Calidad, Hojas de control y Reubicación.
- **Aislamiento.** Se verificaron hashes de 13D, el respaldo protegido y los identificadores y montajes de 190 contenedores preexistentes. PostgreSQL y Redis de certificación tienen puertos internos y volúmenes exclusivos. El alcance del cambio de código se limitó a la interfaz.

## Evidencias

Se registraron 607 pruebas aprobadas, 0 fallidas y 0 bloqueadas de 607 previstas. La regresión técnica corrió en a01 y la interfaz se comprobó en a03 con los mismos archivos Python. Tras revisar la captura móvil se ajustaron los anchos de los filtros de auditoría. La prueba final verifica el ancho efectivo de los tres controles. Dos casos de referencia fallaron en la primera repetición por el momento de medición tras redimensionar. Se conservaron los resultados iniciales y se repitieron las suites con la tabla cargada y la prueba de teclado iniciada directamente en ancho móvil. Axe-core registró 18 análisis, 0 infracciones y 4 resultados pendientes de revisión manual. NVDA, Chrome nativo y zoom real siguen pendientes. WCAG 2.2 AA permanece sin certificar.

Sin fallos registrados en las pruebas nuevas de la ejecución final.

- [Inventario de pantallas](Inventario_pantallas.md)
- [Resultados y servicios](resultado13e.json)
- [Permisos comprobados](matriz_permisos.json)
- [Identificadores de imágenes](build13e-a03.json)
- [Actualización y reversión](Actualizacion_y_rollback.md)

## Capturas

![administracion-confirmacion](administracion-confirmacion.png)
![administracion-escritorio](administracion-escritorio.png)
![administracion-movil](administracion-movil.png)
![reportes-escritorio](reportes-escritorio.png)
![reportes-movil](reportes-movil.png)
![seguimiento-escritorio](seguimiento-escritorio.png)
