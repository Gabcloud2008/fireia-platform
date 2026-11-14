"use client";

// Primitivas de movimiento de FIREIA (M012), adaptadas de la skill
// motion-web (motion-tokens + build-mode): variantes como constantes,
// transform+opacity únicamente (presupuesto de compositor), springs
// definidos y respeto total a prefers-reduced-motion vía MotionConfig.

import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState, type ReactNode } from "react";

// --- springs (motion-web: snappy para botones, gentle para revelados) ---
export const SPRING = {
  snappy: { type: "spring", stiffness: 350, damping: 28 } as const,
  gentle: { type: "spring", stiffness: 100, damping: 15 } as const,
  default: { type: "spring", stiffness: 200, damping: 22 } as const,
};

// --- easings ---
export const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

// --- variantes de entrada (constantes fuera de componentes) ---
export const rise = {
  hidden: { opacity: 0, y: 18 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: EASE_OUT_EXPO },
  },
};

export const fadeIn = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.4, ease: EASE_OUT_EXPO } },
};

/** Contenedor que escala la aparición de sus hijos (stagger 0.07s). */
export function Stagger({
  children,
  className,
  gap = 0.07,
}: {
  children: ReactNode;
  className?: string;
  gap?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: gap } },
      }}
    >
      {children}
    </motion.div>
  );
}

/** Hijo de <Stagger>: aparece con un pequeño ascenso. */
export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div className={className} variants={rise}>
      {children}
    </motion.div>
  );
}

/** Sección que se revela al entrar en pantalla (una vez). */
export function Reveal({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.section
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      variants={rise}
    >
      {children}
    </motion.section>
  );
}

/** Cifra que crece hasta su valor (corta: 500 ms; inmóvil si reduced-motion). */
export function CountUp({
  valor,
  duracionMs = 500,
  formato,
  className,
}: {
  valor: number;
  duracionMs?: number;
  formato?: (n: number) => string;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const [mostrado] = useCountUpState(valor, duracionMs, reduced);
  const fmt = formato ?? ((n: number) => new Intl.NumberFormat("es-PY").format(n));
  return <span className={className}>{fmt(mostrado)}</span>;
}

function useCountUpState(
  valor: number,
  duracionMs: number,
  reduced: boolean | null,
) {
  // Valor final inmediato con motion reducido: sin estados en cascada.
  const [mostrado, setMostrado] = useState(reduced ? valor : 0);
  useEffect(() => {
    if (reduced) return;
    const inicio = performance.now();
    const desde = 0;
    let raf = 0;
    const paso = (t: number) => {
      const p = Math.min((t - inicio) / duracionMs, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setMostrado(Math.round(desde + (valor - desde) * eased));
      if (p < 1) raf = requestAnimationFrame(paso);
    };
    raf = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(raf);
  }, [valor, duracionMs, reduced]);
  return [mostrado, setMostrado] as const;
}

/** Raíz de movimiento: desactiva animaciones si el usuario lo prefiere. */
export function MotionRoot({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

export { motion };
