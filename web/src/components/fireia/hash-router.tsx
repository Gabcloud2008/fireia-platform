"use client";

// Micro-router por hash para la SPA de FIREIA (M012). La plataforma vive en
// la ruta única "/" del App Router; las secciones se representan con
// "#/vista" para que el botón atrás/adelante del navegador funcione y la
// navegación nunca recargue la aplicación.

import { useCallback, useEffect, useState } from "react";

import { ALIAS_VISTAS, VISTAS_VALIDAS, type Vista } from "./nav-config";

function vistaDesdeHash(): Vista {
  if (typeof window === "undefined") return "inicio";
  const h = decodeURIComponent(window.location.hash).replace(/^#\/?/, "");
  const resuelta = ALIAS_VISTAS[h] ?? h;
  return VISTAS_VALIDAS.has(resuelta) ? (resuelta as Vista) : "inicio";
}

export function useHashRouter() {
  const [vista, setVista] = useState<Vista>("inicio");

  useEffect(() => {
    const onHash = () => setVista(vistaDesdeHash());
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navegar = useCallback((v: Vista) => {
    if (`#/${v}` === window.location.hash) {
      setVista(v);
      return;
    }
    window.location.hash = `#/${v}`;
  }, []);

  return { vista, navegar };
}
