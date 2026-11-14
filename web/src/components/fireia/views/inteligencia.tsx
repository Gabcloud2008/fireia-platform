"use client";

// Centro de inteligencia (v3 — conversación primero): el chat ocupa la
// pantalla; el estado de demostración vive en el encabezado, no en una
// tarjeta-banner. Reglas deterministas locales, cero red, cero modelo.

import { useEffect, useRef, useState } from "react";
import {
  Database,
  RotateCcw,
  Send,
  ShieldQuestion,
} from "lucide-react";

import { useFireia } from "@/components/fireia/data-provider";
import { HeroCompacto } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  conversacionService,
  SUGERENCIAS_CONSULTA,
  type RespuestaConversacional,
} from "@/lib/fireia/services/conversacion";

interface Mensaje {
  autor: "usuario" | "fireia";
  texto: string;
  referencias?: RespuestaConversacional["referencias"];
}

const MENSAJE_INICIAL: Mensaje = {
  autor: "fireia",
  texto:
    "Hola, soy el centro de inteligencia de FIREIA. Estoy en modo demostración local: respondo con reglas simples sobre el almacén cargado, sin ninguna IA conectada. Preguntame por detecciones, departamentos, eventos, intensidad o calidad; o tocá una sugerencia para empezar.",
};

export function InteligenciaView() {
  const { datos } = useFireia();
  const [mensajes, setMensajes] = useState<Mensaje[]>([MENSAJE_INICIAL]);
  const [consulta, setConsulta] = useState("");
  const [pensando, setPensando] = useState(false);
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [mensajes, pensando]);

  const enviar = (texto: string) => {
    const t = texto.trim();
    if (!t || !datos || pensando) return;
    setMensajes((m) => [...m, { autor: "usuario", texto: t }]);
    setConsulta("");
    setPensando(true);
    // pequeña pausa natural; la respuesta es local y determinista
    window.setTimeout(() => {
      const r = conversacionService.responder(t, datos);
      setMensajes((m) => [
        ...m,
        { autor: "fireia", texto: r.texto, referencias: r.referencias },
      ]);
      setPensando(false);
    }, 450);
  };

  const reiniciar = () => {
    setMensajes([MENSAJE_INICIAL]);
    setConsulta("");
  };

  return (
    <div className="space-y-4">
      <HeroCompacto
        indice="01"
        categoria="Inteligencia · consultá"
        title="Preguntale a la plataforma"
        lede="Consultas en lenguaje sencillo sobre lo que FIREIA sabe: qué se detectó, dónde, con qué calidad y qué significa cada término."
        actions={
          <Badge className="gap-1.5 rounded-full border-transparent bg-[#fdf3ec] px-3 py-1.5 text-[11px] font-semibold text-flame">
            <span className="fireia-pulse inline-block size-1.5 rounded-full bg-flame" aria-hidden />
            Modo demostración local · sin IA conectada
          </Badge>
        }
      />

      <div className="mx-auto flex max-w-3xl flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-[0_20px_50px_-30px_rgb(57_51_47/0.3)]">
        {/* --- conversación --- */}
        <div
          className="h-[54vh] min-h-[380px] space-y-4 overflow-y-auto px-4 py-6 sm:px-6"
          aria-live="polite"
          aria-label="Conversación"
        >
          {mensajes.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.autor === "usuario" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed sm:max-w-[78%] ${
                  m.autor === "usuario"
                    ? "rounded-br-md bg-action text-white"
                    : "rounded-bl-md border border-border bg-[#fffdfb] text-foreground"
                }`}
              >
                <p className="whitespace-pre-wrap">{m.texto}</p>
                {m.referencias && m.referencias.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-border/70 pt-2">
                    {m.referencias.map((ref, j) => (
                      <span
                        key={j}
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          m.autor === "usuario"
                            ? "bg-white/15 text-white"
                            : "bg-secondary text-muted-foreground"
                        }`}
                      >
                        <Database className="size-2.5" aria-hidden />
                        {ref.etiqueta}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {pensando && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-border bg-[#fffdfb] px-4 py-3.5">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="size-1.5 animate-bounce rounded-full bg-flame/70"
                    style={{ animationDelay: `${d * 120}ms` }}
                    aria-hidden
                  />
                ))}
                <span className="sr-only">Buscando la respuesta…</span>
              </div>
            </div>
          )}
          <div ref={finRef} />
        </div>

        {/* --- sugerencias --- */}
        <div className="flex gap-2 overflow-x-auto border-t border-border bg-secondary/40 px-4 py-2.5 sm:px-6">
          {SUGERENCIAS_CONSULTA.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => enviar(s)}
              className="shrink-0 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground outline-none transition-colors hover:border-[#ecc7b3] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            >
              {s}
            </button>
          ))}
        </div>

        {/* --- campo de consulta --- */}
        <form
          className="flex items-center gap-2 border-t border-border px-4 py-3 sm:px-6"
          onSubmit={(e) => {
            e.preventDefault();
            enviar(consulta);
          }}
        >
          <ShieldQuestion
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden
          />
          <input
            value={consulta}
            onChange={(e) => setConsulta(e.target.value)}
            placeholder="Escribí tu consulta sobre los datos…"
            aria-label="Campo de consulta"
            className="h-11 min-w-0 flex-1 rounded-full border border-border bg-background px-4 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button
            type="submit"
            size="icon"
            disabled={!consulta.trim() || pensando}
            aria-label="Enviar consulta"
            className="size-11 shrink-0 rounded-full bg-action text-white hover:bg-[#a94f22]"
          >
            <Send className="size-4" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={reiniciar}
            aria-label="Reiniciar conversación"
            className="size-11 shrink-0 rounded-full text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <RotateCcw className="size-4" aria-hidden />
          </Button>
        </form>
      </div>

      <p className="text-center text-[11px] leading-relaxed text-muted-foreground/85">
        Cuando exista la integración conversacional real, este aviso desaparecerá.
        Las respuestas se generan siempre desde el almacén cargado.
      </p>
    </div>
  );
}
