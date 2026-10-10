# Decisiones

Las decide una persona. El agente propone; si una fila la eligió el agente, se marca `(agente)` hasta que alguien la revise.

| Hora | Decisión | Alternativas descartadas y por qué | Quién |
|---|---|---|---|
| 11:17 | D1. El reemplazo guarda su estado en memoria y corre en una sola instancia de Cloud Run (min=1, max=1). Esto cambia el stack de `AGENTS.md`, que pedía Neon y de 1 a 3 instancias. | Neon con 1 a 3 instancias: el README dice que el set le habla a un solo proceso y que llama `/__reset` antes de cada test, así que no hay estado que deba sobrevivir ni que compartir. Neon agregaría latencia de red y un punto de falla externo para guardar unos pocos KB. | Andres Parra |
| 11:33 | D2. Reglas declarativas: una tabla de comandos (aridad, tipo de cada argumento, reglas contra el estado, efecto y respuesta) y una lista ordenada de validaciones que reproduce el orden de errores medido. | `if` encadenados por comando: un cambio a las 15:30 (un código, un límite, el orden de dos errores) obligaría a rastrear la lógica en varios lugares; con la tabla es una fila y el orden queda escrito en un solo sitio. | Andres Parra |
| 11:33 | D3. El reemplazo no usa LLM. Esto cambia el stack de `AGENTS.md`, que preveía el pi SDK con OpenRouter. | LLM de respaldo para lo desconocido: la comparación es exacta, carácter por carácter; un LLM no es determinista, cuesta dinero y arriesga el límite de 5 s por paso. Para lo que no medimos aplicamos un supuesto escrito en la especificación. | Andres Parra |
| 11:33 | D4 (reemplazada por D8). Canario: cada 10 minutos desde las 15:00, `arnes.ts replay` de unos 45 requests que tocan cada error y cada comando, comparados con el log. Cuando el canario detecta un cambio, se corre el diferencial completo sobre el área afectada (el comando o la etapa del pipeline donde apareció la diferencia). | Repetir el log completo cada vez: cuesta unos 350 requests por corrida y no agrega detección; el canario detecta en 10 minutos o menos con unos 1.350 requests en la tarde. | Andres Parra |
| 12:45 | D7. Un log por token (`logs/t1.jsonl`, `logs/t2.jsonl`) en rangos de ids separados (t1 desde 1, t2 desde 10001), `lab/send.py` como único arnés y `experimentos.jsonl` generado con `lab/logs.py armar`. El log del token 2 de la mañana se renumeró +10000 con `id_original`. | Un solo archivo escrito por los dos: conflictos de git e ids repetidos. Renumerar todo seguido: rompe las citas del diseño. | Equipo |
| 12:45 | D8. Canario desde las 13:00 cada 20 minutos, y a las 19:45 y 19:55, contra la última línea base aceptada. Reemplaza a D4. | D4 (cada 10 minutos desde las 15:00): el servicio puede cambiar sin aviso y más de una vez, y empezar a las 15:00 dejaba ciego el mediodía. | Equipo |
| 12:50 | D6. Node 26 con `node:http` sin dependencias, en Cloud Run (min=1, max=1). Regla fijada antes de medir: si la huella del original dice Python, Python; si no, Node. | Python con `http.server` en Railway: la huella apunta a JavaScript con router propio (NaN/Infinity → E100, 1e400 aceptado, `M` → E102, `charset=utf-8`, sin ETag ni X-Powered-By, `HEAD /health` → 404; log 73, 10960–10973). Frameworks (Express, Fastify, Flask, FastAPI): agregan 405, redirecciones y HEAD/OPTIONS automáticos que el original no tiene. | Equipo |
| 13:25 | El token del equipo se lee de `TEAM_ENTRYPOINT_TOKEN`, el mismo nombre en `.env`, en el código y en el secreto de Cloud Run. | Reusar el secreto `TEAM_TOKEN`: tenía el valor de una prueba vieja y `deploy.sh` lo habría dejado. Dos nombres para un mismo valor: uno de los dos termina desactualizado. | Andres Parra |
| 13:45 | Primer deploy: servicio `reemplazo`, revisión `reemplazo-00001-frr`, min=1 y max=1. El startup probe es TCP al puerto 8080 y no llama a `/health`, que sin token daría 401 (verificado con `gcloud run services describe`). | — | Andres Parra |
| 15:05 | El entrypoint pasa de Cloud Run a Railway (servicio `cheerful-generosity`, mismo Dockerfile y mismo commit `924cc96`). El proxy de Railway responde igual que el del original en las 13 sondas de HTTP raro (log 500–512); el de Cloud Run difiere en `//msg`, `/%6Dsg` y `/msg#x`. | Seguir en Cloud Run y declarar las tres diferencias en la SPEC: el código no puede corregirlas, porque el proxy cambia el request antes de que llegue a Node. | Andres Parra |
| 15:10 | Validación 1 del set contra Railway, commit `924cc96`: **84/100**. Antes: E-01 2.337/2.337 pasos y diferencial 200/200 secuencias (revisión de Cloud Run con el mismo código). La diferencia de 16 puntos supera los 10 de E-11: el set usa comportamientos que ni el log ni el generador cubren. | — | Andres Parra y Aleja |
| 15:20 | Cloud Run queda como blanco de las evals y del diferencial; Railway solo recibe el set y las verificaciones finales. El estado es uno por token: un `diff.py comparar` contra Railway se cruzó con `run.ts` y metió ALTA y HALT ajenos (`evals/results/2026-10-10T20-11-49-352Z.txt`, 95,2 %). | Turnarse sobre la misma URL: depende de coordinarse cada vez. | Andres Parra |
| 16:55 | Reemplazo adaptado a la v2 (`7ff6190`, `d563bcb`): saldo de CONSULTA como texto /100, E510 con 423 e `intentos`, límite de 50.000 entre titulares distintos. Sumamos dos reglas sin estado encontradas después del cambio: mayúsculas del comando solo en ASCII (log 1239–1263) y sugerencia medida en code points (log 1289, 1314). La v2 se detectó con el canario (último verde 15:35:11, primer rojo 15:57:17, log 12565) y la confirmó la repetición de las secuencias de t1 (log 513–1011: 45 diferencias, todas explicadas por los 3 cambios). | — | Andres Parra |
| 16:58 | Nadie pushea a `main` mientras corre una validación: Railway se redespliega con cada push, y el reinicio borra el estado de los tests en curso. | Apagar el autodeploy de Railway: obliga a desplegar a mano y es fácil olvidarlo antes de la final. | Andres Parra |
| 11:33 | D5. Las 3 corridas del set oculto se reservan: una de calibración después del primer deploy completo, una después de adaptarnos al incidente de las 15:30 y una final antes de congelar. El feedback del día a día son las pruebas diferenciales locales contra el original. | Usar el set oculto para iterar: solo hay 3 corridas en todo el día y su resultado es un número sin detalle de qué falló; las diferenciales dicen qué secuencia y qué paso difieren. | Andres Parra |

## Ambigüedades y supuestos

Si una aclaración del staff contradice el brief, vale la aclaración: se anota con su fuente.

| Hora | El brief dice | Pregunta | Definición o supuesto | Fuente | Estado |
|---|---|---|---|---|---|
| 11:33 | "Doc de diseño (una página, pdf o enlace)" | ¿"Una página" limita el largo? | Es el formato de entrega, no un límite de largo. El staff confirmó por Zoom que el doc de diseño no tiene límite de largo. | staff | definido |
| 11:33 | "`GET /health` responde 200 cuando está listo" y "con otro token o sin token, responde como el original" | El original responde 401 a `/health` sin token (log 53). ¿El set llama a `/health` con token? | Supuesto: el set llama a `/health` con el token del equipo. Sin token, el reemplazo responde 401 como el original. | nosotros | pendiente: preguntar al staff |
| 11:33 | "Cada test empieza con `POST /__reset`"; "cada paso tiene 5 segundos" | ¿El set manda los pasos de una secuencia en paralelo? | Supuesto: los manda en serie. El original tiene un solo estado por token, así que con pasos en paralelo ni el original daría respuestas reproducibles. | nosotros | definido |
| 11:33 | "Es el token del equipo que ves en `/evento`" | ¿El reemplazo debe aceptar otros tokens con estados propios? | Solo vale el token del equipo; cualquier otro recibe 401 `E001`. El reemplazo tiene un único estado. | brief | definido |
| 11:33 | Nada sobre la `sugerencia` de E301 | ¿Cómo elige el original la sugerencia? | Levenshtein ≤ 2 sobre el comando en mayúsculas, sin quitar espacios (log 232–241). En un empate gana el primero en orden alfabético: lo confirman cuatro pares de comandos distintos (log 238, 239, 393–398). | nosotros (experimentos) | definido |
| 11:33 | Nada sobre montos máximos | ¿Dónde está el corte del monto válido? | Hasta 10 dígitos: 9.999.999.999 pasa y 10.000.000.000 da E303 (log 369, 370). El saldo acumula sin tope al menos hasta 5.000.000.000 (log 382). | nosotros (experimentos) | definido |

## Cómo trabajamos con los agentes

Qué delegamos, qué verificamos a mano, dónde se equivocó el agente y cómo lo notamos.

- El generador de corpus del agente calcula el control con `toUpperCase()` de JS, que convierte `ß` en `SS`. Por eso el log 222 probó sin querer "ß cuenta como SS" (y el original lo rechazó). El agente lo notó al preparar el experimento siguiente y confirmó con el log 278 que el original descarta la `ß`.

## Con más tiempo

-
