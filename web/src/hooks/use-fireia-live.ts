"use client";

// Misión 016 — FIREIA LIVE · Hook de datos en vivo.
// Se suscribe a Supabase Realtime (tablas operativas publicadas:
// fireia_ingestion_runs, fireia_alerts, fireia_system_health) y expone
// frescura honesta: última adquisición y edad de los datos.
// Sin variables de entorno → enVivo=false y la web sigue con export estático.
import { useCallback, useEffect, useRef, useState } from "react";

import { getSupabase } from "@/lib/supabase-client";

export interface EstadoLive {
  enVivo: boolean;
  ultimaCorrida: {
    run_id: string;
    product: string;
    status: string;
    started_at: string;
    valid: number | null;
  } | null;
  ultimaAdquisicionUtc: string | null;
  edadHoras: number | null;
  alertasNuevas: number;
  refrescar: () => void;
}

export function useFireiaLive(): EstadoLive {
  const [estado, setEstado] = useState<EstadoLive>({
    enVivo: false,
    ultimaCorrida: null,
    ultimaAdquisicionUtc: null,
    edadHoras: null,
    alertasNuevas: 0,
    refrescar: () => {},
  });
  const [tick, setTick] = useState(0);
  const canalRef = useRef<ReturnType<NonNullable<ReturnType<typeof getSupabase>>["channel"]> | null>(null);

  const cargar = useCallback(async () => {
    const sb = getSupabase();
    if (!sb) return;

    const [{ data: corridas, error: e1 }, { data: alertas, error: e2 }, { data: deteccion, error: e3 }] =
      await Promise.all([
        sb
          .from("fireia_ingestion_runs")
          .select("run_id,product,status,started_at,valid")
          .order("started_at", { ascending: false })
          .limit(1),
        sb
          .from("fireia_alerts")
          .select("id", { count: "exact", head: true })
          .eq("review_state", "nueva"),
        sb
          .from("fireia_latest_detections")
          .select("created_at")
          .order("created_at", { ascending: false })
          .limit(1),
      ]);
    if (e1 || e2 || e3) return;

    const ultima = deteccion?.[0]?.created_at ?? null;
    const edad = ultima ? (Date.now() - new Date(ultima).getTime()) / 3_600_000 : null;
    setEstado((prev) => ({
      ...prev,
      enVivo: true,
      ultimaCorrida: corridas?.[0] ?? null,
      ultimaAdquisicionUtc: ultima,
      edadHoras: edad !== null ? +edad.toFixed(1) : null,
      alertasNuevas: alertas ?? 0,
    }));
  }, []);

  useEffect(() => {
    const sb = getSupabase();
    if (!sb) return;
    void cargar();

    const canal = sb
      .channel("fireia-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "fireia_ingestion_runs" }, () => void cargar())
      .on("postgres_changes", { event: "*", schema: "public", table: "fireia_alerts" }, () => void cargar())
      .on("postgres_changes", { event: "*", schema: "public", table: "fireia_system_health" }, () => void cargar())
      .subscribe();
    canalRef.current = canal;

    const intervalo = window.setInterval(() => {
      setTick((t) => t + 1); // recalcula la edad de los datos cada minuto
    }, 60_000);

    return () => {
      void sb.removeChannel(canal);
      window.clearInterval(intervalo);
    };
  }, [cargar, tick === 0]);

  return { ...estado, refrescar: () => void cargar() };
}
