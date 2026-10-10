"""Qué cambió en la v2. Nunca manda requests.

    python3 evals/cambios.py [log]                         repite log: la tanda 017
    python3 evals/cambios.py --tanda <probes.jsonl> [log]  primera corrida de una tanda contra la última

El log por defecto es logs/t1.jsonl.

Modo repite log: cada línea nueva dice en su hipótesis qué línea repite ("v2: repite log N"); así se
empareja aunque la tanda se haya cortado a mitad.

Modo --tanda: send.py toma un lock sobre el log mientras corre, así que cada corrida queda como un bloque
de líneas seguidas con las hipótesis de la tanda en orden. La línea k de una corrida se empareja con la k
de la otra (mismo texto de hipótesis y mismo número de aparición). Lo que falta en una de las dos
(corrida cortada) se lista aparte.

Compara como el set oculto: status igual y, si los dos cuerpos son JSON, el mismo JSON sin importar el
orden de las claves; si no, el texto exacto. Lista solo lo que difiere.
"""
import json
import re
import sys
from pathlib import Path

args = sys.argv[1:]
tanda = None
if args[:1] == ["--tanda"]:
    if len(args) < 2:
        sys.exit(__doc__)
    tanda, args = Path(args[1]), args[2:]
log = Path(args[0] if args else Path(__file__).resolve().parent.parent / "logs" / "t1.jsonl")
lineas = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def cuerpo(l):
    # El log guarda el cuerpo parseado si era JSON y el texto si no. sort_keys ignora el orden de las
    # claves sin confundir 1 con 1.0 ni con true, como haría == en Python.
    if "error" in l:  # send.py no vio la respuesta
        return f"sin respuesta: {l['error']}"
    r = l["response"]
    return r if isinstance(r, str) else json.dumps(r, sort_keys=True, ensure_ascii=False)


def respuesta(l):
    return cuerpo(l) if "error" in l else f"{l['status']} {cuerpo(l)[:200]}"


def difiere(a, b):
    return "error" in a or "error" in b or (a["status"], cuerpo(a)) != (b["status"], cuerpo(b))


def repite_log():
    por_id = {l["id"]: l for l in lineas}
    pares = diferencias = 0
    print("id_viejo | id_nuevo | esperado_v1 | obtenido_v2")
    for nueva in lineas:
        m = re.fullmatch(r"v2: repite log (\d+)", nueva.get("hipotesis", ""))
        if not m:
            continue
        vieja = por_id.get(int(m.group(1)))
        if vieja is None:
            sys.exit(f"la línea {nueva['id']} repite la {m.group(1)}, que no está en {log}")
        pares += 1
        if difiere(vieja, nueva):
            print(f"{vieja['id']} | {nueva['id']} | {respuesta(vieja)} | {respuesta(nueva)}")
            diferencias += 1
    print(f"{diferencias} diferencias en {pares} pares")


def corridas(hipotesis):
    # Bloques de líneas seguidas que recorren la tanda desde su primera hipótesis. Un bloque de una sola
    # línea es otra tanda que abre con el mismo texto (por ejemplo "estado inicial limpio"): se descarta.
    bloques, i = [], 0
    while i < len(lineas):
        if lineas[i].get("hipotesis") != hipotesis[0]:
            i += 1
            continue
        j = 0
        while i + j < len(lineas) and j < len(hipotesis) and lineas[i + j].get("hipotesis") == hipotesis[j]:
            j += 1
        if j > 1:
            bloques.append(lineas[i:i + j])
        i += j
    return bloques


def comparar_tanda():
    hipotesis = [json.loads(l)["hipotesis"] for l in tanda.read_text().splitlines() if l.strip()]
    bloques = corridas(hipotesis)
    for b in bloques:
        print(f"corrida: ids {b[0]['id']}–{b[-1]['id']}, {len(b)} de {len(hipotesis)} líneas")
    if len(bloques) < 2:
        sys.exit(f"hacen falta dos corridas de {tanda.name} en {log} y hay {len(bloques)}")
    v1, v2 = bloques[0], bloques[-1]
    diferencias = 0
    print("hipotesis | id_v1 | id_v2 | v1 | v2")
    for a, b in zip(v1, v2):
        if difiere(a, b):
            print(f"{a['hipotesis']} | {a['id']} | {b['id']} | {respuesta(a)} | {respuesta(b)}")
            diferencias += 1
    print(f"{diferencias} diferencias en {min(len(v1), len(v2))} pares")
    sobrantes = v1[len(v2):] or v2[len(v1):]
    if sobrantes:
        corrida = "v1" if len(v1) > len(v2) else "v2"
        print(f"sin pareja (la otra corrida se cortó), solo en {corrida}:")
        for l in sobrantes:
            print(f"{l['hipotesis']} | {l['id']}")


comparar_tanda() if tanda else repite_log()
