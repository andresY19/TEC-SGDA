# TEC-ARCHIVA 13D

Candidata aislada en http://127.0.0.1:18092/app. Proyecto geology-auto11e-a11y13d-full-76895cf1. FastAPI y Celery se ejecutan como 10001:10001 con código incorporado y raíz de solo lectura.

- **Cargue.** Consulta opcional del inventario, selección previa, comprobación de extensiones y archivos vacíos, tamaño mostrado, confirmación explícita y resultados de la última operación e historial de hasta cinco envíos anteriores durante la sesión de página. El servidor valida contenido y duplicados. El contrato carece de un máximo uniforme de bytes para PDF. El indicador refleja solicitudes respondidas; el procesamiento técnico es asíncrono.
- **Digitalización.** Conserva filtros de Proceso, ficha con trazabilidad y visor autorizado. El detalle consulta disponibilidad de archivos registrados y copias de consulta. La API carece de un historial general de trabajos y de porcentajes de avance.
- **Revisión.** Filtros por estado y búsqueda sobre las fichas devueltas, con foco de entrada y regreso. Conserva hallazgos, observaciones, historial, validación y devolución según los permisos existentes. El código base contempla una excepción de aprobación propia para Administradora. La fase conserva esa política de 13C, y la revisión institucional de competencias sigue pendiente.
- **Aislamiento.** Se verificaron hashes de 13C, archivos del respaldo protegido e identificadores y montajes de 184 contenedores anteriores. PostgreSQL y Redis de certificación usan volúmenes exclusivos y puertos internos. El alcance de código se limitó a la interfaz.

## Evidencias

Se registraron 586 pruebas aprobadas, 0 fallidas y 0 bloqueadas de 586 previstas. La regresión técnica se ejecutó en a01. Las suites de navegador se ejecutaron sobre a05, que añade el detalle técnico y el desplazamiento local de la tabla de cargue con los mismos archivos Python. Axe-core registró 15 análisis, 0 infracciones y 4 resultados pendientes de revisión manual. El primer análisis detectó un atributo ARIA inválido en el contenedor de la ficha de revisión. Se corrigió la semántica y se repitieron las pruebas en a05. El caso del menú móvil fue intermitente al emular un cambio de ancho. La prueba espera la actualización de la vista y comprueba que el foco realmente llegue al primer botón. Se conservaron ambas evidencias. La exportación inicial del PDF sintético desde el directorio temporal se recuperó leyendo el archivo directamente en el contenedor, sin volver a insertar el expediente de prueba. Quedan pendientes NVDA, Chrome nativo y zoom real. WCAG 2.2 AA permanece sin certificar.

Sin fallos registrados en las pruebas de flujo ejecutadas.

- [Resultados y servicios](resultado13d.json)
- [Permisos comprobados](matriz_permisos.json)
- [Identificadores de imágenes](build13d-a05.json)
- [Actualización y reversión](Actualizacion_y_rollback.md)

## Capturas

![cargue-escritorio](cargue-escritorio.png)
![cargue-movil](cargue-movil.png)
![digitalizacion-detalle-escritorio](digitalizacion-detalle-escritorio.png)
![digitalizacion-escritorio](digitalizacion-escritorio.png)
![digitalizacion-movil](digitalizacion-movil.png)
![revision-escritorio](revision-escritorio.png)
![revision-ficha-escritorio](revision-ficha-escritorio.png)
![revision-movil](revision-movil.png)
