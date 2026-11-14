"""Capa geográfica nacional (Misión 004, etapa 2).

Conceptos separados a propósito (el bbox de consulta NUNCA es la frontera):

- ``firms_query_bbox``: rectángulo con el que se consulta a FIRMS (más margen).
  Incluye territorio de Argentina/Bolivia/Brasil por construcción.
- ``inside_paraguay`` (``dentro_pais``): pertenencia al polígono ADM0 oficial.
- ``outside_query_bbox``: flag de anomalía de contrato (el proveedor devolvió
  algo fuera del rectángulo pedido).
- unidades administrativas (ADM0/ADM1/ADM2) con identificadores estables y
  versión de límites; la asignación es una RELACIÓN versionada (``obs_geo``),
  jamás un atributo de la observación.
"""
