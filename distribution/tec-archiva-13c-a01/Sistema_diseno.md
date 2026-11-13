# TEC-ARCHIVA · Sistema de diseño 13B

La hoja tec-archiva.css define los tokens y las reglas de presentación. Se carga después de los estilos históricos. Los tokens compatibles del frontend anterior apuntan a la nueva paleta. Los módulos de interfaz mantienen HTML, CSS y JavaScript.

| Token | Valor | Uso |
|---|---|---|
| ta-violet | #6257DC | Identidad y acentos |
| ta-indigo | #4848B6 | Acciones primarias, selección y cifras |
| ta-blue | #29577E | Degradados institucionales y acentos |
| ta-white | #FFFFFF | Superficies y texto sobre fondo institucional |
| ta-ink | #172033 | Texto y títulos |
| ta-canvas, ta-soft, ta-line | Derivados de la paleta | Fondo, selección y divisores |
| ta-font, ta-s1…ta-s6 | Segoe UI y escala de 4 a 32 px | Tipografía y ritmo |
| ta-radius, ta-radius-lg, ta-shadow | Radios de 12 y 20 px y sombra suave | Paneles y superficies |

| Componente | Implementación |
|---|---|
| Botones, entradas y selectores | btn, btn2 y controles nativos con etiquetas |
| Tablas | tenv para desplazamiento local, títulos y encabezados asociados |
| Tarjetas, badges y estados | caja, metro, ficha, pill y ta-metric |
| Modal, alertas y notificaciones | modalCuerpo, aviso y panelAlertas con la interacción de 12I |
| Navegación y perfil | ta-sidebar, ta-topbar, ta-crumbs y menú plegable |
| Carga y vacío | ta-skeleton, aria-busy, ta-status y ta-empty |

## Fuentes del dashboard

| Panel | Endpoint existente | Campo o alcance |
|---|---|---|
| Expedientes registrados | GET /unidades/resumen | total |
| Expedientes por estado | GET /unidades/resumen | estados |
| En procesamiento | GET /unidades/resumen | Estado En procesamiento |
| Archivos digitalizados | GET /cargue/estado-de-cargas | resumen.archivos_cargados. Las partes son archivos registrados |
| Actividad reciente | GET /cargue/estado-de-cargas | detalle con fecha de carga, orden descendente |
| Hojas por revisar | GET /unidades/ahora | en_vuelo.hojas_por_revisar |
| Alertas | GET /vigilancia/alertas | Alertas sin leer de la sesión |
| Accesos rápidos | Identidad autenticada | Intersección con pestanas y vistas existentes |

Los indicadores describen registros operativos. La cifra de producción contractual certificada requiere su propia validación. Una consulta fallida deja el indicador como dato no disponible.

El menú utiliza botones existentes y presenta solo las pestañas de la identidad. La ficha de lectura mantiene el acceso desde Localización y desde En cola para los perfiles habilitados. El menú compacto se abre con Enter o Espacio y devuelve el foco al disparador al cerrar con Escape.
