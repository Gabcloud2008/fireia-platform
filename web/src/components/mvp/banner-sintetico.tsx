"use client";

// Banner permanente de honestidad (M012, tema claro): el almacén está
// cargado con fixtures. No se cierra ni se minimiza — si la plataforma
// muestra datos, muestra esto.

import { AlertTriangle, Database } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export function BannerSintetico({
  dataSource,
  nota,
}: {
  dataSource: string;
  nota: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-[#ecc7b3] bg-[#fdf3ec] px-4 py-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="size-5 shrink-0 text-flame" aria-hidden />
          <span className="text-sm font-semibold tracking-wide text-[#8a4516]">
            Datos de demostración
          </span>
          <Badge
            variant="outline"
            className="border-[#ecc7b3] bg-transparent text-[11px] text-[#8a4516]"
          >
            <Database className="mr-1 size-3" aria-hidden />
            origen: {dataSource}
          </Badge>
        </div>
        <p className="text-xs leading-relaxed text-[#a3765a] sm:ml-auto sm:max-w-xl sm:text-right">
          {nota}
        </p>
      </div>
    </div>
  );
}
