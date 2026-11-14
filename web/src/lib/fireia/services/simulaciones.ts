// FIREIA (M012) — Generadores del Laboratorio de simulaciones.
// Todos los datos son SINTÉTICOS, deterministas (semilla fija por
// escenario) y viven solo en el navegador. Ningún resultado representa
// mediciones satelitales reales. No hay lógica científica del pipeline
// aquí: son visualizaciones controladas para demostrar las funciones.

/** PRNG determinista (mulberry32) para escenarios reproducibles. */
export function prng(semilla: number): () => number {
  let a = semilla >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// --- contorno aproximado de Paraguay (caja + vértices simplificados) ---
export const PY = { latMin: -27.6, latMax: -19.2, lonMin: -62.7, lonMax: -54.2 };
export const PY_CONTOUR: Array<[number, number]> = [
  [-58.2, -19.3],
  [-55.0, -19.3],
  [-54.6, -20.0],
  [-54.3, -22.2],
  [-54.6, -23.9],
  [-55.7, -24.0],
  [-56.5, -24.9],
  [-57.6, -25.2],
  [-58.2, -27.3],
  [-58.6, -27.4],
  [-62.1, -25.6],
  [-62.7, -22.2],
  [-61.7, -20.0],
  [-60.2, -19.5],
  [-58.2, -19.3],
];

export const KM_POR_GRADO_LAT = 111;
export function kmPorGradoLon(lat: number): number {
  return 111 * Math.cos((lat * Math.PI) / 180);
}

// ------------------------------------------------------------------
// Módulo 1 — Actividad satelital sintética
// ------------------------------------------------------------------
export interface PuntoSintetico {
  x: number; // 0..1 dentro de la caja de Paraguay
  y: number;
  sensor: "MODIS" | "VIIRS";
  daynight: "D" | "N";
  intensidad: number; // MW sintéticos
}

export interface ParamsActividad {
  cantidad: number;
  proporcionModis: number; // 0..1
  proporcionNoche: number; // 0..1
  semilla: number;
}

export function generarActividad(p: ParamsActividad): PuntoSintetico[] {
  const rnd = prng(p.semilla);
  // rechazo de puntos fuera del contorno simplificado: caja con margen
  const puntos: PuntoSintetico[] = [];
  let guardia = 0;
  while (puntos.length < p.cantidad && guardia < p.cantidad * 30) {
    guardia++;
    const x = rnd();
    const y = rnd();
    const lon = PY.lonMin + x * (PY.lonMax - PY.lonMin);
    const lat = PY.latMax - y * (PY.latMax - PY.latMin);
    if (!dentroDeParaguay(lon, lat)) continue;
    puntos.push({
      x,
      y,
      sensor: rnd() < p.proporcionModis ? "MODIS" : "VIIRS",
      daynight: rnd() < p.proporcionNoche ? "N" : "D",
      intensidad: Math.round((5 + rnd() * 45) * 10) / 10,
    });
  }
  return puntos;
}

function dentroDeParaguay(lon: number, lat: number): boolean {
  // point-in-polygon contra el contorno simplificado
  let dentro = false;
  for (let i = 0, j = PY_CONTOUR.length - 1; i < PY_CONTOUR.length; j = i++) {
    const [xi, yi] = PY_CONTOUR[i];
    const [xj, yj] = PY_CONTOUR[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi)
      dentro = !dentro;
  }
  return dentro;
}

// ------------------------------------------------------------------
// Módulo 2 — Coincidencias MODIS–VIIRS sintéticas
// ------------------------------------------------------------------
export interface ParSintetico {
  modis: { x: number; y: number };
  viirs: { x: number; y: number };
  deltaMin: number; // diferencia temporal en minutos
}

export interface ParamsCoincidencia {
  cantidadPares: number;
  dispersionKm: number; // separación base entre sensores
  semilla: number;
  radioKm: number; // umbral espacial del usuario
  ventanaMin: number; // umbral temporal del usuario
}

export interface ResultadoCoincidencia {
  pares: ParSintetico[];
  coincidentes: boolean[];
  nCoincidentes: number;
}

export function evaluarCoincidencia(
  p: ParamsCoincidencia,
): ResultadoCoincidencia {
  const rnd = prng(p.semilla);
  // conversión km → fracción de caja (para dibujar en el mapa esquemático)
  const lat = -23.4;
  const kmLon = kmPorGradoLon(lat);
  const anchoKm = (PY.lonMax - PY.lonMin) * kmLon;
  const altoKm = (PY.latMax - PY.latMin) * KM_POR_GRADO_LAT;

  const pares: ParSintetico[] = [];
  for (let i = 0; i < p.cantidadPares; i++) {
    const cx = 0.28 + rnd() * 0.44;
    const cy = 0.25 + rnd() * 0.5;
    const ang = rnd() * Math.PI * 2;
    // separación entre sensores en km (± la mitad para cada uno)
    const sepKm = p.dispersionKm * (0.3 + rnd() * 1.4);
    const dx = ((Math.cos(ang) * sepKm) / 2 / anchoKm) * 1.6; // 1.6: corrección visual del mapa esquemático
    const dy = (Math.sin(ang) * sepKm) / 2 / altoKm;
    pares.push({
      modis: { x: cx - dx, y: cy - dy },
      viirs: { x: cx + dx, y: cy + dy },
      deltaMin: Math.round(5 + rnd() * 230),
    });
  }
  // evaluar contra los umbrales del usuario (distancias en km reales)
  const coincidentes = pares.map((par) => {
    const dxKm = (par.modis.x - par.viirs.x) * anchoKm;
    const dyKm = (par.modis.y - par.viirs.y) * altoKm;
    const distKm = Math.hypot(dxKm, dyKm);
    return distKm <= p.radioKm && par.deltaMin <= p.ventanaMin;
  });
  return {
    pares,
    coincidentes,
    nCoincidentes: coincidentes.filter(Boolean).length,
  };
}

// ------------------------------------------------------------------
// Módulo 3 — Agrupación de eventos sintética
// ------------------------------------------------------------------
export interface PuntoAgrupable {
  x: number;
  y: number;
  grupo: number;
}

export interface ParamsAgrupacion {
  cantidad: number;
  nSemillas: number;
  radioKm: number; // radio de agrupación del usuario
  semilla: number;
}

/** Agrupamiento greedy por radio (ilustrativo, no es el método del pipeline). */
export function agrupar(p: ParamsAgrupacion): PuntoAgrupable[] {
  const rnd = prng(p.semilla);
  const puntos: Array<{ x: number; y: number; grupo: number }> = [];
  const lat = -23.4;
  const kmLon = kmPorGradoLon(lat);
  const anchoKm = (PY.lonMax - PY.lonMin) * kmLon;
  const altoKm = (PY.latMax - PY.latMin) * KM_POR_GRADO_LAT;
  const radioFrac =
    Math.hypot(
      (p.radioKm / anchoKm) * Math.cos((lat * Math.PI) / 180),
      p.radioKm / altoKm,
    ) * 0.9;

  let grupos = 0;
  for (let i = 0; i < p.cantidad; i++) {
    const x = 0.2 + rnd() * 0.6;
    const y = 0.2 + rnd() * 0.6;
    // buscar grupo existente dentro del radio
    let asignado = -1;
    for (const pt of puntos) {
      if (Math.hypot(pt.x - x, pt.y - y) <= radioFrac) {
        asignado = pt.grupo;
        break;
      }
    }
    if (asignado === -1) {
      asignado = grupos++;
    }
    puntos.push({ x, y, grupo: asignado });
  }
  return puntos;
}

// ------------------------------------------------------------------
// Módulo 4 — Serie temporal sintética
// ------------------------------------------------------------------
export interface PuntoTemporal {
  dia: number;
  valor: number;
}

export interface ParamsTemporal {
  dias: number;
  nivelBase: number;
  amplitudSemanal: number;
  ruido: number; // 0..1
  tendencia: number; // pendiente por día
  semilla: number;
}

export function generarSerieTemporal(p: ParamsTemporal): PuntoTemporal[] {
  const rnd = prng(p.semilla);
  const salida: PuntoTemporal[] = [];
  for (let d = 0; d < p.dias; d++) {
    const semanal = Math.sin((d / 7) * Math.PI * 2) * p.amplitudSemanal;
    const ruidoVal = (rnd() - 0.5) * 2 * p.ruido * p.nivelBase * 0.5;
    const valor = Math.max(0, p.nivelBase + semanal + p.tendencia * d + ruidoVal);
    salida.push({ dia: d, valor: Math.round(valor * 10) / 10 });
  }
  return salida;
}

// ------------------------------------------------------------------
// Módulo 5 — Perfil ambiental hipotético
// ------------------------------------------------------------------
export interface DiaAmbiental {
  dia: string;
  temperatura: number;
  precipitacion: number;
  viento: number;
}

export interface ParamsAmbiental {
  temperaturaBase: number;
  precipitacionSemanal: number;
  vientoBase: number;
  semilla: number;
}

const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export function generarSemanaAmbiental(p: ParamsAmbiental): DiaAmbiental[] {
  const rnd = prng(p.semilla);
  let lluviaRestante = p.precipitacionSemanal;
  const salida: DiaAmbiental[] = [];
  for (let i = 0; i < 7; i++) {
    const lluviaDia =
      lluviaRestante <= 0
        ? 0
        : Math.min(lluviaRestante, lluviaRestante * rnd() * 0.6);
    lluviaRestante -= lluviaDia;
    salida.push({
      dia: DIAS[i],
      temperatura: Math.round((p.temperaturaBase + (rnd() - 0.5) * 4) * 10) / 10,
      precipitacion: Math.round(lluviaDia * 10) / 10,
      viento: Math.round(Math.max(0, p.vientoBase + (rnd() - 0.5) * 3) * 10) / 10,
    });
  }
  return salida;
}

// ------------------------------------------------------------------
// Módulo 6 — Anomalías sintéticas
// ------------------------------------------------------------------
export interface PuntoAnomalia {
  dia: number;
  valor: number;
  esperado: number;
  z: number;
  detectada: boolean;
  inyectada: boolean;
}

export interface ParamsAnomalia {
  magnitud: number; // multiplicador del pico inyectado
  umbralZ: number;
  semilla: number;
}

export function generarSerieAnomalia(p: ParamsAnomalia): {
  puntos: PuntoAnomalia[];
  nDetectadas: number;
  nInyectadas: number;
  falsosPositivos: number;
} {
  const rnd = prng(p.semilla);
  const puntos: PuntoAnomalia[] = [];
  const diaInyeccion = 38;
  let suma = 0;
  let suma2 = 0;
  let n = 0;

  for (let d = 0; d < 60; d++) {
    const base = 40 + Math.sin((d / 7) * Math.PI * 2) * 6 + (rnd() - 0.5) * 4;
    const inyectada = d === diaInyeccion;
    const valor = inyectada ? base * p.magnitud : base;
    // esperado: media móvil simple del pasado (ilustrativo)
    const esperado = n > 0 ? suma / n : base;
    const varianza = n > 1 ? Math.max(1, suma2 / n - esperado * esperado) : 4;
    const sigma = Math.sqrt(varianza);
    const z = (valor - esperado) / sigma;
    const detectada = z >= p.umbralZ;
    puntos.push({
      dia: d,
      valor: Math.round(valor * 10) / 10,
      esperado: Math.round(esperado * 10) / 10,
      z: Math.round(z * 10) / 10,
      detectada,
      inyectada,
    });
    if (!inyectada) {
      suma += valor;
      suma2 += valor * valor;
      n++;
    }
  }

  const nDetectadas = puntos.filter((x) => x.detectada).length;
  const nInyectadas = puntos.filter((x) => x.inyectada).length;
  const falsosPositivos = puntos.filter((x) => x.detectada && !x.inyectada).length;
  return { puntos, nDetectadas, nInyectadas, falsosPositivos };
}

// ------------------------------------------------------------------
// Módulo 7 — Escenarios futuros hipotéticos
// ------------------------------------------------------------------
export interface PuntoEscenario {
  dia: number;
  central: number;
  piso: number;
  techo: number;
}

export interface ParamsEscenario {
  horizonteDias: number;
  nivel: "bajo" | "medio" | "alto";
  incertidumbre: number; // 0..1 ancho de la banda
  semilla: number;
}

const FACTOR_NIVEL = { bajo: 0.55, medio: 1, alto: 1.6 };

export function generarEscenario(p: ParamsEscenario): PuntoEscenario[] {
  const rnd = prng(p.semilla);
  const base = 22 * FACTOR_NIVEL[p.nivel];
  const salida: PuntoEscenario[] = [];
  for (let d = 0; d < p.horizonteDias; d++) {
    const estacional = Math.sin((d / 14) * Math.PI * 2) * 5 * FACTOR_NIVEL[p.nivel];
    const central = Math.max(0, base + estacional + (rnd() - 0.5) * 3);
    const ancho = central * p.incertidumbre * 0.5;
    salida.push({
      dia: d,
      central: Math.round(central * 10) / 10,
      piso: Math.round(Math.max(0, central - ancho) * 10) / 10,
      techo: Math.round((central + ancho) * 10) / 10,
    });
  }
  return salida;
}
