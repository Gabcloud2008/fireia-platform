"use client";

// FIREIA — Paraguay Fire Intelligence (M012 — dirección premium).
// SPA en la ruta única "/": la navegación por secciones usa hash (#/vista)
// así la aplicación nunca se recarga. Consumidor de solo lectura de la API
// espejo del pipeline: nada de lo que hagamos acá dispara una ingesta ni
// una operación de red. MotionRoot desactiva las animaciones cuando el
// usuario prefiere movimiento reducido.

import { FireiaDataProvider } from "@/components/fireia/data-provider";
import { useHashRouter } from "@/components/fireia/hash-router";
import { AppShell } from "@/components/fireia/app-shell";
import { MotionRoot } from "@/components/fireia/motion";
import { InicioView } from "@/components/fireia/views/inicio";
import { MapaView } from "@/components/fireia/views/mapa";
import { ObservacionesView } from "@/components/fireia/views/observaciones";
import { ComparacionView } from "@/components/fireia/views/comparacion";
import { EventosView } from "@/components/fireia/views/eventos";
import { HistorialView } from "@/components/fireia/views/historial";
import { AmbientalView } from "@/components/fireia/views/ambiental";
import { AnomaliasView } from "@/components/fireia/views/anomalias";
import { InteligenciaView } from "@/components/fireia/views/inteligencia";
import { SimulacionesView } from "@/components/fireia/views/simulaciones";
import { RiesgoView } from "@/components/fireia/views/riesgo";
import { InformesView } from "@/components/fireia/views/informes";
import { FuentesView } from "@/components/fireia/views/fuentes";
import { MetodologiaView } from "@/components/fireia/views/metodologia";
import { DocumentacionView } from "@/components/fireia/views/documentacion";
import { ProcesamientoView } from "@/components/fireia/views/procesamiento";
import { CalidadView } from "@/components/fireia/views/calidad";
import { TrazabilidadView } from "@/components/fireia/views/trazabilidad";
import { ValidacionView } from "@/components/fireia/views/validacion";
import { EstadoView } from "@/components/fireia/views/estado";
import type { Vista } from "@/components/fireia/nav-config";

const VISTAS: Record<Vista, () => React.JSX.Element> = {
  inicio: InicioView,
  mapa: MapaView,
  observaciones: ObservacionesView,
  comparacion: ComparacionView,
  eventos: EventosView,
  historial: HistorialView,
  ambiental: AmbientalView,
  anomalias: AnomaliasView,
  inteligencia: InteligenciaView,
  simulaciones: SimulacionesView,
  riesgo: RiesgoView,
  informes: InformesView,
  fuentes: FuentesView,
  metodologia: MetodologiaView,
  documentacion: DocumentacionView,
  procesamiento: ProcesamientoView,
  calidad: CalidadView,
  trazabilidad: TrazabilidadView,
  validacion: ValidacionView,
  estado: EstadoView,
};

export default function Home() {
  const { vista } = useHashRouter();
  const VistaActual = VISTAS[vista] ?? InicioView;

  return (
    <MotionRoot>
      <FireiaDataProvider>
        <AppShell vista={vista}>
          <div key={vista} className="fireia-view">
            <VistaActual />
          </div>
        </AppShell>
      </FireiaDataProvider>
    </MotionRoot>
  );
}
