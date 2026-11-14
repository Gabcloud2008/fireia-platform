"use client";

// Laboratorio de simulaciones FIREIA (M012 §7) — módulos interactivos.
// Todos usan los generadores sintéticos deterministas del servicio de
// simulaciones (src/lib/fireia/services/simulaciones.ts). Etiqueta
// permanente «SIMULACIÓN — DATOS SINTÉTICOS», parámetros visibles,
// restablecimiento y explicación en lenguaje sencillo en cada módulo.

import { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  evaluarCoincidencia,
  agrupar,
  generarActividad,
  generarEscenario,
  generarSemanaAmbiental,
  generarSerieAnomalia,
  generarSerieTemporal,
  PY_CONTOUR,
  type PuntoSintetico,
} from "@/lib/fireia/services/simulaciones";

const COLOR_MODIS = "#d97c45";
const COLOR_VIIRS = "#3e8e87";

const tooltipStyle = {
  backgroundColor: "#ffffff",
  border: "1px solid #ecdfd1",
  borderRadius: "10px",
  color: "#39332f",
  fontSize: "12px",
  boxShadow: "0 8px 20px rgb(57 51 47 / 0.08)",
};

// --- contorno de Paraguay normalizado a un viewBox 100×100 ---
const CONTORNO_PATH =
  PY_CONTOUR.map(([lon, lat], i) => {
    const x = ((lon - -62.7) / (-54.2 - -62.7)) * 100;
    const y = ((-19.2 - lat) / (-19.2 - -27.6)) * 100;
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + " Z";

function EtiquetaSimulacion() {
  return (
    <span className="rounded-full bg-tint px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-flame">
      Simulación — datos sintéticos
    </span>
  );
}

function MarcoSim({
  titulo,
  explicacion,
  onReset,
  children,
  controles,
}: {
  titulo: string;
  explicacion: string;
  onReset: () => void;
  children: React.ReactNode;
  controles: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
          {titulo}
          <EtiquetaSimulacion />
        </h3>
        <Button
          variant="outline"
          size="sm"
          onClick={onReset}
          className="rounded-full border-border bg-card text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <RotateCcw className="size-3" aria-hidden />
          Restablecer
        </Button>
      </div>
      <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">
        {explicacion}
      </p>
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-4">{controles}</div>
        <div className="lg:col-span-8">{children}</div>
      </div>
    </div>
  );
}

function ControlSlider({
  etiqueta,
  valor,
  min,
  max,
  step = 1,
  formato,
  onChange,
}: {
  etiqueta: string;
  valor: number;
  min: number;
  max: number;
  step?: number;
  formato?: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label className="text-xs font-medium text-foreground">{etiqueta}</label>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold tabular-nums text-brown">
          {formato ? formato(valor) : valor}
        </span>
      </div>
      <Slider
        value={[valor]}
        min={min}
        max={max}
        step={step}
        onValueChange={(v) => onChange(v[0])}
        aria-label={etiqueta}
      />
    </div>
  );
}

function MapaSvg({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="-4 -4 108 108"
      className="w-full rounded-xl border border-border bg-[#fffdfb]"
      role="img"
      aria-label="Mapa esquemático de Paraguay con datos sintéticos"
    >
      <path
        d={CONTORNO_PATH}
        fill="#f4eae0"
        stroke="#c4ae97"
        strokeWidth="0.8"
      />
      {children}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Módulo 1 — Simulación de actividad satelital
// ---------------------------------------------------------------------------

export function SimActividad() {
  const [cantidad, setCantidad] = useState(36);
  const [propModis, setPropModis] = useState(55);
  const [propNoche, setPropNoche] = useState(35);
  const [semilla, setSemilla] = useState(7);

  const puntos = useMemo(
    () =>
      generarActividad({
        cantidad,
        proporcionModis: propModis / 100,
        proporcionNoche: propNoche / 100,
        semilla,
      }),
    [cantidad, propModis, propNoche, semilla],
  );

  const nModis = puntos.filter((p) => p.sensor === "MODIS").length;
  const nViirs = puntos.length - nModis;

  return (
    <MarcoSim
      titulo="1 · Actividad satelital"
      explicacion="Generá un conjunto ficticio de detecciones y observá cómo se visualizarían sobre el país: puntos naranjas (MODIS, píxeles de 1 km) y verdes azulados (VIIRS, píxeles de 375 m). Ninguno de estos focos existió: sirven para entender la representación."
      onReset={() => {
        setCantidad(36);
        setPropModis(55);
        setPropNoche(35);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Cantidad de focos"
            valor={cantidad}
            min={5}
            max={90}
            onChange={setCantidad}
          />
          <ControlSlider
            etiqueta="Proporción MODIS"
            valor={propModis}
            min={0}
            max={100}
            formato={(v) => `${v}%`}
            onChange={setPropModis}
          />
          <ControlSlider
            etiqueta="Passes nocturnos"
            valor={propNoche}
            min={0}
            max={100}
            formato={(v) => `${v}%`}
            onChange={setPropNoche}
          />
          <p className="rounded-lg bg-secondary/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            Resultado: {nModis} MODIS · {nViirs} VIIRS. El resto sería VIIRS.
            Los focos nocturnos (pass de noche) suelen tener menos falsos
            positivos porque el suelo está más frío.
          </p>
        </>
      }
    >
      <MapaSvg>
        {puntos.map((p, i) => (
          <circle
            key={i}
            cx={p.x * 100}
            cy={p.y * 100}
            r={p.sensor === "MODIS" ? 1.7 : 1.2}
            fill={p.sensor === "MODIS" ? COLOR_MODIS : COLOR_VIIRS}
            fillOpacity={0.85}
            stroke={p.sensor === "MODIS" ? "#8a4516" : "#1f5450"}
            strokeWidth={0.3}
          />
        ))}
      </MapaSvg>
    </MarcoSim>
  );
}

// ---------------------------------------------------------------------------
// Módulo 2 — Simulación MODIS–VIIRS
// ---------------------------------------------------------------------------

export function SimCoincidencia() {
  const [radioKm, setRadioKm] = useState(2);
  const [ventanaMin, setVentanaMin] = useState(60);
  const [dispersion, setDispersion] = useState(4);
  const [semilla, setSemilla] = useState(11);

  const resultado = useMemo(
    () =>
      evaluarCoincidencia({
        cantidadPares: 14,
        dispersionKm: dispersion,
        semilla,
        radioKm,
        ventanaMin,
      }),
    [dispersion, semilla, radioKm, ventanaMin],
  );

  return (
    <MarcoSim
      titulo="2 · Coincidencias MODIS–VIIRS"
      explicacion="Cada par de puntos (naranja = MODIS, verde = VIIRS) es un candidato a coincidencia. Trazá la línea de coincidencia ajustando la distancia máxima y la ventana temporal permitidas. Así funciona el criterio del pipeline: la ventana junta candidatos; confirmar la relación es otro análisis."
      onReset={() => {
        setRadioKm(2);
        setVentanaMin(60);
        setDispersion(4);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Distancia máxima entre sensores"
            valor={radioKm}
            min={0.5}
            max={10}
            step={0.5}
            formato={(v) => `${v} km`}
            onChange={setRadioKm}
          />
          <ControlSlider
            etiqueta="Ventana temporal"
            valor={ventanaMin}
            min={10}
            max={240}
            step={10}
            formato={(v) => `${v} min`}
            onChange={setVentanaMin}
          />
          <ControlSlider
            etiqueta="Dispersión base de los pares"
            valor={dispersion}
            min={1}
            max={10}
            step={0.5}
            formato={(v) => `${v} km`}
            onChange={setDispersion}
          />
          <p className="rounded-lg bg-secondary/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            Coinciden {resultado.nCoincidentes} de {resultado.pares.length}{" "}
            pares. Con ventanas más amplias coinciden más pares — y también
            aumenta el riesgo de juntar fuegos distintos. Ese equilibrio lo
            decide el método versionado del pipeline, no esta demo.
          </p>
        </>
      }
    >
      <MapaSvg>
        {resultado.pares.map((par, i) => {
          const coincide = resultado.coincidentes[i];
          const x1 = 10 + par.modis.x * 80;
          const y1 = 10 + par.modis.y * 80;
          const x2 = 10 + par.viirs.x * 80;
          const y2 = 10 + par.viirs.y * 80;
          return (
            <g key={i}>
              {coincide && (
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="#c05f2c"
                  strokeWidth={0.5}
                  strokeDasharray="1.4 1"
                />
              )}
              <circle
                cx={x1}
                cy={y1}
                r={1.6}
                fill={COLOR_MODIS}
                fillOpacity={coincide ? 1 : 0.45}
              />
              <circle
                cx={x2}
                cy={y2}
                r={1.3}
                fill={COLOR_VIIRS}
                fillOpacity={coincide ? 1 : 0.45}
              />
            </g>
          );
        })}
      </MapaSvg>
    </MarcoSim>
  );
}

// ---------------------------------------------------------------------------
// Módulo 3 — Simulación de agrupación de eventos
// ---------------------------------------------------------------------------

const COLORES_GRUPO = [
  "#c05f2c",
  "#3e8e87",
  "#8a6116",
  "#6b5d52",
  "#a94f22",
  "#1f5450",
  "#8a4516",
  "#4a6b8a",
  "#7a5c3d",
  "#5d7052",
  "#9c4f5e",
  "#55606b",
];

export function SimAgrupacion() {
  const [radioKm, setRadioKm] = useState(30);
  const [semilla, setSemilla] = useState(23);

  const puntos = useMemo(
    () =>
      agrupar({
        cantidad: 40,
        nSemillas: 6,
        radioKm,
        semilla,
      }),
    [radioKm, semilla],
  );

  const nGrupos = new Set(puntos.map((p) => p.grupo)).size;

  return (
    <MarcoSim
      titulo="3 · Agrupación de eventos"
      explicacion="Cada punto es una detección ficticia. Aumentá el radio de agrupación y observá cómo detecciones que antes quedaban sueltas se fusionan en un mismo grupo (un «evento»). El pipeline hace esto con un método versionado de componentes conexas entre pares de sensores; aquí se muestra la idea con un agrupamiento ilustrativo por radio."
      onReset={() => {
        setRadioKm(30);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Radio de agrupación"
            valor={radioKm}
            min={5}
            max={120}
            step={5}
            formato={(v) => `${v} km`}
            onChange={setRadioKm}
          />
          <p className="rounded-lg bg-secondary/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            Con {radioKm} km se forman {nGrupos} grupos a partir de{" "}
            {puntos.length} detecciones. Un radio muy grande fusiona fenómenos
            distintos; muy pequeño, parte en pedazos el mismo fenómeno.
          </p>
        </>
      }
    >
      <MapaSvg>
        {puntos.map((p, i) => (
          <circle
            key={i}
            cx={10 + p.x * 80}
            cy={10 + p.y * 80}
            r={1.5}
            fill={COLORES_GRUPO[p.grupo % COLORES_GRUPO.length]}
            fillOpacity={0.85}
          />
        ))}
      </MapaSvg>
    </MarcoSim>
  );
}

// ---------------------------------------------------------------------------
// Módulo 4 — Simulación temporal
// ---------------------------------------------------------------------------

export function SimTemporal() {
  const [nivel, setNivel] = useState(35);
  const [amplitud, setAmplitud] = useState(8);
  const [ruido, setRuido] = useState(0.3);
  const [tendencia, setTendencia] = useState(0.1);
  const [semilla, setSemilla] = useState(41);

  const serie = useMemo(
    () =>
      generarSerieTemporal({
        dias: 90,
        nivelBase: nivel,
        amplitudSemanal: amplitud,
        ruido,
        tendencia,
        semilla,
      }),
    [nivel, amplitud, ruido, tendencia, semilla],
  );

  const datos = serie.map((p) => ({ dia: p.dia + 1, valor: p.valor }));

  return (
    <MarcoSim
      titulo="4 · Distribución temporal"
      explicacion="Explorá cómo se vería la actividad a lo largo de los días: un nivel base, un ciclo semanal, ruido y una tendencia. Así se aprecia la diferencia entre un pico puntual (una anomalía) y un cambio sostenido (una tendencia)."
      onReset={() => {
        setNivel(35);
        setAmplitud(8);
        setRuido(0.3);
        setTendencia(0.1);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Nivel base de actividad"
            valor={nivel}
            min={10}
            max={80}
            onChange={setNivel}
          />
          <ControlSlider
            etiqueta="Ciclo semanal"
            valor={amplitud}
            min={0}
            max={20}
            onChange={setAmplitud}
          />
          <ControlSlider
            etiqueta="Ruido"
            valor={ruido}
            min={0}
            max={1}
            step={0.05}
            formato={(v) => `${Math.round(v * 100)}%`}
            onChange={setRuido}
          />
          <ControlSlider
            etiqueta="Tendencia diaria"
            valor={tendencia}
            min={-0.5}
            max={0.5}
            step={0.05}
            formato={(v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}/día`}
            onChange={setTendencia}
          />
        </>
      }
    >
      <div className="h-72 rounded-xl border border-border bg-[#fffdfb] p-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="dia"
              tick={{ fill: "#82766d", fontSize: 10 }}
              stroke="#e4d5c6"
              interval={13}
            />
            <YAxis tick={{ fill: "#82766d", fontSize: 10 }} stroke="#e4d5c6" />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#82766d" }}
              labelFormatter={(d) => `Día ${d}`}
              cursor={{ stroke: "#b7a89c", strokeDasharray: "3 3" }}
            />
            <Line
              type="monotone"
              dataKey="valor"
              name="Detecciones (sintéticas)"
              stroke="#c05f2c"
              strokeWidth={1.8}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </MarcoSim>
  );
}

// ---------------------------------------------------------------------------
// Módulo 5 — Simulación ambiental
// ---------------------------------------------------------------------------

export function SimAmbiental() {
  const [temperatura, setTemperatura] = useState(33);
  const [lluvia, setLluvia] = useState(10);
  const [viento, setViento] = useState(9);
  const [semilla, setSemilla] = useState(59);

  const semana = useMemo(
    () =>
      generarSemanaAmbiental({
        temperaturaBase: temperatura,
        precipitacionSemanal: lluvia,
        vientoBase: viento,
        semilla,
      }),
    [temperatura, lluvia, viento, semilla],
  );

  return (
    <MarcoSim
      titulo="5 · Variables ambientales"
      explicacion="Componé una semana hipotética de temperatura, lluvia y viento y observá cómo se representarían juntas. Esta simulación no afirma ninguna relación causal entre clima y fuego: solo muestra la representación visual prevista para cuando los datos reales existan."
      onReset={() => {
        setTemperatura(33);
        setLluvia(10);
        setViento(9);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Temperatura promedio"
            valor={temperatura}
            min={15}
            max={42}
            formato={(v) => `${v} °C`}
            onChange={setTemperatura}
          />
          <ControlSlider
            etiqueta="Lluvia total de la semana"
            valor={lluvia}
            min={0}
            max={120}
            step={5}
            formato={(v) => `${v} mm`}
            onChange={setLluvia}
          />
          <ControlSlider
            etiqueta="Viento promedio"
            valor={viento}
            min={0}
            max={25}
            formato={(v) => `${v} m/s`}
            onChange={setViento}
          />
          <p className="rounded-lg bg-secondary/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            La lluvia se reparte de forma sintética entre los días de la semana.
            Con 0 mm la semana es seca; con 120 mm, casi toda la lluvia cae en
            pocos días.
          </p>
        </>
      }
    >
      <div className="h-72 rounded-xl border border-border bg-[#fffdfb] p-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={semana} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
            <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="dia" tick={{ fill: "#82766d", fontSize: 11 }} stroke="#e4d5c6" />
            <YAxis yAxisId="t" tick={{ fill: "#82766d", fontSize: 10 }} stroke="#e4d5c6" />
            <YAxis
              yAxisId="p"
              orientation="right"
              tick={{ fill: "#82766d", fontSize: 10 }}
              stroke="#e4d5c6"
            />
            <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: "#82766d" }} />
            <Legend wrapperStyle={{ fontSize: 11, color: "#82766d" }} />
            <Bar
              yAxisId="p"
              dataKey="precipitacion"
              name="Lluvia (mm)"
              fill="#7ba7bc"
              radius={[3, 3, 0, 0]}
            />
            <Line
              yAxisId="t"
              type="monotone"
              dataKey="temperatura"
              name="Temperatura (°C)"
              stroke="#c05f2c"
              strokeWidth={1.8}
              dot={false}
            />
            <Line
              yAxisId="t"
              type="monotone"
              dataKey="viento"
              name="Viento (m/s)"
              stroke="#3e8e87"
              strokeWidth={1.8}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </MarcoSim>
  );
}

// ---------------------------------------------------------------------------
// Módulo 6 — Simulación de anomalías
// ---------------------------------------------------------------------------

export function SimAnomalias() {
  const [magnitud, setMagnitud] = useState(2.5);
  const [umbralZ, setUmbralZ] = useState(3);
  const [semilla, setSemilla] = useState(73);

  const { puntos, nDetectadas, falsosPositivos } = useMemo(
    () => generarSerieAnomalia({ magnitud, umbralZ, semilla }),
    [magnitud, umbralZ, semilla],
  );

  const datos = puntos.map((p) => ({
    dia: p.dia + 1,
    valor: p.valor,
    esperado: p.esperado,
    anomalia: p.detectada ? p.valor : null,
  }));

  return (
    <MarcoSim
      titulo="6 · Detección de anomalías"
      explicacion="La línea gris clara es el comportamiento de referencia (lo esperado según el pasado); la línea naranja es lo observado. El día 38 se planta un pico sintético. Bajá el umbral y verás que el detector se vuelve más sensible: encuentra el pico, pero también empieza a marcar días normales (falsos positivos). Ese equilibrio es la decisión central del método."
      onReset={() => {
        setMagnitud(2.5);
        setUmbralZ(3);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Magnitud del pico plantado"
            valor={magnitud}
            min={1.5}
            max={5}
            step={0.1}
            formato={(v) => `${v}× lo normal`}
            onChange={setMagnitud}
          />
          <ControlSlider
            etiqueta="Umbral de detección (z)"
            valor={umbralZ}
            min={1.5}
            max={4}
            step={0.1}
            formato={(v) => `${v.toFixed(1)} desvíos`}
            onChange={setUmbralZ}
          />
          <p className="rounded-lg bg-secondary/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            Días marcados: {nDetectadas} · falsos positivos: {falsosPositivos}.
            Un día anómalo no es un incendio confirmado ni una predicción: es
            una señal para mirar con más atención.
          </p>
        </>
      }
    >
      <div className="h-72 rounded-xl border border-border bg-[#fffdfb] p-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="dia"
              tick={{ fill: "#82766d", fontSize: 10 }}
              stroke="#e4d5c6"
              interval={9}
            />
            <YAxis tick={{ fill: "#82766d", fontSize: 10 }} stroke="#e4d5c6" />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#82766d" }}
              labelFormatter={(d) => `Día ${d}`}
              cursor={{ stroke: "#b7a89c", strokeDasharray: "3 3" }}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: "#82766d" }} />
            <ReferenceLine x={39} stroke="#c4ae97" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="esperado"
              name="Esperado (referencia)"
              stroke="#b7a89c"
              strokeWidth={1.4}
              strokeDasharray="4 3"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="valor"
              name="Observado (sintético)"
              stroke="#c05f2c"
              strokeWidth={1.8}
              dot={false}
            />
            <Scatter
              dataKey="anomalia"
              name="Marcado como anómalo"
              fill="#8a4516"
              shape="triangle"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </MarcoSim>
  );
}

// ---------------------------------------------------------------------------
// Módulo 7 — Simulación de escenarios futuros
// ---------------------------------------------------------------------------

export function SimEscenarios() {
  const [horizonte, setHorizonte] = useState(30);
  const [nivel, setNivel] = useState<"bajo" | "medio" | "alto">("medio");
  const [incertidumbre, setIncertidumbre] = useState(0.35);
  const [semilla, setSemilla] = useState(97);

  const serie = useMemo(
    () =>
      generarEscenario({ horizonteDias: horizonte, nivel, incertidumbre, semilla }),
    [horizonte, nivel, incertidumbre, semilla],
  );

  const datos = serie.map((p) => ({
    dia: p.dia + 1,
    central: p.central,
    banda: p.techo,
    bandaPiso: p.piso,
  }));

  return (
    <MarcoSim
      titulo="7 · Escenarios futuros"
      explicacion="Explorá cómo se vería una proyección: una línea central (lo que el escenario plantea) y una banda de incertidumbre (el rango honesto dentro del cual podría estar la realidad). Esto NO es un pronóstico: no existe ningún modelo validado. Es la representación visual prevista para cuando lo haya."
      onReset={() => {
        setHorizonte(30);
        setNivel("medio");
        setIncertidumbre(0.35);
        setSemilla(Math.floor(Math.random() * 9999));
      }}
      controles={
        <>
          <ControlSlider
            etiqueta="Horizonte"
            valor={horizonte}
            min={7}
            max={90}
            formato={(v) => `${v} días`}
            onChange={setHorizonte}
          />
          <div>
            <label className="mb-1.5 block text-xs font-medium text-foreground">
              Escenario de actividad
            </label>
            <Select value={nivel} onValueChange={(v) => setNivel(v as typeof nivel)}>
              <SelectTrigger className="h-9 rounded-full border-border bg-card text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="bajo">Bajo</SelectItem>
                <SelectItem value="medio">Medio</SelectItem>
                <SelectItem value="alto">Alto</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <ControlSlider
            etiqueta="Incertidumbre"
            valor={incertidumbre}
            min={0.1}
            max={0.8}
            step={0.05}
            formato={(v) => `${Math.round(v * 100)}%`}
            onChange={setIncertidumbre}
          />
          <p className="rounded-lg bg-secondary/60 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            Cuanto más lejos en el tiempo, más ancha suele volverse la banda:
            pretender precisión a 90 días sería deshonesto.
          </p>
        </>
      }
    >
      <div className="h-72 rounded-xl border border-border bg-[#fffdfb] p-3">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="dia"
              tick={{ fill: "#82766d", fontSize: 10 }}
              stroke="#e4d5c6"
              interval={Math.max(1, Math.floor(horizonte / 8))}
            />
            <YAxis tick={{ fill: "#82766d", fontSize: 10 }} stroke="#e4d5c6" />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#82766d" }}
              labelFormatter={(d) => `Día ${d}`}
            />
            <Area
              type="monotone"
              dataKey="banda"
              name="Techo de la banda"
              stroke="none"
              fill="#e9a477"
              fillOpacity={0.25}
            />
            <Area
              type="monotone"
              dataKey="bandaPiso"
              name="Piso de la banda"
              stroke="none"
              fill="#fffdfb"
              fillOpacity={1}
            />
            <Line
              type="monotone"
              dataKey="central"
              name="Línea central del escenario"
              stroke="#c05f2c"
              strokeWidth={2}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </MarcoSim>
  );
}
