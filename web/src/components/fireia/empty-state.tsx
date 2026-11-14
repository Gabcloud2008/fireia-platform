"use client";

// Estado vacío / no disponible elegante para secciones cuya información
// todavía no entrega el backend. Nunca se simula contenido inexistente.

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";

export function EmptyState({
  icon: Icon,
  title,
  description,
  badge,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  badge?: string;
  children?: ReactNode;
}) {
  return (
    <Card className="border-dashed border-[#e4d5c6] bg-[#fffdfb] shadow-none">
      <CardContent className="flex flex-col items-center gap-3 px-6 py-12 text-center">
        <div
          className="flex size-14 items-center justify-center rounded-2xl bg-secondary text-muted-foreground"
          aria-hidden
        >
          <Icon className="size-7" />
        </div>
        {badge ? (
          <span className="rounded-full bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {badge}
          </span>
        ) : null}
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
        {children}
      </CardContent>
    </Card>
  );
}
