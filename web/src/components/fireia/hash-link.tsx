"use client";

// Enlace interno de la SPA FIREIA: ancla nativa con href="#/vista".
// No usa el router de Next porque pushState no dispara el evento
// hashchange; el ancla nativa sí lo hace y así la vista cambia sin
// recargar la aplicación.

import type { AnchorHTMLAttributes, ReactNode } from "react";

export function HashLink({
  href,
  children,
  ...props
}: {
  href: string;
  children: ReactNode;
} & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a href={href} {...props}>
      {children}
    </a>
  );
}
