"""Canario (D8): la misma tanda cada 20 minutos contra el original, comparada con la última línea base aceptada.

    python3 lab/canary.py tanda                  # escribe lab/probes/canario.jsonl
    BB_TOKEN=... python3 lab/canary.py vigilar   # corre a las :05, :25 y :45, y a las 19:55; para a las 20:00
    python3 lab/canary.py comparar               # compara cada corrida del log con la línea base
    python3 lab/canary.py aceptar t2-sN          # esa corrida pasa a ser la línea base

Mientras exista logs/canario.pausa, vigilar se salta las corridas (por ejemplo, durante la tanda de HALT).
Salida de comparar: 0 sin cambios, 1 cambió, 2 no hay corrida completa.

Las corridas se reconocen por sus requests: si cambian los casos de EXTRA (o los ejemplos), las corridas
viejas dejan de reconocerse y la línea base desaparece. Antes de tocarlos hay que avisar, reiniciar
vigilar y aceptar una corrida nueva como base.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = os.environ.get("BB_TAG", "t2")
LOG = Path(os.environ.get("BB_LOG", ROOT / "logs" / f"{TAG}.jsonl"))
BASE = LOG.with_name(f"{LOG.stem}-canario-base.json")
PAUSE = ROOT / "logs" / "canario.pausa"
PROBES = ROOT / "lab" / "probes" / "canario.jsonl"
EJEMPLOS = ROOT.parent / "frontier-reto-2" / "material" / "pruebas" / "ejemplos.jsonl"


def ctl(body):
    # DESIGN 3.2: se descarta todo lo que no sea A–Z o 0–9 antes de pasar a mayúsculas.
    n = "".join(str(ord(c) - 64) if "A" <= c <= "Z" else c
                for c in "".join(c for c in body if c.isascii() and c.isalnum()).upper())
    # Módulo 97 dígito por dígito: un m de miles de caracteres da un N que int() no convierte.
    r = 0
    for d in n:
        r = (r * 10 + int(d)) % 97
    return str(98 - (r * 100) % 97)


def msg(body):
    return f"{body};{ctl(body)}"


def err(code, mensaje, **extra):
    return {"error": code, "mensaje": mensaje, **extra}


E303 = err("E303", "monto inválido")
E401 = err("E401", "cuenta inexistente")
E507 = err("E507", "saldo insuficiente")
E101_RAW = '{"m":"PING;64","pad":"' + "x" * (8193 - len('{"m":"PING;64","pad":""}')) + '"}'


def recieved(op):
    return {"status": "recieved", "operacionId": op}


# Después de los 20 ejemplos: AC-0001 con 210.000, AC-0002 con 40.700, la última operación es OP-0004.
# (sonda, status, respuesta, regla, log que la respalda)
EXTRA = [
    ({"method": "GET", "path": "/nada", "auth": "none"}, 404, err("E404", "ruta desconocida"),
     "ruta antes que token", "57"),
    ({"m": "PING;64", "auth": "none"}, 401, err("E001", "no autorizado"), "token", "50"),
    ({"method": "GET", "path": "/health"}, 200, {"ok": True}, "health", "54"),
    ({"raw": E101_RAW}, 413, err("E101", "cuerpo demasiado grande"), "tope 8.192 bytes", "10987"),
    ({"raw": "hola"}, 400, err("E100", "json inválido"), "json", "69"),
    ({"raw": "[" * 21 + "]" * 21}, 400, err("E100", "json inválido"), "profundidad 21", "11007"),
    ({"body": {}}, 400, err("E102", "falta m"), "campo m", "72"),
    ({"m": "PING"}, 400, err("E103", "falta control"), "sin ;", "31"),
    ({"m": "PING;"}, 400, err("E104", "segmento vacío"), "segmento vacío", "30"),
    ({"m": f"XXXX;AC-0001;{int(ctl('XXXX;AC-0001')) % 98 + 1}"}, 400, err("E202", "control inválido"),
     "control antes que comando", "38–41"),
    ({"m": "CONSULT;AC-0001;41"}, 400, err("E301", "comando desconocido ", sugerencia="CONSULTA"),
     "sugerencia", "87"),
    ({"m": "PING;x;21"}, 400, err("E302", "aridad inválida"), "aridad", "43"),
    ({"m": msg("ALTA;Ana")}, 201, {"cuentaId": "AC-0003"}, "ALTA numera", "3, 4"),
    ({"m": msg("ALTA;Beto")}, 201, {"cuentaId": "AC-0004"}, "ALTA numera", "3, 4"),
    ({"m": msg("TRANSFER;AC-0003;AC-0003;0")}, 400, E303, "E303 antes que E304", "141"),
    ({"m": msg("TRANSFER;AC-0003;AC-0003;10")}, 400, err("E304", "origen y destino iguales"), "E304", "103, 140"),
    ({"m": msg("TRANSFER;AC-0003;AC-0099;10")}, 404, E401, "E401 en TRANSFER", "104–106"),
    ({"m": msg("ANULA;OP-0099")}, 404, err("E402", "operación inexistente"), "E402", "126–128"),
    ({"m": msg("DEPOSITO;AC-0003;10000000000")}, 400, E303, "monto de 11 dígitos", "371–374"),
    ({"m": msg("DEPOSITO;AC-0004;9999999999")}, 200, recieved("OP-0005"), "monto de 10 dígitos", "365–370"),
    ({"m": msg("CONSULTA;AC-0004")}, 200, {"cuenta_id": "AC-0004", "saldo": 9999999999}, "saldo grande", "379"),
    ({"m": msg("DEPOSITO;AC-0003;1000")}, 200, recieved("OP-0006"), "depósito", "6"),
    ({"m": msg("TRANSFER;AC-0003;AC-0004;100001")}, 422, err("E506", "límite excedido"),
     "límite antes que saldo; rechazo 1", "108, 110"),
    ({"m": msg("TRANSFER;AC-0003;AC-0004;5000")}, 422, E507, "rechazo 2", "16"),
    ({"m": msg("TRANSFER;AC-0003;AC-0004;5000")}, 422, E507, "rechazo 3", "16"),
    ({"m": msg("TRANSFER;AC-0003;AC-0004;10")}, 409, err("E510", "cuenta bloqueada"), "bloqueo tras 3", "249, 269"),
    ({"m": msg("TRANSFER;AC-0003;AC-0003;10")}, 400, err("E304", "origen y destino iguales"),
     "E304 antes que E510", "306"),
    ({"m": msg("DEPOSITO;AC-0003;1")}, 200, recieved("OP-0007"), "depósito desbloquea", "250, 323–324"),
    ({"m": msg("TRANSFER;AC-0003;AC-0004;10")}, 200, recieved("OP-0008"), "desbloqueada", "250"),
    ({"m": msg("CONSULTA;AC-0003")}, 200, {"cuenta_id": "AC-0003", "saldo": 991}, "saldo tras bloqueo", "—"),
    ({"m": "HALT;AC-0001;82"}, 409,
     err("E520", "operación destructiva: detiene el servicio; reenvía con confirmación"), "HALT", "292"),
    ({"m": "PING;64"}, 200, {"pong": True}, "responde tras HALT", "294"),
    ({"m": msg("ALTA;Ana")}, 201, {"cuentaId": "AC-0005"}, "segunda cuenta de Ana", "3, 4"),
    ({"m": msg("DEPOSITO;AC-0003;300000")}, 200, recieved("OP-0009"), "depósito", "6"),
    ({"m": msg("TRANSFER;AC-0003;AC-0005;150000")}, 200, recieved("OP-0010"),
     "mismo titular sin límite", "11782, 11794"),
    ({"m": msg("CONSULTA;AC-0005")}, 200, {"cuenta_id": "AC-0005", "saldo": 150000}, "mismo titular sin límite",
     "11783, 11795"),
    # HALT;1 deja el servicio detenido: va al final y lo que sigue solo mide E599.
    ({"m": "HALT;1;19"}, 503, err("E599", "service halted"), "HALT;1 detiene", "11134, 11199"),
    ({"raw": E101_RAW}, 503, err("E599", "service halted"), "E599 antes que E101", "11320, 11324"),
    ({"m": "PING;64"}, 503, err("E599", "service halted"), "detenido", "11135"),
]


def cases():
    ej = [json.loads(l) for l in EJEMPLOS.read_text().splitlines() if l.strip()]
    replay = [({"m": e["request"]["m"]}, e["status"], e["response"], f"ejemplo {e['n']}", "1–20") for e in ej]
    return replay + EXTRA


def probes():
    rows = [{"hipotesis": "canario: reset abre la corrida", "reset": True}]
    for p, status, resp, regla, ids in cases():
        rows.append({"hipotesis": f"canario ({regla}): {status} {json.dumps(resp, ensure_ascii=False)} "
                                  f"como en log {ids}", **p})
    return rows


def key_of_probe(p):
    if "m" in p:
        req = {"m": p["m"]}
    else:
        req = p.get("raw", p.get("body"))
    return (p.get("method", "POST"), p.get("path", "/msg"), p.get("auth", "ok"), json.dumps(req))


def key_of_row(r):
    return (r.get("metodo", "POST"), r.get("ruta", "/msg"), r.get("auth", "ok"), json.dumps(r["request"]))


def same(a, b):
    # En Python 1 == 1.0 == True: el README exige strings y números idénticos, así que se compara el tipo.
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def runs(log):
    """Corridas del canario en el log, en orden: (seq, filas sin el reset, completa)."""
    keys = [key_of_probe(p) for p in probes()[1:]]
    by_seq = {}
    for r in log:
        by_seq.setdefault(r["seq"], []).append(r)
    found = []
    for seq, rows in by_seq.items():
        if rows[0].get("ruta") != "/__reset":
            continue
        steps = rows[1:]
        # Se reconoce por sus requests, no por la hipótesis: así otra tanda nunca pasa por canario.
        if not steps or [key_of_row(r) for r in steps] != keys[:len(steps)]:
            continue
        found.append((seq, steps, len(steps) == len(keys) and not any("error" in r for r in steps)))
    return found


def diffs(expected, got):
    return [(i, e, g) for i, (e, g) in enumerate(zip(expected, got))
            if g["status"] != e["status"] or not same(g["response"], e["response"])]


def span(seq, steps):
    return f"{seq} (ids {steps[0]['id']}–{steps[-1]['id']}, {steps[0]['ts']}–{steps[-1]['ts']} UTC)"


def load_log():
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []


def baseline(found):
    if not BASE.exists():
        rows = [{"status": s, "response": r} for _, s, r, _, _ in cases()]
        return "catálogo (DESIGN §3)", rows
    seq = json.loads(BASE.read_text())["seq"]
    for s, steps, ok in found:
        if s == seq and ok:
            return seq, steps
    sys.exit(f"la línea base {seq} no está completa en {LOG}")


def compare():
    found = runs(load_log())
    base_name, expected = baseline(found)
    complete = [(s, st) for s, st, ok in found if ok]
    last_green = None
    if base_name in [s for s, _ in complete]:
        i = [s for s, _ in complete].index(base_name)
        last_green, complete = complete[i], complete[i + 1:]
    if not complete:
        print(f"sin corridas completas después de la línea base {base_name}")
        return 2
    for seq, steps in complete:
        d = diffs(expected, steps)
        if not d:
            last_green = (seq, steps)
            continue
        regla = [c[3] for c in cases()]
        print(f"CAMBIO contra la línea base {base_name}: {len(d)} de {len(expected)} pasos difieren")
        print("  última en verde: " + (span(*last_green) if last_green else "ninguna desde la línea base"))
        print("  primera en rojo: " + span(seq, steps))
        for n, (i, e, g) in enumerate(d):
            # Si cambia un ALTA o un depósito, los ids que siguen se corren: solo la primera diferencia es causa.
            print(f"  {'causa ' if n == 0 else 'efecto'} paso {i + 1} ({regla[i]}) {key_of_row(g)[3]}")
            print(f"    antes {e['status']} {json.dumps(e['response'], ensure_ascii=False)}")
            print(f"    ahora {g['status']} {json.dumps(g['response'], ensure_ascii=False)}  (log {g['id']})")
        # Mientras el cambio no se acepte, esta primera roja se repite en cada corrida: la última dice
        # si sigue igual de roja o si el servicio volvió atrás.
        if (seq, steps) != complete[-1]:
            n = len(diffs(expected, complete[-1][1]))
            print(f"  la más reciente, {span(*complete[-1])}: "
                  + (f"{n} pasos difieren" if n else "igual a la línea base (¿reversión?)"))
        return 1
    print(f"verde: {len(complete)} corrida(s) iguales a {base_name}; la última {span(*last_green)}")
    if base_name.startswith("catálogo"):
        accept(last_green[0], "primera corrida igual al catálogo")
    return 0


def accept(seq, motivo):
    found = {s: ok for s, _, ok in runs(load_log())}
    if not found.get(seq):
        sys.exit(f"{seq} no es una corrida completa del canario en {LOG}")
    BASE.write_text(json.dumps({"seq": seq, "motivo": motivo,
                                "aceptada": datetime.now().astimezone().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
    print(f"línea base: {seq} ({motivo})")


def run_once():
    PROBES.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in probes()))
    env = {**os.environ, "BB_TAG": TAG, "BB_LOG": str(LOG)}
    deadline = time.monotonic() + 300
    while True:
        r = subprocess.run([sys.executable, ROOT / "lab" / "send.py", PROBES], env=env,
                           capture_output=True, text=True)
        # Otra tanda tiene el candado del log: el canario espera su turno en vez de perder la corrida.
        if r.returncode != 0 and "otro send.py" in r.stderr and time.monotonic() < deadline:
            time.sleep(15)
            continue
        if r.returncode != 0:
            print(f"send.py falló: {r.stderr.strip()}")
        return


def slots(now):
    day = now.replace(second=0, microsecond=0)
    grid = [day.replace(hour=h, minute=m) for h in range(24) for m in (5, 25, 45)]
    grid += [day.replace(hour=19, minute=55)]
    end = day.replace(hour=20, minute=0)
    return sorted(t for t in grid if now < t < end)


def watch():
    if not os.environ.get("BB_TOKEN"):
        sys.exit("falta BB_TOKEN")
    pending = [datetime.now()] + slots(datetime.now())
    for t in pending:
        wait = (t - datetime.now()).total_seconds()
        if wait > 0:
            time.sleep(wait)
        stamp = datetime.now().strftime("%H:%M")
        if PAUSE.exists():
            print(f"{stamp} pausado ({PAUSE.name} existe)", flush=True)
            continue
        run_once()
        print(f"{stamp} ", end="")
        # Una base que no aparece o una corrida que no se puede aceptar no deben matar la vigilancia.
        try:
            if compare() == 1:
                print("\a", end="")
        except SystemExit as e:
            print(f"no se pudo comparar: {e.code}")
        sys.stdout.flush()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "tanda":
        PROBES.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in probes()))
        print(f"{len(probes())} requests en {PROBES.relative_to(ROOT)}")
    elif cmd == "comparar":
        return compare()
    elif cmd == "aceptar" and len(sys.argv) == 3 and re.fullmatch(r"\w+-s\d+", sys.argv[2]):
        accept(sys.argv[2], "aceptada a mano")
    elif cmd == "vigilar":
        watch()
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
