"use client";

// Proveedor de datos de FIREIA (M012): delega la carga en el servicio del
// almacén (adaptador HTTP contra la API espejo existente) y comparte el
// resultado entre todas las vistas de la SPA. Consumidor de solo lectura —
// ninguna acción aquí dispara una ingesta ni una operación de red hacia FIRMS.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  almacenService,
  type DatosMVP,
} from "@/lib/fireia/services/almacen";

export type { DatosMVP };

interface FireiaContexto {
  datos: DatosMVP | null;
  error: string | null;
  cargando: boolean;
  reintentar: () => void;
}

const Ctx = createContext<FireiaContexto | null>(null);

export function FireiaDataProvider({ children }: { children: ReactNode }) {
  const [datos, setDatos] = useState<DatosMVP | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let cancelado = false;
    almacenService
      .cargarTodo()
      .then((d) => {
        if (cancelado) return;
        setDatos(d);
        setCargando(false);
      })
      .catch((e: unknown) => {
        if (cancelado) return;
        setError(e instanceof Error ? e.message : String(e));
        setCargando(false);
      });
    return () => {
      cancelado = true;
    };
  }, [intento]);

  const reintentar = useCallback(() => {
    setCargando(true);
    setError(null);
    setIntento((n) => n + 1);
  }, []);

  return (
    <Ctx.Provider value={{ datos, error, cargando, reintentar }}>
      {children}
    </Ctx.Provider>
  );
}

export function useFireia(): FireiaContexto {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error(
      "useFireia debe usarse dentro de <FireiaDataProvider> (M012).",
    );
  }
  return ctx;
}
