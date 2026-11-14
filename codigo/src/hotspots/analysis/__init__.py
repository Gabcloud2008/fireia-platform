"""Análisis: anomalías, baselines y comparación de sensores (Misión 004, etapa 7).

Reglas de esta sección (no negociables):

1. **Separación temporal estricta**: el baseline (entrenamiento) siempre es
   ANTERIOR al período evaluado. Nada de ventanas deslizantes que miren hacia
   adelante (fuga de información).
2. **Baselines simples primero**: cualquier modelo que agreguemos tiene que
   ganarle a "persistencia" y "climatología" para justificarse.
3. **Datos sintéticos marcados**: los experimentos que corremos hoy usan la
   serie sintética del generador de pruebas; sus números demuestran que el
   MÉTODO funciona en condiciones controladas, no que conoce la realidad de
   Paraguay. Cuando haya datos reales del piloto, la misma corrida produce el
   informe real.
4. **Guardas de suficiencia**: si la serie es corta o plana, el detector se
   niega y lo dice — un "sin datos suficientes" explícito vale más que un
   número inventado.
"""
