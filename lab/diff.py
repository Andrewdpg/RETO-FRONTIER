"""Diferencial: secuencias con la forma del set, grabadas en el original y reproducidas contra el reemplazo.

    python3 lab/diff.py generar [--semilla N]          # escribe lab/probes/NNN-diff-sN.jsonl y muestra el --dry
    BB_TOKEN=... python3 lab/diff.py grabar ARCHIVO     # pausa el canario, la manda con send.py y lo despausa
    REPL_URL=... REPL_TOKEN=... python3 lab/diff.py comparar [--semilla N] [--canario] [--log L --seq S ...]
    python3 lab/diff.py cambios --semilla N            # primera grabación contra la última, para ver qué cambió

Cada tanda tiene 100 secuencias como el set: 40 de 1 paso, 45 de 2 a 5 y 15 de 6 a 12, cada una tras un reset.
Cerca del 70 % de los pasos son mensajes bien formados (control correcto, aridad e ids que existen en el
estado de la secuencia) y el resto son mutaciones; si no, la mayoría moriría en E201/E202 y el negocio
quedaría sin probar. El estado se sigue con un modelo del catálogo (DESIGN §3); si el modelo se equivoca,
solo cambia qué se prueba: la verdad es lo que respondió el original.
"""
import argparse
import http.client
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canary import ctl, msg, same  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROBES = ROOT / "lab" / "probes"
LOG = Path(os.environ.get("BB_LOG", ROOT / "logs" / "t2.jsonl"))
# Junto al log: la del log real es la que mira el canario (logs/canario.pausa).
PAUSE = LOG.parent / "canario.pausa"
BUDGET = 3000  # tope del día para el diferencial con t2 (plan, tarea 3)
SHAPE = [1] * 40 + [None] * 45 + [None] * 15
ARITY = {"PING": 0, "ALTA": 1, "CONSULTA": 1, "DEPOSITO": 2, "TRANSFER": 3, "ANULA": 1, "HALT": 1}
AMOUNT = re.compile(r"[1-9]\d{0,9}")
NAMES = ["Ana", "Beto", "Lucia", "Mateo", "José", "Ñandú", "Maria Paz", "X", "007", "Zoe-Lee"]


def err(code, mensaje):
    return {"error": code, "mensaje": mensaje}


class Model:
    """Lo que el catálogo dice del original, lo justo para elegir ids y montos que tengan sentido."""

    # v=2 es el servicio desde las 15:57 (DESIGN 3.12); v=1 sirve para revisar lo grabado antes.
    def __init__(self, v=2):
        self.v = v
        self.saldo, self.racha, self.titular, self.ops, self.halted = {}, {}, {}, [], False
        self.intentos = {}

    def acct(self, n):
        return f"AC-{n:04d}"

    def apply(self, m):
        if self.halted:
            return 503, err("E599", "service halted")
        if ";" not in m:
            return 400, err("E103", "falta control")
        segs = m.split(";")
        if any(s == "" for s in segs):
            return 400, err("E104", "segmento vacío")
        # Mayúsculas solo en ASCII: "tranſfer" no es TRANSFER (log 1239, 1261).
        cmd = "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in segs[0])
        args, k = segs[1:-1], segs[-1]
        if cmd != "PING":
            if not re.fullmatch(r"\d{1,2}", k):
                return 400, err("E201", "control mal formado")
            if k != ctl(m[:-len(k) - 1]):
                return 400, err("E202", "control inválido")
        if cmd not in ARITY:
            return 400, err("E301", "comando desconocido ")
        if len(args) != ARITY[cmd]:
            return 400, err("E302", "aridad inválida")
        return getattr(self, cmd.lower())(*args)

    def ping(self):
        return 200, {"pong": True}

    def halt(self, a):
        if a != "1":
            return 409, err("E520", "operación destructiva: detiene el servicio; reenvía con confirmación")
        self.halted = True
        return 503, err("E599", "service halted")

    def alta(self, nombre):
        c = self.acct(len(self.saldo) + 1)
        self.saldo[c], self.racha[c], self.titular[c] = 0, 0, nombre
        return 201, {"cuentaId": c}

    def consulta(self, c):
        if c not in self.saldo:
            return 404, err("E401", "cuenta inexistente")
        n = self.saldo[c]
        if self.v == 1:
            return 200, {"cuenta_id": c, "saldo": n}
        # v2: el entero dividido por 100 con dos decimales, como string (12638, 12789).
        return 200, {"cuenta_id": c, "saldo": f"{'-' if n < 0 else ''}{abs(n) // 100}.{abs(n) % 100:02d}"}

    def _op(self, kind, a, b, n):
        self.ops.append({"kind": kind, "a": a, "b": b, "n": n, "anulada": False})
        return 200, {"status": "recieved", "operacionId": f"OP-{len(self.ops):04d}"}

    def deposito(self, c, amt):
        if not AMOUNT.fullmatch(amt):
            return 400, err("E303", "monto inválido")
        if c not in self.saldo:
            return 404, err("E401", "cuenta inexistente")
        self.saldo[c] += int(amt)
        self.racha[c] = 0
        self.intentos[c] = 0
        return self._op("dep", None, c, int(amt))

    def transfer(self, a, b, amt):
        if not AMOUNT.fullmatch(amt):
            return 400, err("E303", "monto inválido")
        if a == b:
            return 400, err("E304", "origen y destino iguales")
        if a not in self.saldo or b not in self.saldo:
            return 404, err("E401", "cuenta inexistente")
        if self.racha[a] >= 3:
            if self.v == 1:
                return 409, err("E510", "cuenta bloqueada")
            self.intentos[a] = self.intentos.get(a, 0) + 1
            return 423, {**err("E510", "cuenta bloqueada"), "intentos": self.intentos[a]}
        n = int(amt)
        # Entre cuentas del mismo titular no hay límite (DESIGN 3.7, log 11782, 11794).
        if n > (100000 if self.v == 1 else 50000) and self.titular[a] != self.titular[b]:
            self.racha[a] += 1
            return 422, err("E506", "límite excedido")
        if self.saldo[a] < n:
            self.racha[a] += 1
            return 422, err("E507", "saldo insuficiente")
        self.saldo[a] -= n
        self.saldo[b] += n
        self.racha[a] = 0
        return self._op("tr", a, b, n)

    def anula(self, op):
        i = int(op[3:]) - 1 if re.fullmatch(r"OP-\d{4}", op) else -1
        if not 0 <= i < len(self.ops):
            return 404, err("E402", "operación inexistente")
        o = self.ops[i]
        if o["anulada"]:
            return 200, {"ok": False, "motivo": "ya anulada"}
        o["anulada"] = True
        if o["a"]:
            self.saldo[o["a"]] += o["n"]
        self.saldo[o["b"]] -= o["n"]
        return 200, {"ok": True, "anulada": op}


class Gen:
    def __init__(self, seed):
        self.r = random.Random(seed)

    def amount(self, model, a=None):
        r, saldo = self.r, model.saldo.get(a, 0)
        return str(r.choice([r.randint(1, 999), r.randint(1000, 100000), 100000, saldo or 1, saldo + 1,
                             max(saldo // 2, 1), 100001]))

    def valid(self, model):
        """Un mensaje bien formado según el estado: (tipo, m)."""
        r, accts = self.r, list(model.saldo)
        if not accts:
            return ("ALTA", msg(f"ALTA;{r.choice(NAMES)}")) if r.random() < 0.85 else ("PING", "PING;64")
        options = ["DEPOSITO"] * 25 + ["TRANSFER"] * (35 if len(accts) > 1 else 0) + ["CONSULTA"] * 15 \
            + ["ALTA"] * 5 + ["PING"] * 5 + ["ANULA"] * (20 if model.ops else 0)
        kind = r.choice(options)
        if kind == "ALTA":
            return kind, msg(f"ALTA;{r.choice(NAMES)}")
        if kind == "PING":
            return kind, "PING;64"
        if kind == "CONSULTA":
            return kind, msg(f"CONSULTA;{r.choice(accts)}")
        if kind == "DEPOSITO":
            return kind, msg(f"DEPOSITO;{r.choice(accts)};{r.choice([r.randint(1, 999), r.randint(1000, 300000)])}")
        if kind == "TRANSFER":
            a, b = r.sample(accts, 2)
            return kind, msg(f"TRANSFER;{a};{b};{self.amount(model, a)}")
        return kind, msg(f"ANULA;OP-{r.randint(1, len(model.ops)):04d}")

    def mutate(self, model):
        r = self.r
        kind, m = self.valid(model)
        body = m.rsplit(";", 1)[0]
        cmd, *args = body.split(";")
        t = r.choice(["control alterado", "control mal formado", "aridad", "monto en el borde", "id inexistente",
                      "minúsculas", "comando cercano", "formato", "anula repetida", "origen igual a destino"])
        if t == "control alterado":
            return t, f"{body};{int(ctl(body)) % 98 + 1}" if kind != "PING" else "PING;x;21"
        if t == "control mal formado":
            return t, f"{body};{r.choice(['5X', '0' + ctl(body), ctl(body) + ' ', '+' + ctl(body), '114'])}"
        if t == "aridad":
            args = args + ["X"] if r.random() < 0.5 or not args else args[:-1]
            return t, msg(";".join([cmd] + args))
        if t == "monto en el borde":
            a = list(model.saldo) or ["AC-0001"]
            n = r.choice(["0", "100000", "100001", "9999999999", "10000000000", "007", "-5", "1.5", "1e3"])
            if len(a) > 1 and r.random() < 0.6:
                x, y = r.sample(a, 2)
                return t, msg(f"TRANSFER;{x};{y};{n}")
            return t, msg(f"DEPOSITO;{r.choice(a)};{n}")
        if t == "origen igual a destino":
            a = r.choice(list(model.saldo) or ["AC-0001"])
            return t, msg(f"TRANSFER;{a};{a};{r.choice(['10', '0', '100001'])}")
        if t == "id inexistente":
            bad = r.choice(["AC-0099", "ac-0001", "AC-1", "OP-0099", "op-0001", "AC-0001 "])
            c = r.choice(["CONSULTA", "DEPOSITO", "ANULA", "TRANSFER"])
            if c == "ANULA":
                return t, msg(f"ANULA;{bad}")
            if c == "CONSULTA":
                return t, msg(f"CONSULTA;{bad}")
            if c == "DEPOSITO":
                return t, msg(f"DEPOSITO;{bad};{r.randint(1, 999)}")
            other = (list(model.saldo) or ["AC-0001"])[0]
            return t, msg(f"TRANSFER;{other};{bad};{r.randint(1, 999)}")
        if t == "minúsculas":
            low = "".join(c.lower() if r.random() < 0.5 else c for c in cmd)
            return t, f"{low};{';'.join(args) + ';' if args else ''}{ctl(body)}"
        if t == "comando cercano":
            return t, msg(";".join([self.near(cmd)] + args))
        if t == "formato":
            return t, r.choice([body, f"{body};", f";{body};{ctl(body)}", f"{cmd};;{ctl(cmd)}", ""])
        ops = [i for i, o in enumerate(model.ops) if o["anulada"]]
        if ops:
            return t, msg(f"ANULA;OP-{r.choice(ops) + 1:04d}")
        return "control alterado", f"{body};{int(ctl(body)) % 98 + 1}"

    def near(self, cmd):
        r = self.r
        while True:
            w = list(cmd)
            for _ in range(r.randint(1, 3)):
                op, i = r.choice("sid"), r.randrange(len(w) + 1)
                if op == "s" and i < len(w):
                    w[i] = r.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                elif op == "d" and i < len(w) and len(w) > 1:
                    del w[i]
                else:
                    w.insert(i, r.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            word = "".join(w)
            if word.upper() not in ARITY and word.strip():
                return word

    def streak(self, model, n):
        """Racha para E510 en una secuencia larga: dos cuentas, rechazos seguidos y lo que venga."""
        steps = [("ALTA", msg("ALTA;Ana")), ("ALTA", msg("ALTA;Beto")),
                 ("DEPOSITO", msg(f"DEPOSITO;AC-0001;{self.r.randint(100, 5000)}"))]
        for _ in range(3):
            steps.append(("racha", msg(f"TRANSFER;AC-0001;AC-0002;{self.r.choice(['100001', '900000', '99999'])}")))
        steps.append(("racha", msg("TRANSFER;AC-0001;AC-0002;10")))
        return steps[:n]

    def sequence(self, n, halt=False, streak=False):
        model, steps = Model(), []
        if streak:
            for kind, m in self.streak(model, n):
                model.apply(m)
                steps.append((kind, m))
        while len(steps) < n:
            if halt and len(steps) == n - 2:
                kind, m = "HALT;1", msg("HALT;1")
            # Con dos cuentas desde el principio, TRANSFER y ANULA aparecen; con una sola, casi nunca.
            elif len(steps) < (2 if n >= 3 else 1 if n > 1 else 0) and self.r.random() < 0.85:
                kind, m = "ALTA", msg(f"ALTA;{self.r.choice(NAMES)}")
            elif self.r.random() < 0.7:
                kind, m = self.valid(model)
            else:
                kind, m = self.mutate(model)
            model.apply(m)
            steps.append((kind, m))
        return steps

    def batch(self):
        lengths = [1] * 40 + [self.r.randint(2, 5) for _ in range(45)] + [self.r.randint(6, 12) for _ in range(15)]
        halts = set(self.r.sample(range(40, 100), 3))
        streaks = set(self.r.sample([i for i in range(85, 100) if i not in halts], 5))
        return [self.sequence(n, halt=i in halts and n >= 2, streak=i in streaks) for i, n in enumerate(lengths)]


def probes(seed):
    rows = []
    for i, seq in enumerate(Gen(seed).batch(), 1):
        rows.append({"hipotesis": f"diferencial s{seed} #{i}: reset abre la secuencia de {len(seq)} pasos", "reset": True})
        for j, (kind, m) in enumerate(seq, 1):
            rows.append({"hipotesis": f"diferencial s{seed} #{i} paso {j}: {kind}", "m": m})
    return rows


def load_log():
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []


def generate(seed):
    existing = [int(p.name[:3]) for p in PROBES.glob("[0-9][0-9][0-9]-*.jsonl")]
    path = PROBES / f"{max(existing, default=0) + 1:03d}-diff-s{seed}.jsonl"
    rows = probes(seed)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    steps = [r for r in rows if "m" in r]
    mut = [r for r in steps if r["hipotesis"].split(": ", 1)[1] not in ARITY]
    print(f"{path.relative_to(ROOT)}: 100 secuencias, {len(rows)} requests, "
          f"{len(mut)} de {len(steps)} pasos fuera de los mensajes válidos ({100 * len(mut) // len(steps)} %)")
    return path


def record(path):
    if not os.environ.get("BB_TOKEN"):
        sys.exit("falta BB_TOKEN")
    rows = [l for l in Path(path).read_text().splitlines() if l.strip()]
    spent = sum(1 for r in load_log() if str(r.get("hipotesis", "")).startswith("diferencial"))
    if spent + len(rows) > BUDGET:
        sys.exit(f"el diferencial lleva {spent} requests: con {len(rows)} más pasa el tope de {BUDGET}")
    env = {**os.environ, "BB_TAG": "t2", "BB_LOG": str(LOG)}
    PAUSE.touch()
    try:
        while True:
            r = subprocess.run([sys.executable, ROOT / "lab" / "send.py", path], env=env,
                               stderr=subprocess.PIPE, text=True)
            # Si el canario empezó justo antes que la pausa, tiene el candado: se espera a que termine.
            if r.returncode != 0 and "otro send.py" in r.stderr:
                time.sleep(15)
                continue
            if r.stderr:
                print(r.stderr, end="", file=sys.stderr)
            return r.returncode
    finally:
        PAUSE.unlink(missing_ok=True)
        print(f"canario despausado ({PAUSE.name} borrado)")


def sequences(log, prefixes, only=None):
    by_seq = {}
    for r in log:
        by_seq.setdefault(r["seq"], []).append(r)
    out = []
    for seq, rows in by_seq.items():
        if rows[0].get("ruta") != "/__reset" or len(rows) < 2 or any("error" in r for r in rows):
            continue
        if (seq in only) if only else any(rows[0]["hipotesis"].startswith(p) for p in prefixes):
            out.append((seq, rows[1:]))
    return out


def changes(seed):
    """Primera grabación de cada secuencia de la semilla contra la última: qué respondió distinto el original."""
    runs = {}
    for seq, steps in sequences(load_log(), [f"diferencial s{seed} "]):
        n = re.search(r"#(\d+)", steps[0]["hipotesis"]).group(1)
        runs.setdefault(int(n), []).append(steps)
    pairs = {n: (r[0], r[-1]) for n, r in runs.items() if len(r) > 1}
    if not pairs:
        sys.exit(f"la semilla {seed} tiene una sola grabación en {LOG}: hay que regrabarla")
    diff_seqs, rules = 0, {}
    for n, (old, new) in sorted(pairs.items()):
        first = True
        for j, (a, b) in enumerate(zip(old, new), 1):
            if a["status"] == b["status"] and same(a["response"], b["response"]):
                continue
            # Un cambio temprano corre los ids y los saldos de lo que sigue: solo el primero es causa.
            tag = "causa " if first else "efecto"
            if first:
                diff_seqs += 1
                key = (a["status"], json.dumps(a["response"], ensure_ascii=False),
                       b["status"], json.dumps(b["response"], ensure_ascii=False))
                rules.setdefault(key, []).append((a["id"], b["id"], a["request"]["m"]))
            first = False
            print(f"{tag} #{n} paso {j} | {a['request']['m']} | v1 {a['status']} "
                  f"{json.dumps(a['response'], ensure_ascii=False)} (log {a['id']}) | ahora {b['status']} "
                  f"{json.dumps(b['response'], ensure_ascii=False)} (log {b['id']})")
    print(f"\n{diff_seqs} de {len(pairs)} secuencias cambiaron. Causas agrupadas por respuesta:")
    for (s1, r1, s2, r2), ex in sorted(rules.items(), key=lambda kv: -len(kv[1])):
        print(f"- {len(ex)}× v1 {s1} {r1} → ahora {s2} {r2}; ej. {ex[0][2]} (log {ex[0][0]} → {ex[0][1]})")
    return 1 if diff_seqs else 0


class Replacement:
    def __init__(self):
        self.url = urllib.parse.urlsplit(os.environ.get("REPL_URL") or sys.exit("falta REPL_URL"))
        self.token = os.environ.get("REPL_TOKEN") or sys.exit("falta REPL_TOKEN")
        cls = http.client.HTTPSConnection if self.url.scheme == "https" else http.client.HTTPConnection
        self.conn = cls(self.url.netloc, timeout=10)

    def send(self, row):
        method, path = row.get("metodo", "POST"), row.get("ruta", "/msg")
        req = row["request"]
        data = None if req is None else (req if isinstance(req, str) else json.dumps(req)).encode()
        # content_type null en el log significa que la sonda lo omitió a propósito.
        ct = row["content_type"] if "content_type" in row else "application/json"
        headers = {"Content-Type": ct} if data is not None and ct is not None else {}
        auth = row.get("auth", "ok")
        if auth in ("ok", "propio"):
            headers["Authorization"] = f"Bearer {self.token}"
        elif "{token}" in auth:
            headers["Authorization"] = auth.replace("{token}", self.token)
        elif auth not in ("none", "sin token"):
            headers["Authorization"] = "Bearer token-ajeno"
        for attempt in range(2):
            try:
                self.conn.request(method, path, body=data, headers=headers)
                resp = self.conn.getresponse()
                text = resp.read().decode("utf-8", errors="replace")
                break
            except (OSError, http.client.HTTPException):
                # Conexión vieja cerrada por el otro lado: se reabre una vez.
                self.conn.close()
                if attempt:
                    raise
        try:
            return resp.status, json.loads(text)
        except ValueError:
            return resp.status, text


def compare(seed, canario, only=None, log=None):
    prefixes = [f"diferencial s{seed} " if seed is not None else "diferencial"] + (["canario"] if canario else [])
    rows = [json.loads(l) for l in Path(log).read_text().splitlines() if l.strip()] if log else load_log()
    seqs = sequences(rows, prefixes, only)
    if not seqs:
        sys.exit(f"no hay secuencias que empiecen por {prefixes} en {LOG}")
    repl, equal_seqs, equal_steps, total_steps, bad = Replacement(), 0, 0, 0, []
    for seq, steps in seqs:
        repl.send({"metodo": "POST", "ruta": "/__reset", "request": None})
        ok = True
        for j, row in enumerate(steps, 1):
            status, body = repl.send(row)
            total_steps += 1
            if status == row["status"] and same(body, row["response"]):
                equal_steps += 1
                continue
            ok = False
            bad.append((row["id"], seq, j, f"{row['status']} {json.dumps(row['response'], ensure_ascii=False)}",
                        f"{status} {json.dumps(body, ensure_ascii=False)}", json.dumps(row["request"], ensure_ascii=False)))
        equal_seqs += ok
    print(f"secuencias iguales: {equal_seqs} de {len(seqs)} ({100 * equal_seqs / len(seqs):.1f} %)")
    print(f"pasos iguales: {equal_steps} de {total_steps} ({100 * equal_steps / total_steps:.1f} %)")
    if bad:
        print("id | seq | paso | request | esperado | obtenido")
        for i, s, j, e, g, q in bad:
            print(f"{i} | {s} | {j} | {q} | {e} | {g}")
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generar")
    g.add_argument("--semilla", type=int, default=None)
    gr = sub.add_parser("grabar")
    gr.add_argument("archivo")
    c = sub.add_parser("comparar")
    c.add_argument("--semilla", type=int, default=None)
    c.add_argument("--canario", action="store_true")
    # Para reproducir otras secuencias, como la tanda de HTTP raro de t1: --log logs/t1.jsonl --seq t1-s3
    c.add_argument("--seq", nargs="*")
    c.add_argument("--log")
    ch = sub.add_parser("cambios")
    ch.add_argument("--semilla", type=int, required=True)
    a = ap.parse_args()
    if a.cmd == "generar":
        # Una semilla nueva por grabación; queda en el nombre del archivo para poder regenerarla.
        seed = a.semilla if a.semilla is not None else int(time.time()) % 100000
        path = generate(seed)
        subprocess.run([sys.executable, ROOT / "lab" / "send.py", path, "--dry"])
        return 0
    if a.cmd == "grabar":
        return record(a.archivo)
    if a.cmd == "cambios":
        return changes(a.semilla)
    return compare(a.semilla, a.canario, a.seq, a.log)


if __name__ == "__main__":
    sys.exit(main())
