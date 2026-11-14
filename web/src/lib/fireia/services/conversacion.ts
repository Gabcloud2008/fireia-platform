// FIREIA (M012) — Servicio conversacional del Centro de inteligencia.
// NO hay IA conectada: este adaptador local responde con REGLAS simples y
// deterministas sobre el almacén ya cargado en el navegador. Cero llamadas
// de red, cero simulación de modelo. Cuando exista una integración real,
// un adaptador remoto implementará la misma interfaz.

import type { DatosMVP } from "./almacen";

export interface ReferenciaRespuesta {
  tipo: "observaciones" | "eventos" | "calidad" | "almacen";
  etiqueta: string;
}

export interface RespuestaConversacional {
  texto: string;
  referencias: ReferenciaRespuesta[];
  tipo: "datos" | "explicacion" | "no_encontrado" | "disponibilidad";
}

export interface ConversacionService {
  /**
   * Responde una consulta del usuario usando únicamente el almacén
   * cargado y un conjunto fijo de reglas locales.
   */
  responder(consulta: string, datos: DatosMVP): RespuestaConversacional;
}

const nf = new Intl.NumberFormat("es-PY");

function referenciasAlmacen(): ReferenciaRespuesta[] {
  return [
    { tipo: "almacen", etiqueta: "Almacén Misión 004 (fixtures de demostración)" },
  ];
}

function despachar(consulta: string, datos: DatosMVP): RespuestaConversacional {
  const q = consulta.toLowerCase();
  const r = datos.health.resumen;

  const tiene = (...claves: string[]) => claves.some((c) => q.includes(c));

  if (tiene("hola", "buenas", "qué tal", "que tal")) {
    return {
      tipo: "explicacion",
      texto:
        "¡Hola! Soy el centro de inteligencia de FIREIA en modo demostración local. Puedo responder preguntas simples sobre el almacén cargado: cuántas detecciones hay, qué departamentos están afectados, qué eventos de co-detección existen y qué significa cada cosa. Probá con una de las sugerencias.",
      referencias: referenciasAlmacen(),
    };
  }

  if (tiene("cuántas", "cuantas", "cantidad", "detecciones", "focos")) {
    const fuera = r.total - r.dentro_pais;
    return {
      tipo: "datos",
      texto: `En la ventana del ${datos.health.cobertura.desde} al ${datos.health.cobertura.hasta} hay ${nf.format(r.total)} detecciones registradas: ${nf.format(r.modis)} de MODIS y ${nf.format(r.viirs)} de VIIRS. De ellas, ${nf.format(r.dentro_pais)} caen dentro del territorio de Paraguay y ${nf.format(fuera)} en el área de consulta vecina. Recuerda que en esta demo los datos son sintéticos (fixtures de NASA FIRMS).`,
      referencias: [
        ...referenciasAlmacen(),
        { tipo: "observaciones", etiqueta: `${nf.format(r.total)} observaciones` },
      ],
    };
  }

  if (tiene("departamento", "donde", "dónde", "región", "region", "territorio")) {
    const porDep = new Map<string, number>();
    for (const o of datos.observaciones) {
      if (o.departamento)
        porDep.set(o.departamento, (porDep.get(o.departamento) ?? 0) + 1);
    }
    const filas = Array.from(porDep.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([d, n]) => `${d} (${n})`)
      .join(", ");
    return {
      tipo: "datos",
      texto: `Hay ${r.departamentos_afectados.length} departamentos con al menos una detección en la ventana: ${filas}. La asignación se hace comprobando si el punto cae dentro del polígono oficial de cada departamento (método point-in-polygon, límites geoBoundaries).`,
      referencias: [
        ...referenciasAlmacen(),
        {
          tipo: "observaciones",
          etiqueta: `${r.departamentos_afectados.length} departamentos afectados`,
        },
      ],
    };
  }

  if (tiene("evento", "co-detección", "codeteccion", "coincidencia")) {
    if (datos.eventos.length === 0) {
      return {
        tipo: "datos",
        texto:
          "El almacén actual no tiene eventos de co-detección construidos. Los eventos se generan con el comando hotspots events build del pipeline.",
        referencias: referenciasAlmacen(),
      };
    }
    const e = datos.eventos[0];
    return {
      tipo: "datos",
      texto: `Hay ${datos.eventos.length} evento${datos.eventos.length === 1 ? "" : "s"} de co-detección en la ventana. El primero agrupa ${e.n_observaciones} observaciones de ${e.productos.join(" y ")}, con una duración de ${e.duracion_segundos} segundos y una dispersión de ${e.dispersion_metros} m. Importante: un evento es una agrupación analítica de observaciones cercanas en espacio y tiempo, no necesariamente un incendio individual confirmado.`,
      referencias: [
        ...referenciasAlmacen(),
        { tipo: "eventos", etiqueta: `Evento ${e.event_id.slice(0, 8)}…` },
      ],
    };
  }

  if (tiene("frp", "intensidad", "potencia", "energía", "energia")) {
    const frpModis = datos.stats.nacional_dia
      .filter((s) => s.product === "MODIS_NRT")
      .reduce((a, s) => a + s.frp_total, 0);
    const frpViirs = datos.stats.nacional_dia
      .filter((s) => s.product === "VIIRS_NOAA20_NRT")
      .reduce((a, s) => a + s.frp_total, 0);
    return {
      tipo: "explicacion",
      texto: `La intensidad energética estimada (FRP, potencia radiativa de fuego) mide la energía que irradia cada foco, en megavatios. En la ventana, la suma por sensor es ${frpModis.toFixed(1)} MW para MODIS y ${frpViirs.toFixed(1)} MW para VIIRS. Los valores de ambos sensores no son directamente comparables entre sí, por eso FIREIA nunca los suma.`,
      referencias: [
        ...referenciasAlmacen(),
        { tipo: "observaciones", etiqueta: "FRP por observación disponible" },
      ],
    };
  }

  if (tiene("calidad", "confianza", "cuarentena", "error")) {
    const cuarentena = datos.calidad.cuarentena_registros;
    const conDatos = datos.cobertura?.resumen?.con_detecciones ?? 0;
    return {
      tipo: "datos",
      texto: `La calidad del almacén se controla en dos niveles. Por registro: cada observación pasa por un control de ingesta con 10 estados posibles; ahora hay ${cuarentena} registros en cuarentena (conservados íntegros con sus errores, nunca descartados en silencio). Por día: cada día se clasifica antes de entrar a las estadísticas; en esta ventana ${conDatos} días tienen detecciones. Un día sin datos no se cuenta como día sin fuego.`,
      referencias: [
        ...referenciasAlmacen(),
        { tipo: "calidad", etiqueta: `${cuarentena} registros en cuarentena` },
      ],
    };
  }

  if (tiene("confianza de detección", "l", "nominal", "high", "low")) {
    const porBanda = new Map<string, number>();
    for (const o of datos.observaciones)
      porBanda.set(o.confidence_band, (porBanda.get(o.confidence_band) ?? 0) + 1);
    const filas = Array.from(porBanda.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([b, n]) => `${b}: ${n}`)
      .join(" · ");
    return {
      tipo: "explicacion",
      texto: `El nivel de confianza indica qué tan seguro está el algoritmo del satélite de que el punto detectado es realmente fuego. Distribución en la ventana — ${filas}. "l" (low) es baja confianza, "nominal" es intermedia y "high" es alta.`,
      referencias: [
        ...referenciasAlmacen(),
        { tipo: "observaciones", etiqueta: "Confianza por observación" },
      ],
    };
  }

  if (tiene("pronóstico", "pronostico", "predicción", "prediccion", "futuro", "riesgo")) {
    return {
      tipo: "disponibilidad",
      texto:
        "Todavía no existen modelos predictivos validados en FIREIA, así que no doy pronósticos. Cuando los haya —tras el piloto con datos reales y validación frente al baseline de persistencia— aparecerán en la sección Riesgo y estimaciones futuras. Podés explorar cómo se verían en el Laboratorio de simulaciones, siempre con datos sintéticos etiquetados.",
      referencias: [
        { tipo: "almacen", etiqueta: "Sin modelos validados (política del proyecto)" },
      ],
    };
  }

  if (tiene("qué es fireia", "que es fireia", "quiénes", "quienes", "proyecto", "nasas", "firma", "firms")) {
    return {
      tipo: "explicacion",
      texto:
        "FIREIA (Paraguay Fire Intelligence) es una plataforma de inteligencia sobre incendios que cruza las detecciones de los satélites MODIS y VIIRS de la NASA (distribuidas por FIRMS) sobre el territorio de Paraguay. Es el proyecto del equipo P400 para el NASA Space Apps Challenge 2026 (reto 1.9). Esta versión carga fixtures sintéticos: ningún dato real fue consumido todavía.",
      referencias: referenciasAlmacen(),
    };
  }

  if (tiene("real", "fase 1b", "cuándo", "cuando", "datos reales")) {
    return {
      tipo: "disponibilidad",
      texto:
        "Los datos reales llegan con la Fase 1B: la ingesta desde la API de FIRMS está detrás de una compuerta de red que exige credenciales válidas y autorización explícita del propietario. Esta plataforma es consumidora de solo lectura: navegarla nunca dispara descargas ni consume cuota de la API.",
      referencias: referenciasAlmacen(),
    };
  }

  if (tiene("gracias", "excelente", "perfecto")) {
    return {
      tipo: "explicacion",
      texto:
        "¡De nada! Si querés seguir explorando, preguntame por departamentos, eventos, intensidad o calidad; o usá las sugerencias debajo del campo de consulta.",
      referencias: [],
    };
  }

  return {
    tipo: "no_encontrado",
    texto:
      "En el modo demostración local solo puedo responder consultas simples sobre el almacén cargado (detecciones, departamentos, eventos, intensidad, calidad y el estado del proyecto). Probá con: «¿Cuántas detecciones hubo?», «¿Qué departamentos están afectados?» o «¿Qué es un evento?».",
    referencias: referenciasAlmacen(),
  };
}

/** Adaptador local por reglas — sin IA, sin red. */
export class ReglasLocalesAdapter implements ConversacionService {
  responder(consulta: string, datos: DatosMVP): RespuestaConversacional {
    return despachar(consulta, datos);
  }
}

export const conversacionService: ConversacionService =
  new ReglasLocalesAdapter();

export const SUGERENCIAS_CONSULTA = [
  "¿Cuántas detecciones hubo?",
  "¿Qué departamentos están afectados?",
  "¿Qué es un evento de co-detección?",
  "¿Qué significa la intensidad (FRP)?",
  "¿Cómo se controla la calidad?",
  "¿Cuándo habrá datos reales?",
];
