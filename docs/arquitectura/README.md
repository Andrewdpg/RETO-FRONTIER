# Arquitectura

El modelo está en `arquitectura.c4` (LikeC4). Los diagramas van en el orden en que conviene leerlos: primero el reemplazo por dentro, después lo que lo rodea.

1. **Reemplazo por dentro** — [`png/reemplazo.png`](png/reemplazo.png). Muestra cada componente del router y del motor de reglas con el error que emite, y dónde se lee y escribe el estado. Importa porque es lo que se evalúa: si una caja emite el error equivocado o en otro orden, el test falla.
2. **Contexto** — [`png/contexto.png`](png/contexto.png). Muestra quién habla con quién: el set de evaluación con el reemplazo, y el equipo con el original a través del laboratorio. Importa porque deja claro que el reemplazo nunca llama al original, que es la regla que anula el set si se rompe.
3. **Laboratorio** — [`png/laboratorio.png`](png/laboratorio.png). Muestra el arnés, el generador diferencial, el comparador, el buscador de control, el log y los evals. Importa porque es como medimos la fidelidad todo el día sin gastar las 3 corridas del set oculto.
4. **Despliegue** — [`png/despliegue.png`](png/despliegue.png). Muestra el reemplazo en una sola instancia de Cloud Run con el estado en memoria, y el laboratorio en las laptops. Importa porque la decisión D1 (una instancia, sin base de datos) se ve acá.
5. **Canario de las 15:30** — [`png/canario.png`](png/canario.png). Muestra el replay cada 10 minutos, el diferencial del área afectada cuando aparece un cambio y el buscador de control si aparecen E202 nuevos. Importa porque el incidente se califica por detectarlo, adaptarse y explicarlo.

El orden de validación (qué revisa cada estación, qué error da y qué línea del log prueba su lugar) está como tabla en `../DESIGN.md`, sección 3.11.
