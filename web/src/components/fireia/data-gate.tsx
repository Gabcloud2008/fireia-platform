"use client";

// Portón de datos: mientras el almacén carga muestra un esqueleto; si falla,
// muestra el error y un botón de reintento. Evita repetir esa lógica en cada
// vista de FIREIA.

import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useFireia, type DatosMVP } from "./data-provider";

export type { DatosMVP };

export function PageSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Cargando datos">
      <div className="flex items-start gap-3.5">
        <Skeleton className="size-11 rounded-xl" />
        <div className="space-y-2 pt-1">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  );
}

export function ErrorAlmacen({
  mensaje,
  onRetry,
}: {
  mensaje: string;
  onRetry: () => void;
}) {
  return (
    <Card className="border-[#ecc7b3] bg-[#fdf1ea] shadow-none">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <div
          className="flex size-12 items-center justify-center rounded-2xl bg-[#f7dfd2] text-[#b5543b]"
          aria-hidden
        >
          <AlertTriangle className="size-6" />
        </div>
        <h3 className="text-base font-semibold text-foreground">
          No pudimos cargar el almacén de datos
        </h3>
        <p className="max-w-md break-all text-sm leading-relaxed text-muted-foreground">
          {mensaje}
        </p>
        <Button onClick={onRetry} variant="outline" className="gap-2">
          <Loader2 className="size-4" aria-hidden />
          Reintentar
        </Button>
      </CardContent>
    </Card>
  );
}

export function DataGate({
  children,
}: {
  children: (datos: DatosMVP) => ReactNode;
}) {
  const { datos, error, cargando, reintentar } = useFireia();

  if (cargando && !datos) return <PageSkeleton />;
  if (!datos && error) return <ErrorAlmacen mensaje={error} onRetry={reintentar} />;
  if (!datos) return null;

  return <>{children(datos)}</>;
}
