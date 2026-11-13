# Preparación de release candidate TEC-ARCHIVA 2.13.0-rc.1

Estado **READY**. Candidata independiente geology-auto11e-a11y14a-full-66ad0b80, disponible en http://127.0.0.1:18096/app. Se ejecutaron las mismas imágenes de 13G desde un proyecto nuevo y volúmenes propios. El release identifica los binarios existentes y no cambia la versión declarada por la aplicación.

## Reproducibilidad

FastAPI y Celery arrancaron como UID/GID 10001, con raíz de solo lectura, sin montajes del host y con el manifiesto de código verificado. La prueba con una base PostgreSQL vacía mantuvo el catálogo en cero objetos antes y después del arranque. Se registraron 0 sentencias DDL durante el arranque. Se verificaron 71 dependencias fijadas en ambas imágenes y Redis con AOF. El esquema normalizado del original coincidió exactamente con el esquema de certificación.

## Regresión y resguardo

- 783 pruebas aprobadas, 0 fallidas, cero omitidas y 0 bloqueadas de 783. Conteo de esta ejecución, con cero pruebas históricas contabilizadas. Un primer intento de conciliación se detuvo por una referencia al código ausente en el arnés. Se corrigió el dato del arnés, se repitió el bloque completo y se conservó el registro inicial.
- Seguridad, flujo documental, conciliación, PDF/A-1b y PDF/A-2b evaluados con datos sintéticos.
- Original antes y después coincidente. 27 tablas, 26 registros y 17 hashes de archivos sintéticos coincidentes con 9E. Se verificó la identidad, el inicio y los montajes de 208 contenedores preexistentes.
- Axe-core: 40 análisis, 0 infracciones y 7 resultados para revisión manual. WCAG 2.2 AA sigue sin certificar.

## Evidencias

- [Manifiesto de release](Manifiesto_release.json)
- [Reproducibilidad](reproducibilidad14a.json)
- [Resultados](resultado14a.json)
- [Limitaciones](Limitaciones.md)
- [Actualización y reversión](Actualizacion_y_rollback.md)

El original conserva su configuración y sus imágenes. La actualización sigue pendiente de aprobación.
