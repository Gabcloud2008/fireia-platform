# Fixtures sintéticas — aviso

Todos los archivos de este directorio son 100% sintéticos. Los escribimos a mano para probar el pipeline (Fase 1A): no provienen de satélites, no representan detecciones reales y no sirven como datos de investigación.

Las coordenadas caen dentro del bounding box de Paraguay (o cerca, para probar los controles), los FRP son números plausibles inventados y las fechas son arbitrarias.

| Archivo | Contenido |
|---|---|
| `synthetic_modis_nrt.csv` | 12 filas formato MODIS (2 con flags soft: fuera de área, FRP alto) |
| `synthetic_viirs_noaa20_nrt.csv` | 8 filas formato VIIRS, código de satélite sin mapear |
| `synthetic_viirs_snpp_nrt.csv` | 5 filas formato VIIRS, código `N` (S-NPP) |
| `synthetic_empty.csv` | Solo encabezado VIIRS (respuesta vacía válida) |
| `synthetic_invalid_rows.csv` | 8 filas MODIS con un error hard por fila (cuarentena) |
| `synthetic_wrong_columns.csv` | Encabezado inválido (error de parseo a nivel archivo) |
| `synthetic_missing_coords.csv` | 4 filas MODIS: 1 válida + 3 con coordenadas ausentes (missing_latitude/missing_longitude) |
| `synthetic_all_quarantined.csv` | 3 filas MODIS válidas como CSV pero con FRP negativo (estado success_all_quarantined) |
| `synthetic_html_response.html` | Cuerpo HTML simulando mantenimiento del proveedor (parse_failed/html_body) |
| `synthetic_json_response.json` | Cuerpo JSON inesperado en un endpoint CSV (parse_failed/json_body) |
