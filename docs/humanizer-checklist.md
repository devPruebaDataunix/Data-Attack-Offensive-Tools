# Humanizer — que el informe lea como lo escribió un pentester con experiencia

**Por qué.** Un informe que "suena a IA" (relleno, plantilla, vocabulario delator) pierde
credibilidad y el cliente puede descartarlo. Esto **no es engañar a un detector**: es
escribir con la especificidad y el criterio de un profesional. El antídoto contra el "tono
IA" es el mismo que contra el mal informe: concreción anclada en evidencia.

## Lista negra de vocabulario-IA (evitar / sustituir)
No uses por inercia: *delve, profundizar, en el panorama (landscape), aprovechar (harness),
robusto, crucial, fundamental (pivotal), meticuloso, tapiz (tapestry), testimonio de (a
testament to), subrayar (underscore), fomentar, vibrante, integral, sin fisuras (seamless),
en el mundo actual, cabe destacar/es importante señalar, en resumen/en conclusión* (de
relleno).

## Patrones de frase delatores (evitar)
- "No solo X, sino también Y" / "No es X, es Y" en serie.
- Regla de tres por defecto (tres adjetivos/cláusulas encadenadas sin necesidad).
- Sustituir "es/son" por "se erige como / funciona como / cuenta con" sin motivo.
- Abrir frases consecutivas con "Además, / Asimismo, / Por consiguiente, / Más aún,".
- Atribuciones vagas: "los expertos coinciden", "los informes del sector indican".
- Conclusiones formulaicas: "A pesar de estos retos…".

## Puntuación y formato
- No abuses de la raya (—) ni del **negrita en cada término**.
- Comillas rectas, no tipográficas.
- Encabezados en mayúscula de frase, no Tipo Título En Cada Palabra.
- No metas una línea horizontal antes de cada encabezado.
- Las listas "**Término**: descripción" en cadena son un tell: úsalas con mesura.

## Estructura y ritmo
- **Varía la longitud de las frases** (burstiness). Alterna frases cortas y largas. La
  uniformidad robótica es el delator nº1.
- No todo tiene que ser una lista con viñetas. Usa prosa donde el argumento fluye.
- Evita el párrafo "resumen de lo dicho" al final de cada sección.

## Tono
- **Voz activa** y sujeto concreto: "El servidor expone…", no "Es expuesto por el servidor…".
- Cero lenguaje promocional ("solución potente", "enfoque integral").
- Específico > genérico: nombres de host, rutas, parámetros, versiones, líneas de evidencia.
  La especificidad es lo que un humano experto aporta y la IA genérica no.
- Prueba del "¿lo diría en voz alta?": si no, reescríbelo como lo dirías.

## Regla práctica para el agente
Tras redactar un hallazgo, **autorrevisa contra esta lista**: borra la mitad de las
transiciones, sustituye cualquier palabra de la lista negra, ancla cada frase en un dato
concreto de la evidencia, y rompe la uniformidad de longitud. Si una frase no aporta un dato
o una acción, elimínala.

> Nota: el objetivo es calidad profesional y credibilidad, dentro de un informe veraz para
> un cliente que autorizó el test. No se trata de ocultar autoría ni de falsear nada.
