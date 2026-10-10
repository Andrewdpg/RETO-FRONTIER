"""Única puerta al servicio original: cada request que sale por aquí queda en experimentos.jsonl.

    BB_TOKEN=... BB_TAG=t2 BB_LOG=logs/t2.jsonl python3 lab/send.py lab/probes/001-entrada.jsonl [--dry]

BB_TAG identifica el token sin nombrarlo (t1, t2): va en cada línea y como prefijo de la secuencia, así
los dos logs del equipo se pueden juntar sin que choquen las secuencias. Los ids no chocan porque cada
token escribe en su propio archivo y rango (ver lab/logs.py).

Cada línea de una tanda es una sonda: {"hipotesis": "...", "m": "PING;64"}. La hipótesis es
obligatoria porque el log la exige y la spec cita estas líneas. Otras claves: "body", "raw",
"method", "path", "auth" ("ok" por defecto, "none", o el valor literal del header, donde {token}
se reemplaza por el token sin que llegue al log), "content_type" (null lo omite), "conclusion",
"headers" (true guarda los headers de la respuesta en la línea del log).
{"reset": true, "hipotesis": "..."} abre una secuencia nueva.
"""
import fcntl
import http.client
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("BB_URL", "https://caja-negra-production-c64f.up.railway.app")
TAG = os.environ.get("BB_TAG", "")
ID_START = {"t1": 1, "t2": 10001}
LOG = Path(os.environ.get("BB_LOG", Path(__file__).resolve().parent.parent / "logs" / f"{TAG or 'sin-tag'}.jsonl"))
MIN_GAP = 1 / 8  # el tope es 10 rps; el margen es para otros scripts con el mismo token
DAILY_LIMIT = 8000
DAILY_WARN = 7000
JSON_CT = "application/json"
PROBE_KEYS = {"hipotesis", "reset", "m", "body", "raw", "method", "path", "auth", "content_type",
              "conclusion", "headers"}


def opened_by_reset(entry):
    return (entry.get("metodo"), entry.get("ruta")) == ("POST", "/__reset") \
        and isinstance(entry["status"], int) and 200 <= entry["status"] < 300


class Client:
    def __init__(self):
        self.token = os.environ.get("BB_TOKEN")
        if not self.token:
            sys.exit("falta BB_TOKEN")
        # Dos send.py a la vez repetirían ids (cada uno lee el último al arrancar) y un reset
        # borraría el estado de la secuencia que el otro está explorando con el mismo token.
        self._lock = open(LOG.with_suffix(".lock"), "w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit("hay otro send.py corriendo con este log: espera a que termine")
        rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []
        self.sent = len(rows)
        # Cada token tiene su rango (t1 desde 1, t2 desde 10001): aunque su archivo esté vacío, sus ids
        # nunca caen en el rango del otro.
        self.next_id = max(max((r["id"] for r in rows), default=0) + 1, ID_START.get(TAG, 1))
        if not TAG:
            sys.exit("falta BB_TAG (t1 o t2)")
        # Solo cuentan las secuencias de este formato; las importadas de antes tienen otros nombres.
        seqs = [int(m.group(1)) for r in rows if (m := re.fullmatch(rf"{TAG}-s(\d+)", str(r["seq"])))]
        self.seq_n = max(seqs, default=0)
        self.seq = f"{TAG}-s{self.seq_n}" if self.seq_n else None
        # Una secuencia sin reset exitoso, o con un request cuyo efecto no se vio, tiene un estado
        # desconocido: lo que se mande después ya no es evidencia.
        current = [r for r in rows if r["seq"] == self.seq]
        self.dirty = bool(current) and (not opened_by_reset(current[0]) or any("error" in r for r in current))
        self.last = 0.0

    def reset(self, hipotesis="estado inicial limpio", conclusion=None):
        self.seq_n += 1
        self.seq = f"{TAG}-s{self.seq_n}"
        self.dirty = False
        entry = self.send(hipotesis, path="/__reset", conclusion=conclusion)
        if not opened_by_reset(entry):
            sys.exit(f"reset respondió {entry['status']}: la secuencia {self.seq} no está limpia")
        return entry

    def send(self, hipotesis, method="POST", path="/msg", m=None, body=None, raw=None,
             auth="ok", content_type=JSON_CT, conclusion=None, headers=False):
        if self.seq is None:
            sys.exit("antes de la primera sonda hace falta un reset: abre una secuencia")
        if self.dirty:
            sys.exit(f"la secuencia {self.seq} quedó contaminada: la tanda tiene que empezar con un reset")
        if self.sent >= DAILY_LIMIT:
            sys.exit(f"{self.sent} requests en el log: tope diario de {DAILY_LIMIT}")
        if m is not None:
            body = {"m": m}
        data = raw.encode() if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {}
        if data is not None and content_type is not None:
            headers["Content-Type"] = content_type
        if auth == "ok":
            headers["Authorization"] = f"Bearer {self.token}"
        elif auth != "none":
            headers["Authorization"] = auth.replace("{token}", self.token)

        entry = {
            "id": self.next_id,
            "seq": self.seq,
            "token": TAG,
            "x_req": None,
            "hipotesis": hipotesis,
            "request": body if raw is None else raw,
            "status": None,
            "response": None,
            # La sección 6 de la spec pide desde cuándo cambió el servicio: sin hora no se responde.
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        # El formato del README solo habla de POST /msg con el token propio: los campos extra
        # aparecen únicamente cuando la sonda se sale de ese caso.
        if method != "POST" or path != "/msg":
            entry["metodo"], entry["ruta"] = method, path
        if auth != "ok":
            entry["auth"] = auth
        if content_type != JSON_CT:
            entry["content_type"] = content_type
        if conclusion:
            entry["conclusion"] = conclusion

        try:
            status, resp_headers, text = self._send_within_rate(method, path, data, headers)
        except (OSError, http.client.HTTPException) as e:
            # El request pudo llegar y cambiar el estado sin que viéramos la respuesta.
            entry["error"] = f"{type(e).__name__}: {e}"
            self._append(entry)
            sys.exit(f"{entry['id']} {entry['error']}: la secuencia {self.seq} queda contaminada")

        try:
            entry["response"] = json.loads(text)
        except ValueError:
            entry["response"] = text
        x_req = resp_headers.get("X-Req")
        entry["x_req"] = int(x_req) if x_req and x_req.isdigit() else x_req
        entry["status"] = status
        # Solo en las sondas que buscan qué stack hay detrás: el resto del log queda con el formato del README.
        if headers:
            entry["headers"] = dict(resp_headers.items())
        self._append(entry)
        return entry

    def _send_within_rate(self, method, path, data, headers):
        for attempt in range(4):
            wait = MIN_GAP - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            status, resp_headers, text = self._http(method, path, data, headers)
            # La respuesta de rate limit es de la infraestructura: no es evidencia del servicio.
            if resp_headers.get("X-Frontier-Infra") == "rate-limit":
                time.sleep(1 + attempt)
                continue
            return status, resp_headers, text
        sys.exit("rate limit persistente: para y revisa el presupuesto")

    def _append(self, entry):
        with LOG.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.next_id += 1
        self.sent += 1
        if self.sent == DAILY_WARN:
            print(f"aviso: {self.sent} de {DAILY_LIMIT} requests del día", file=sys.stderr)

    def _http(self, method, path, data, headers):
        # http.client y no urllib: urllib sigue las redirecciones (reenviando el token) e inventa un
        # Content-Type cuando falta, y las dos cosas son justo lo que hay que observar.
        url = urllib.parse.urlsplit(BASE)
        conn_cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(url.netloc, timeout=10)
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.headers, resp.read().decode("utf-8", errors="replace")
        finally:
            conn.close()


def run(path, dry):
    probes = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    for i, p in enumerate(probes, 1):
        if "hipotesis" not in p:
            sys.exit(f"{path}:{i} sin hipotesis")
        # Una clave mal escrita revienta a mitad de tanda y deja la secuencia a medias.
        if unknown := set(p) - PROBE_KEYS:
            sys.exit(f"{path}:{i} claves desconocidas: {sorted(unknown)}")
    if dry:
        for p in probes:
            # Un m de 100.000 caracteres haría ilegible la revisión: se muestra el tamaño y el inicio.
            print(json.dumps({k: v if k == "hipotesis" or len(str(v)) <= 150
                              else f"{str(v)[:60]}… ({len(str(v))} car.)" for k, v in p.items()},
                             ensure_ascii=False))
        print(f"{len(probes)} sondas, nada enviado")
        return
    client = Client()
    for i, p in enumerate(probes, 1):
        if client.token in str(p.get("auth", "")):
            sys.exit(f"{path}:{i} el token va como {{token}}, no escrito en la sonda")
    for p in probes:
        p = dict(p)
        if p.pop("reset", False):
            e = client.reset(p["hipotesis"], p.get("conclusion"))
        else:
            e = client.send(**p)
        print(e["id"], e["seq"], e["status"], json.dumps(e["response"], ensure_ascii=False)[:100])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry"]
    if len(args) != 1:
        sys.exit(__doc__)
    run(args[0], "--dry" in sys.argv)
