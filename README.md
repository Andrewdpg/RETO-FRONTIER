# Reemplazo de la caja negra

Responde igual que el servicio original del reto 2 en su versión 2 (la vigente desde el incidente de las 15:30): mismo status y mismo cuerpo en `POST /msg`, `POST /__reset`, `GET /health` y cualquier otra ruta. Es Node 26 con `node:http` y sin dependencias (D6). El estado vive en memoria, así que corre en una sola instancia (D1).

## Correrlo local

Hace falta Node 26. Crear un `.env` en la raíz:

```
TEAM_ENTRYPOINT_TOKEN=<token del equipo>
PORT=8080
BLACK_BOX_URL=<url del servicio original>
```

`PORT` es opcional (por defecto 8080). `BLACK_BOX_URL` solo la usan las evals, para negarse a correr contra el original.

```
node --env-file=.env src/server.ts
```

Todo request lleva `Authorization: Bearer <token>`. Sin el token, el servicio responde lo mismo que el original sin token.

## Evals

Las dos comparan como el set oculto: status igual y, si ambos cuerpos son JSON, el mismo JSON sin importar el orden de las claves; si no, el texto exacto.

```
node --env-file=.env evals/run.ts http://localhost:8080
node --env-file=.env evals/paralelo.ts http://localhost:8080
```

- `run.ts` (E-01) reproduce cada secuencia de `experimentos.jsonl` y da el % de pasos y de secuencias iguales. Con `--sin-espera` saltea los pasos 495–497, que esperan 10 minutos. El log tiene líneas de las dos versiones; para medir solo lo grabado contra la v2: `--desde 2026-10-10T20:57:00Z`. Sin ese corte, las líneas de la v1 difieren donde cambió el servicio.
- `paralelo.ts` (E-10) reproduce las ráfagas en paralelo del log 175–204 y compara el estado final: saldos, ids y cuántos 200, E507 y E510. Esas líneas son de la v1: contra la v2 solo difieren el formato del saldo y el 423 de E510.

Cada corrida deja un archivo con hora en `evals/results/`, con una línea `id | seq | esperado | obtenido` por diferencia. No correr las dos a la vez: comparten el estado del token.

## Deploy

El entrypoint corre en Railway con la v2, desde el `Dockerfile` de la raíz:

```
railway up
```

En el servicio de Railway: la variable `TEAM_ENTRYPOINT_TOKEN`, 1 réplica y sin sleep (el estado vive en memoria). Railway pone `PORT`.

Alternativa en Cloud Run:

```
./deploy.sh
```

Pide `gcloud` con un proyecto activo y facturación, y `TEAM_ENTRYPOINT_TOKEN` en `.env`, que sube a Secret Manager. Antes de desplegar pide confirmación. El servicio queda con min=1 y max=1. Al final llama a `/health` con el token y muestra la URL.

## Lo demás

- `docs/DESIGN.md`: diseño, catálogo del servicio (§3) y decisiones (§7).
- `SPEC.md`: especificación del original, cada comportamiento con su línea del log.
- `experimentos.jsonl`: el log de experimentos. No se edita a mano: lo genera `python3 lab/logs.py armar` a partir de `logs/t1.jsonl` y `logs/t2.jsonl`.
- `lab/`: herramientas del laboratorio (sondas, canario, escáner del control).
- `DECISIONS.md`: decisiones con hora y quién las tomó.
