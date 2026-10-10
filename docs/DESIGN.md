# Reemplazo de la caja negra

**Resumen.**

1. El original es un pequeño banco que recibe `COMANDO;argumentos;control` por `POST /msg`; el control es un dígito de verificación módulo 97 al estilo IBAN.
2. Tiene seis comandos visibles y uno oculto (`HALT`), errores que se evalúan en un orden fijo que medimos, y un bloqueo de cuenta después de tres transferencias rechazadas seguidas.
3. El reemplazo es un único proceso Node con el estado en memoria y las reglas declaradas en tablas, sin LLM (decisiones D1 a D5, aprobadas).
4. La fidelidad se mide con pruebas diferenciales locales contra el original; el set oculto se usa solo 3 veces: calibración, después del incidente y final.
5. El servicio puede cambiar sin aviso (la agenda marca un incidente a las 15:30, y puede haber más de uno). Un canario corre cada 20 minutos desde las 13:00 contra una línea base móvil, y el diferencial del área afectada dice qué hay que ajustar.

Todas las referencias entre paréntesis, como (log 122), son ids de `experimentos.jsonl`. Ese archivo no se edita a mano: lo arma `python3 lab/logs.py armar` a partir de `logs/t1.jsonl` y `logs/t2.jsonl`, uno por token. Los ids 1–497 son del token 1 durante el diseño; los 10001–10958 son del token 2 durante el diseño, renumerados +10000 (con `id_original`, mapeo en `logs/MAPEO.md`); desde las 12:40 cada token sigue en su rango (t1 desde 498, t2 desde 10959). Cada línea tiene los campos del README más `token`, `metodo`, `ruta` y `auth` (propio, sin token, token ajeno o esquema Basic; nunca el token en sí), y desde las 12:40 `ts` (hora UTC). Algunas líneas llevan además `par` (pasos mandados en paralelo, en la misma ráfaga), `espera` (milisegundos de pausa antes de mandarlo), `texto` (el cuerpo de la respuesta no era JSON) o `headers` (headers de la respuesta, solo en las sondas de huella del stack). En los ids 1–497 el arnés de entonces (`exploracion/arnes.ts`) no registraba los `POST /__reset` de inicio de secuencia ni la hora: cada secuencia de ese rango empieza tras un reset que no tiene línea propia.

## 1. Problema

El servicio lleva años en producción, no tiene código ni documentación, y hay que reemplazarlo por otro que responda exactamente igual: el mismo status HTTP y el mismo cuerpo, incluidos los errores y las rarezas (por ejemplo, la palabra mal escrita `"recieved"`). El reemplazo se evalúa con 100 secuencias ocultas contra la versión del servicio vigente a las 20:00, y el servicio va a cambiar durante el día. No buscamos mejorar el comportamiento del original; lo copiamos tal cual y documentamos aparte los riesgos que un cliente nuevo no debería heredar.

## 2. Requisitos

| ID | Requisito | Criterio de aceptación (verificable) |
|---|---|---|
| RF-01 | Entrada idéntica | Dado un `POST /msg` sin token o con un token ajeno, entonces el reemplazo responde 401 `{"error":"E001","mensaje":"no autorizado"}`; dada una ruta o un método que no existe, responde 404 `E404` incluso sin token (log 50–68). |
| RF-02 | Integridad idéntica | Dado un mensaje cuyo control no coincide con el calculado, entonces responde 400 `E202`; si el control no tiene uno o dos dígitos, 400 `E201` (log 21–49, 131–135). |
| RF-03 | Comandos idénticos | Dada cualquier secuencia del catálogo de la sección 3, entonces cada respuesta coincide con el log según el comparador del README. |
| RF-04 | Orden de errores | Dado un mensaje con dos o más errores, entonces responde el que aparece primero en el orden de la sección 3.11 (log 38–44, 106, 110, 139–141, 296–298, 305–309). |
| RF-05 | Memoria | Después de `/__reset`, el primer ALTA devuelve `AC-0001`, la primera operación `OP-0001`, y tres transferencias rechazadas seguidas bloquean la cuenta de origen (log 249, 269). |
| RF-06 | Cambio de las 15:30 | Después del cambio, cada respuesta que difiere del log queda listada con el id viejo, el id nuevo y la hora en que se detectó. |

| ID | Atributo | Umbral |
|---|---|---|
| RNF-01 | Latencia | p95 ≤ 50 ms por paso medido desde fuera de Cloud Run (el set permite 5 s). |
| RNF-02 | Costo | US$0 por caso en el reemplazo; como máximo 8.000 requests por día y por token contra el original. |
| RNF-03 | Fidelidad | 100 % de las secuencias del log reproducidas igual; ≥ 90 % de las secuencias diferenciales nuevas iguales. |
| RNF-04 | Disponibilidad | `/health` responde 200 en ≤ 10 s después de desplegar; un solo proceso con un solo estado. |

## 3. Lo que sabemos del servicio

La confianza sigue la regla del README. **Confirmado** significa que lo vimos en dos o más líneas del log que coinciden, en secuencias distintas. **Probable** significa que lo vimos una sola vez o que lo inferimos. **Supuesto** significa que no lo probamos y es lo que hará el reemplazo por defecto. Ante la duda marcamos probable, porque una afirmación falsa en la especificación resta puntos.

### 3.1 Entrada

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| `POST /msg` sin token, con token inventado o con esquema Basic | 401 `{"error":"E001","mensaje":"no autorizado"}` | 50, 51, 52 | confirmado |
| `POST /__reset` sin token o con token inventado | 401 `E001` | 55, 56 | confirmado |
| El token se evalúa antes que el cuerpo: sin token o con token ajeno, un cuerpo no JSON o sin `m` da E001 y no E100 ni E102 | 401 `E001` | 296, 297, 298 | confirmado |
| `GET /health` sin token | 401 `E001` | 53 | probable |
| `GET /health` con token | 200 `{"ok":true}` | 54 | probable |
| Ruta inexistente (`/nada`, `/`), con o sin token: la ruta se evalúa antes que el token | 404 `{"error":"E404","mensaje":"ruta desconocida"}` | 57, 58, 59, 60 | confirmado |
| Método equivocado en ruta conocida (`GET /msg`, `PUT /msg`, `GET /__reset`, `POST /health`) | 404 `E404` | 61–65 | confirmado |
| Variantes de la ruta: `/msg/` y `/MSG` no existen; `/msg?x=1` sí funciona | 404 `E404` / respuesta normal | 66, 67, 68 | confirmado / probable |
| Rutas que solo se parecen a `/msg`: `//msg`, `/msg%2F`, `/%6Dsg` (no se decodifica) y una ruta de 9.001 caracteres | 404 `E404` | 501, 502, 503, 506 | probable |
| `/msg?` con query vacía, `/msg` con una query de 9.000 caracteres y `/msg#x` con el fragmento en la línea del request | respuesta normal | 505, 507, 504 | probable |
| `Content-Type` ausente o `text/plain` con un cuerpo JSON válido: no se mira el header | respuesta normal | 508, 509 | probable |
| `bearer` en minúscula, dos espacios después de `Bearer` o el token sin `Bearer`: el esquema y el separador se comparan exactos | 401 `E001` | 510, 511, 1427 | probable |
| Un espacio o un tab al final del header se ignoran: el token sigue valiendo | respuesta normal | 1425, 1426 | probable |
| Cuerpo que no es JSON (texto, JSON truncado, vacío) | 400 `{"error":"E100","mensaje":"json inválido"}` | 69, 70, 71 | confirmado |
| JSON válido sin un campo `m` de tipo string (objeto vacío, `M`, número, null, array, string JSON) | 400 `{"error":"E102","mensaje":"falta m"}` | 72–78 | confirmado |
| Claves extra junto a `m` se ignoran; un `m` de 5.000 caracteres se procesa | respuesta normal | 79, 80 | probable |
| Con la clave `m` repetida gana la última: `{"m":5,"m":"PING;64"}` da pong | 200 `{"pong":true}` | 1290, 1315 | confirmado |
| `{"__proto__":{"m":"PING;64"}}` no aporta un `m`: no hay contaminación por prototipo | 400 `E102` | 1291, 1316 | confirmado |
| `HEAD`, `OPTIONS` y `PATCH` a `/msg` | 404 `E404`; en HEAD sin cuerpo | 10967–10969 | probable |
| `HEAD /health` con token: no se deriva de GET | 404 sin cuerpo | 10970 | probable |
| Cuerpo de más de 8.192 bytes, contados en bytes (8.192 pasa; 8.193 no; 8.200 bytes con `ñ`, que son 4.112 caracteres, tampoco) | 413 `{"error":"E101","mensaje":"cuerpo demasiado grande"}` | 10976, 10977, 10987, 10989 | probable |
| El tamaño se evalúa después de la ruta y del token: un cuerpo grande sin token da E001 y a `/nada` da E404 | 401 `E001` / 404 `E404` | 10984, 10985 | probable |
| JSON con más de 20 niveles de anidamiento. Arrays y objetos cuentan igual y el objeto exterior es el nivel 1; vale aunque `m` sea válido | 400 `E100` | 10999, 11007, 11011, 11012 | probable |
| JSON no estricto: `NaN`, `Infinity`, coma final, BOM al inicio | 400 `E100` | 10962–10966 | probable |
| Un número fuera de rango como `1e400` en una clave extra se acepta | respuesta normal | 10973 | probable |
| Todas las respuestas llevan `Content-Type: application/json; charset=utf-8`, sin `ETag` ni `X-Powered-By` (headers: no se comparan, sirven para la huella del stack, ver D6) | — | 10959–10970 | probable |
| El header `X-Req` cuenta los `/msg` autenticados del token y `/__reset` no lo reinicia | header, no se compara | todo el log | confirmado |

### 3.2 Integridad del mensaje

El mensaje se parte por `;`. El último segmento es el control y el resto es el cuerpo. Para calcular el control, el cuerpo se pasa a mayúsculas, cada letra A–Z se reemplaza por su posición en el alfabeto sin ceros a la izquierda (A→1, Z→26), los dígitos se dejan tal cual y todo lo demás se descarta (`;`, `-`, espacios, tildes, `ñ`, `ß`). Eso da un número N en decimal, y el control esperado es `98 − (N·100 mod 97)`, el mismo esquema que el dígito de un IBAN. Encontramos la fórmula sin gastar requests: tres TRANSFER que solo difieren en el monto fijan la constante y el multiplicador módulo 97, y después la fórmula explicó los 20 ejemplos.

| Regla | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Sin ningún `;` (incluye el mensaje vacío) | 400 `{"error":"E103","mensaje":"falta control"}` | 31, 36, 46 | confirmado |
| Algún segmento vacío (`PING;`, `;`, `PING;64;`, `ALTA;;85`) | 400 `{"error":"E104","mensaje":"segmento vacío"}` | 30, 37, 45, 47, 84 | confirmado |
| El control no es de uno o dos dígitos (`5X`, `114`, `+14`, `14.0`, `14 `, `014`) | 400 `{"error":"E201","mensaje":"control mal formado"}` | 17, 39, 131–135 | confirmado |
| El control tiene buen formato pero no coincide | 400 `{"error":"E202","mensaje":"control inválido"}` | 2, 38, 40, 44 | confirmado |
| Fórmula mod 97 descrita arriba | — | 1–20 y cada mensaje aceptado | confirmado |
| Se compara como texto: `03` no vale aunque el control sea 3, y `1` no reemplaza a `98` | 400 `E202` | 21, 24 | probable |
| `í`, `ñ` y `ß` se descartan; `ß` no se convierte en `SS` | — | 32, 222, 278, 279 | confirmado |
| PING no valida el control: acepta `XX`, `0`, `161`, `-33` | 200 `{"pong":true}` | 25–29, 81, 82 | confirmado |
| El nombre del comando no distingue mayúsculas, pero no se le quitan espacios | — | 11, 34, 35, 86, 91 | confirmado |
| El comando se pasa a mayúsculas solo en ASCII: `tranſfer` (ſ larga) y `pıng` (ı sin punto) no son comandos, aunque `toUpperCase` de JS los convierta | 400 `E301` con sugerencia TRANSFER / PING | 1239, 1261, 1241, 1263 | confirmado |

### 3.3 PING

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| `PING;<cualquier control>` | 200 `{"pong":true}` | 1, 49, 81 | confirmado |
| Con un argumento de más | 400 `{"error":"E302","mensaje":"aridad inválida"}` | 43, 83 | confirmado |

### 3.4 ALTA;nombre;control

Crea una cuenta con saldo 0. Acepta cualquier nombre no vacío: con tildes, numérico, con espacios, solo símbolos, de 300 o 3.000 caracteres, y también nombres repetidos.

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Nombre válido | 201 `{"cuentaId":"AC-0001"}`, después `AC-0002`, y así | 3, 4, 22, 32, 48, 114, 137, 138, 219–221 | confirmado |
| Dos argumentos | 400 `E302` | 20 | probable |
| Cinco ALTA en paralelo: ids únicos, asignados en el orden de llegada | `AC-0001`…`AC-0005` | 187–194 | probable |
| Más de 9.999 cuentas | sin probar; el reemplazo sigue numerando con 4 dígitos mínimos | — | supuesto |

### 3.5 CONSULTA;cuenta;control

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Cuenta existente (ojo: la clave es `cuenta_id`, en snake_case, y en ALTA es `cuentaId`). **v2:** el saldo es un string con el entero dividido por 100 y dos decimales (ver 3.12) | v1: 200 `{"cuenta_id":"AC-0001","saldo":0}`; v2: `"saldo":"0.00"` | 5, 8, 19; v2: 12635 | confirmado |
| Cuenta inexistente; el id se compara exacto, sin normalizar (`ac-0001`, `AC-1`, `AC-0001 `, un id `OP-`) | 404 `{"error":"E401","mensaje":"cuenta inexistente"}` | 15, 100, 101, 115, 136 | confirmado |
| Sin argumento | 400 `E302` | 142 | probable |

### 3.6 DEPOSITO;cuenta;monto;control

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Monto válido: entero positivo sin ceros a la izquierda ni signos | 200 `{"status":"recieved","operacionId":"OP-0001"}` | 6, 18, 93 | confirmado |
| Monto inválido: 0, negativo, decimal, `1e3`, letras, `007`, `+5`, con espacios, comas o puntos | 400 `{"error":"E303","mensaje":"monto inválido"}` | 94–99, 144, 206–213 | confirmado |
| Tope del monto: hasta 10 dígitos (9.999.999.999 pasa; 10.000.000.000 da E303). No es un tope binario: 2^31 y 2^32 pasan | 200 / 400 `E303` | 365–370, 371–374, 214, 277 | confirmado |
| El saldo no tiene tope ni desborda: acumula 5.000.000.000 | 200 `{"cuenta_id":"AC-0001","saldo":5000000000}` | 379, 382 | probable |
| No hay límite por depósito como el de TRANSFER | 200 con 1.000.000 | 93, 271–276 | confirmado |
| Cuenta inexistente | 404 `E401` | 100, 101 | confirmado |
| Se puede depositar en una cuenta bloqueada, y el depósito la desbloquea: pone en 0 los rechazos seguidos | 200 | 250, 323–324, 466–467 | confirmado |
| Un depósito en medio de una racha de rechazos también la corta | 200 | 359–363 | probable |
| Diez depósitos en paralelo: no se pierde ninguno (saldo 1023 = suma de 1 a 512) y los OP siguen el orden de llegada | 200 cada uno | 175–186 | probable |

### 3.7 TRANSFER;origen;destino;monto;control

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Transferencia válida | 200 `{"status":"recieved","operacionId":"OP-0002"}` | 7, 10, 109 | confirmado |
| Monto inválido (mismas reglas que DEPOSITO) | 400 `E303` | 111, 112 | confirmado |
| Origen igual a destino | 400 `{"error":"E304","mensaje":"origen y destino iguales"}` | 103, 140 | confirmado |
| Origen o destino inexistente | 404 `E401` | 104, 105, 106 | confirmado |
| Monto mayor que el límite entre cuentas de titulares distintos. v1: 100.000 (100.000 exacto pasa). **v2: 50.000** (50.000 pasa, 50.001 no; ver 3.12). Es por transferencia: seis de 100.000 seguidas pasan todas | 422 `{"error":"E506","mensaje":"límite excedido"}` | 9, 108, 109, 155–157, 386–392 | confirmado |
| Entre dos cuentas del mismo titular (el nombre del ALTA) no hay límite: 150.000 pasan, y con saldo insuficiente el error es E507 aunque el monto pase de 100.000 | 200 / 422 `E507` | 11575, 11782, 11783, 11794, 11795, 11805; control con titulares distintos: 11624, 11788 | confirmado |
| El titular se compara exacto, sin recortar ni normalizar: `Ana` y `ana`, `Ana` y ` Ana`, `José` y `Jose` son titulares distintos | 422 `E506` | 11800, 12609, 12614 | confirmado |
| Entre el mismo titular tampoco hay tope con montos de 10 dígitos | 200 | 12604 | probable |
| Saldo menor que el monto | 422 `{"error":"E507","mensaje":"saldo insuficiente"}` | 16, 246 | confirmado |
| Después de tres rechazos E506 o E507 seguidos con el mismo origen, la siguiente TRANSFER desde ese origen se bloquea, aunque alcance el saldo | v1: 409 `{"error":"E510","mensaje":"cuenta bloqueada"}`; **v2: 423** con `"intentos"` (ver 3.12) | 200, 249, 269, 319, 455 | confirmado |
| Solo cuentan E506 y E507. Tres E303, tres E304 o tres E401 seguidos no bloquean | la siguiente TRANSFER válida da 200 | 330–333, 337–340, 344–347 | confirmado |
| Un E303 en medio de la racha no la corta: E507, E507, E303, E507 bloquea igual | E510 | 351–355, 12579–12583 | confirmado |
| La racha cuenta por origen aunque cambie el destino | E510 al cuarto intento | 12590–12593 | probable |
| Un depósito rechazado (E303) no desbloquea | E510 sigue | 12584, 12585 | probable |
| Una transferencia exitosa desde la cuenta pone en 0 los rechazos | 200 | 258–262, 12570–12575 | confirmado |
| El bloqueo es por cuenta: otra cuenta con fondos transfiere normal, y la bloqueada puede recibir | 200 | 320, 321, 456 | confirmado |
| Lo único que la desbloquea es un depósito en ella (ver 3.6). Recibir una transferencia no la desbloquea ni corta la racha, ANULA tampoco, y el tiempo tampoco: sigue bloqueada a los 1, 5 y 10 minutos | E510 sigue | 456–457, 477–478, 485–487, 492–495 | confirmado |
| Mientras está bloqueada, E303, E304 y E401 se evalúan antes que E510, y E510 antes que E506 y E507 | 400 / 404 / 409 | 305–309 | probable |
| Cinco transferencias de 60 en paralelo con saldo 100: pasa una, las tres siguientes dan E507 y la quinta ya da E510 | 200, E507 ×3, E510 | 195–204 | probable |

### 3.8 ANULA;operación;control

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Primera anulación: revierte el efecto de un depósito o de una transferencia en las dos cuentas | 200 `{"ok":true,"anulada":"OP-0003"}` | 13, 19, 121, 124, 125 | confirmado |
| Segunda anulación de la misma operación | 200 `{"ok":false,"motivo":"ya anulada"}` | 14, 10015, 11027, 11736, 12194, 12204, 12299 | confirmado |
| No revisa saldo: puede dejar una cuenta en negativo | 200, saldo −50.000 o −50 | 122, 231 | confirmado |
| Operación inexistente o con otro formato (`op-0003`, `OP-1`, `OP-0000`, `OP-00001`, un id `AC-`) | 404 `{"error":"E402","mensaje":"operación inexistente"}` | 126–128, 223–225 | confirmado |
| Ids con nombres internos de JavaScript (`constructor`, `__proto__`, `toString`, `hasOwnProperty`, `valueOf`) no existen: CONSULTA, DEPOSITO y TRANSFER dan E401 y ANULA da E402 | 404 `E401` / `E402` | 1285–1288, 1299–1306, 1310–1313 | confirmado |
| ANULA no consume un número de operación | la siguiente operación toma el OP que seguía | 18, 129, 11738, 12183, 12205 | confirmado |

### 3.9 HALT (comando oculto)

Apareció porque la sugerencia de E301 busca entre todos los comandos, incluidos los no documentados: `HELP` sugirió `HALT` (log 171).

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| `HALT` con un argumento distinto de `1` (`AC-0001`, `CONFIRMAR`, `SI`, `YES`, `TRUE`, `OK`, `0`, `2`, `01`, `10`, `-1`, ` 1` y otros ocho) | 409 `{"error":"E520","mensaje":"operación destructiva: detiene el servicio; reenvía con confirmación"}` | 292, 11068–11128, 11140, 11146, 11178–11193 | confirmado |
| Después de un E520 el servicio sigue respondiendo | 200 | 294, 295, 11069, 11075 | confirmado |
| Mandar el mismo HALT dos veces seguidas no confirma | 409 `E520` las dos veces | 11152, 11153 | probable |
| `HALT` sin argumentos o con dos | 400 `E302` | 293, 11159 | confirmado |
| Una clave `confirmacion` o `confirm` en el JSON no confirma | 409 `E520` | 11165, 11171 | probable |
| `HALT;1` con el control bien calculado detiene el servicio para el token; el mismo request ya responde | 503 `{"error":"E599","mensaje":"service halted"}` | 11134, 11199 | confirmado |
| El control se valida antes: `HALT;1;20` no detiene | 400 `E202` | 11196, 11197 | probable |
| Detenido, todo `POST /msg` con token responde E599, incluidos PING, JSON inválido, sin `m`, sin `;`, control malo, comando desconocido y otro HALT | 503 `E599` | 11135, 11137, 11202–11207 | confirmado |
| Detenido, la ruta y el token se siguen evaluando antes | 404 `E404` / 401 `E001` | 11200, 11201 | probable |
| Detenido, `GET /health` no cambia: 200 con token, E001 sin token | 200 `{"ok":true}` / 401 | 11136, 11208, 11209 | confirmado |
| `/__reset` lo repara: estado en cero y HALT vuelve a pedir confirmación | 200, después `AC-0001` | 11138–11140, 11210, 11211 | confirmado |
| Detenido, un cuerpo de más de 8.192 bytes: E599 va antes que el tamaño | 503 `E599` | 11320, 11324 | confirmado |

### 3.10 Comando desconocido y sugerencia

| Caso | Respuesta exacta | Log | Confianza |
|---|---|---|---|
| Comando inexistente lejos de todos los conocidos (`SALDOS`, `TRANS`, `XXXX` y once palabras bancarias) | 400 `{"error":"E301","mensaje":"comando desconocido "}` (con espacio final) | 12, 89, 159–169, 242 | confirmado |
| A distancia de Levenshtein ≤ 2 de un comando, contando espacios y en mayúsculas | se agrega `"sugerencia":"<COMANDO>"` | 35, 85–88, 147–152, 170, 171, 232, 233, 236, 237, 240, 241 | confirmado |
| Las trasposiciones cuentan como dos cambios (Levenshtein, no Damerau): `PNIGX` y `TPANSFRE` no sugieren nada | sin sugerencia | 234, 235 | confirmado |
| La distancia cuenta caracteres, no unidades UTF-16: `PI😀😀` está a distancia 2 de PING | `"sugerencia":"PING"` | 1289, 1314 | confirmado |
| En un empate gana el comando que va primero en orden alfabético: HALT frente a PING (`PANT`, `HINT`), ALTA frente a PING (`PITA`, `AINA`) y frente a HALT (`HATA`), ANULA frente a HALT (`HULA`). Si PING estuviera primero en una tabla sin ordenar, habría ganado PING | `"sugerencia":"HALT"` o `"ALTA"` | 238, 239, 393–398 | confirmado |
| Barrido de 76 palabras bancarias y administrativas en inglés y español con el control bien calculado: ninguna existe, y fuera de `HELP` (que sugirió HALT) ninguna sugiere un comando desconocido | 400 `E301` | 159–174, 280–291, 400–447 | confirmado |

### 3.11 Orden de los errores

El orden medido es: E404 → E001 → E599 (solo con el servicio detenido) → E101 → E100 → E102 → E103 → E104 → E201 → E202 → E301 o E302 → E303 → E304 → E401 o E402 → E510 → E506 → E507. Cada paso tiene su evidencia: la ruta antes que el token (57) y que el tamaño (10985), el token antes que el cuerpo (296–298) y que el tamaño (10984), el control antes que el comando y que la aridad (38–41), E202 antes que E401 (44), E303 antes que E304 (141) y que E401 (139), E304 antes que E401 (140), E401 antes que E506 (106), E303, E304 y E401 antes que E510 (305–307), E510 antes que E506 y E507 (308, 309) y E506 antes que E507 (110). Con el servicio detenido por `HALT;1`, E599 va después de la ruta y del token (11200, 11201) y antes del tamaño (11320, 11324), del JSON y de todo lo demás (11202–11207). El comando y la aridad van antes que el monto: un comando a distancia 1 con monto 0 da E301 (11328, 11333) y una aridad equivocada con monto 0 da E302 (11329, 11330, 11334, 11335).

| Estación | Qué revisa | Error si falla | Log que prueba su lugar |
|---|---|---|---|
| 1. Ruta | Método y ruta exactos (`POST /msg`, `POST /__reset`, `GET /health`); cualquier otro método, incluidos HEAD y OPTIONS, no existe | 404 `E404` | 57 (antes que el token), 10985 (antes que el tamaño) |
| 2. Token | Bearer igual al token del equipo | 401 `E001` | 296–298 (antes que el cuerpo), 10984 (antes que el tamaño) |
| 2b. Detenido | El token no está detenido por un `HALT;1` posterior al último reset | 503 `E599` | 11200, 11201 (después de ruta y token), 11320, 11324 (antes que el tamaño), 11202–11207 (antes que el resto) |
| 2c. Tamaño | Cuerpo de 8.192 bytes o menos, contados en bytes | 413 `E101` | 10977, 10987, 10989 |
| 3. JSON | El cuerpo se puede parsear como JSON estricto y no pasa de 20 niveles de anidamiento | 400 `E100` | 69, 10962–10966, 11007, 11012 |
| 4. Campo m | `m` existe y es string | 400 `E102` | 72 |
| 5. Segmentos | Hay al menos un `;` y ningún segmento vacío | 400 `E103` / `E104` | 30, 31 (antes que el control) |
| 6. Control | Uno o dos dígitos e igual al calculado; PING la saltea | 400 `E201` / `E202` | 38–41 (antes que comando y aridad), 81 |
| 7. Comando y aridad | El comando existe y tiene la cantidad de argumentos de su fila | 400 `E301` (con sugerencia) / `E302`; HALT responde 409 `E520` | 12, 20; antes que el monto: 11328–11330, 11333–11335 |
| 8. Monto | Entero positivo de hasta 10 dígitos sin ceros a la izquierda | 400 `E303` | 139, 141 (antes que E304 y E401) |
| 9. Origen y destino | En TRANSFER, origen distinto de destino | 400 `E304` | 140 (antes que E401) |
| 10. Existencia | Las cuentas o la operación existen | 404 `E401` / `E402` | 106, 307 (antes que E506 y E510) |
| 11. Bloqueo | El origen no tiene 3 rechazos seguidos | 423 `E510` con `intentos` (v1: 409) | 308, 309 (antes que E506 y E507) |
| 12. Límite | Entre titulares distintos, monto de TRANSFER ≤ 50.000 (v1: 100.000) | 422 `E506` | 110 (antes que E507) |
| 13. Saldo | Saldo del origen ≥ monto | 422 `E507` | 16, 246 |
| 14. Efecto y respuesta | Aplica el cambio y responde con el cuerpo exacto | 200 o 201 | 1–20 |

### 3.12 Versión 2 del servicio (incidente de las 15:30)

La última corrida del canario igual a v1 terminó a las 15:35:11 (`t2-s270`, ids 12495–12553) y la primera respuesta distinta fue a las 15:57:17 (12565). Las corridas del canario de las 16:01 y 16:05 (`t2-s283`, `t2-s284`) son idénticas entre sí: v2 es estable, y `t2-s284` es la línea base nueva. De los 18 pasos del canario que difieren, estos tres cambios son las causas; el resto son efectos (una TRANSFER que ya no pasa corre la numeración de las operaciones siguientes y deja a ANULA sin su OP).

| Cambio | v1 | v2 | Log | Confianza |
|---|---|---|---|---|
| Saldo de CONSULTA como string: el entero dividido por 100 con dos decimales | `"saldo":40000` | `"saldo":"400.00"`; 0 → `"0.00"`, 991 → `"9.91"`, 9.999.999.999 → `"99999999.99"`, −1.000 → `"-10.00"` | 12635–12686 (dos corridas), 12780, 12787, 12789 | confirmado |
| Los montos de entrada no cambian de escala ni aceptan decimales | `10.50` → E303 | `10.50` → E303 | 12784 | probable |
| E510 responde 423 y agrega `intentos`: cuenta los E510 seguidos de la cuenta | 409 `{"error":"E510","mensaje":"cuenta bloqueada"}` | 423 `{"error":"E510","mensaje":"cuenta bloqueada","intentos":1}`; después 2, 3 | 12565, 12583, 12585, 12593, 12600, 12676, 12772–12774 | confirmado |
| `intentos` vuelve a 1 después del depósito que desbloquea | — | 1 | 12779 | probable |
| Límite por transferencia entre titulares distintos | 100.000 | 50.000: 50.000 pasa, 50.001, 75.000, 99.999 y 100.000 dan E506 | 12640, 12754–12764, 12854, 12856 | confirmado |
| Entre cuentas del mismo titular sigue sin límite | 150.000 pasan | 150.000 pasan | 12685 | confirmado |

Siguen igual en v2: la regla del bloqueo (3 rechazos, solo un depósito desbloquea), el titular exacto, ANULA, HALT y el resto de los 59 pasos del canario (tanda 021, ids 12554–12629; canario `t2-s283`).

## 4. Supuestos

| Supuesto | Por qué lo creemos | Riesgo si es falso | Estado |
|---|---|---|---|
| El set manda los pasos de una secuencia en serie, esperando cada respuesta | El original tiene un solo estado por token, y el README compara paso a paso con 5 s cada uno; con pasos en paralelo, ni el original daría respuestas reproducibles | Un test en paralelo podría ordenar distinto los ids | definido |
| El set llama a `/health` con el token del equipo | El original responde 401 sin token (log 53), y el contrato pide "con otro token o sin token, responde como el original" | La validación del entrypoint falla | pendiente: preguntar al staff |
| El reemplazo solo acepta el token del equipo, así que tiene un único estado | Es el único token del contrato | Si el set usara varios tokens, se mezclarían estados | definido |
| Lo que no medimos responde con el error más cercano en el orden de la sección 3.11 | Es la regla más simple que explica lo observado | Fallan casos no explorados | definido |

## 5. Casos difíciles

El control se compara como texto, así que `03` da E202 pero `014` da E201. PING no valida el control pero sí exige que exista. El bloqueo por tres rechazos depende de la historia de la cuenta, de modo que un test de 6 a 12 pasos puede terminar en E510 aunque el último mensaje sea válido; además, un E303 en medio no corta la racha pero un depósito sí la borra. ANULA puede dejar saldos negativos que después cambian los E507. La sugerencia de E301 depende de la distancia exacta, que incluye espacios y el comando oculto HALT. Las claves mezcladas (`cuentaId` en ALTA y `cuenta_id` en CONSULTA) y la palabra `recieved` hay que copiarlas al pie de la letra.

## 6. Fuera de alcance

No reproducimos el header `X-Req`, porque el README dice que los headers no se comparan. No persistimos el estado entre reinicios, porque cada test empieza con `/__reset`.

## 7. Arquitectura

El reemplazo es un solo proceso Node con tres partes: un router HTTP que resuelve rutas, token y JSON; un motor de reglas que recorre una lista ordenada de validaciones y una tabla de comandos; y el estado en memoria. Aparte está el laboratorio (arnés, generador diferencial, comparador, buscador de control, log y evals), que habla con el original y con el reemplazo pero nunca los conecta entre sí, porque el reemplazo no puede llamar al original.

Los diagramas están en `docs/arquitectura/` y su índice en `docs/arquitectura/README.md`: el reemplazo por dentro (`png/reemplazo.png`), el contexto (`png/contexto.png`), el laboratorio (`png/laboratorio.png`), el despliegue (`png/despliegue.png`) y el flujo del canario de las 15:30 (`png/canario.png`). El orden de validación está en la tabla de la sección 3.11, porque como diagrama de secuencia no se leía en una pantalla.

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| D1. Estado en memoria y Cloud Run con min=1 y max=1. Aprobada por Andres Parra a las 11:17. | Neon con 1 a 3 instancias, como pide la plantilla | El set le habla a un solo proceso y llama a `/__reset` antes de cada test, así que no hay estado que deba sobrevivir ni que compartir. Neon agregaría latencia de red y un punto de falla externo para guardar unos pocos KB. |
| D2. Reglas declarativas: una tabla de comandos (aridad, tipo de cada argumento, efecto, cuerpo de respuesta) y una lista ordenada de validaciones. Aprobada por Andres Parra a las 11:33. | Un `if` por comando con la lógica mezclada | Si a las 15:30 cambia un código, un límite, la aridad o el orden de los errores, se cambia una fila y no hay que rastrear el código. El orden queda escrito en un solo lugar y coincide con la sección 3.11. |
| D3. Reemplazo sin LLM. Aprobada por Andres Parra a las 11:33. | Un LLM de respaldo para lo que no conocemos | La comparación es exacta, carácter por carácter. Un LLM no es determinista, cuesta dinero y arriesga el límite de 5 s. Para lo desconocido aplicamos un supuesto escrito. |
| D4 (reemplazada por D8). Canario: cada 10 minutos desde las 15:00, `arnes.ts replay` de unos 45 requests que tocan cada error y cada comando, comparados con el log. Cuando detecta un cambio, se corre el diferencial completo sobre el área afectada (el comando o la etapa del pipeline donde apareció la diferencia). Aprobada por Andres Parra a las 11:33. | Repetir el log completo cada vez | 30 corridas de 45 requests son unos 1.350 requests, y detectamos el cambio en 10 minutos o menos sin agotar el cupo. El diferencial dirigido después del aviso encuentra lo que el canario no cubre. |
| D5. Las 3 corridas del set oculto se reservan: calibración, después del incidente y final. El feedback del día a día son las diferenciales locales contra el original. Aprobada por Andres Parra a las 11:33. | Usar el set oculto para iterar | Solo hay 3 corridas en el día y su resultado es un número sin detalle; una diferencial dice qué secuencia y qué paso difieren. Ver la sección 8. |
| D6. Node 26 con `node:http`, sin framework ni dependencias, en Cloud Run. Decidido por el equipo a las 12:50 con la regla acordada antes de medir: "si la huella dice Python, Python; si no, Node". | Python con `http.server` en Railway (el diseño individual del token 2); Express, Fastify, Flask o FastAPI | La huella apunta a JavaScript con un router propio: `NaN` e `Infinity` dan E100 (Python los acepta), `1e400` se acepta (Go no), `{"M":…}` da E102 (Go no distingue mayúsculas), `charset=utf-8` en todas las respuestas, sin `ETag` ni `X-Powered-By` (no es Express) y `HEAD /health` da 404 (Express y Fastify lo derivan de GET) (log 73, 10960–10973). Un framework agrega respuestas propias (405, redirecciones, HEAD y OPTIONS automáticos) que el original no tiene. Lo que JavaScript no hace solo y hay que escribir: el tope de 8.192 bytes medido con `Buffer.byteLength` y la profundidad máxima de 20, porque `JSON.parse` acepta 20.000 niveles. |
| D7. Un log por token (`logs/t1.jsonl`, `logs/t2.jsonl`) en rangos de ids separados, `lab/send.py` como único arnés y `experimentos.jsonl` generado con `lab/logs.py armar`. Decidido por el equipo a las 12:45. | Un solo archivo que escriben los dos; renumerar todo seguido | Con un archivo por token no hay conflictos de git ni ids repetidos. Renumerar seguido rompería todas las citas de este documento. `send.py` registra cada reset, la hora y, si se pide, los headers; `arnes.ts` no lo hacía. |
| D8. El canario corre desde las 13:00 cada 20 minutos (y a las 19:45 y 19:55) contra la última línea base aceptada, y reemplaza a D4. Decidido por el equipo a las 12:45. | D4: cada 10 minutos desde las 15:00 contra el log de la mañana | El servicio puede cambiar sin aviso y más de una vez; empezar a las 15:00 dejaba ciego el mediodía. La línea base móvil hace visible un segundo cambio o una reversión. |

### 7.1 Modelo de datos del estado

El estado vive en memoria, dentro del proceso. Guardamos solo lo que no se puede derivar: los números de la próxima cuenta y de la próxima operación salen del tamaño de cada colección, porque nada se borra, los rechazos no crean operaciones (log 9 y 10) y ANULA marca una operación sin crear otra (log 129).

| Entidad | Campo | Tipo y reglas | Lo cambia | Evidencia |
|---|---|---|---|---|
| Cuenta | `id` | `AC-` y el número con 4 dígitos mínimos, empezando en `AC-0001` | ALTA | log 3, 4, 92 |
| Cuenta | `nombre` | Texto no vacío. Se guarda, pero ninguna respuesta lo devuelve | ALTA | log 219–221 |
| Cuenta | `saldo` | Entero. Empieza en 0 y puede quedar negativo por ANULA | DEPOSITO, TRANSFER, ANULA | log 5, 122, 231 |
| Cuenta | `rechazosSeguidos` | Entero de 0 a 3. Un E506 o E507 con esta cuenta como origen suma 1; E303, E304 y E401 no lo tocan. Una TRANSFER exitosa desde la cuenta o un DEPOSITO en ella lo vuelven a 0; recibir una transferencia y ANULA no. Con 3, la cuenta está bloqueada para transferir (no se guarda aparte porque se deriva) | TRANSFER, DEPOSITO | log 249, 260–262, 269, 330–347, 351–363, 456–487 |
| Operación | `id` | `OP-` y el número con 4 dígitos mínimos, empezando en `OP-0001` | DEPOSITO, TRANSFER | log 6, 7, 129 |
| Operación | `tipo` | `DEPOSITO` o `TRANSFER` | — | log 6, 7 |
| Operación | `cuentas` | En un depósito, la cuenta destino; en una transferencia, origen y destino | — | log 13, 19, 124 |
| Operación | `monto` | Entero positivo, ya validado | — | log 6 |
| Operación | `anulada` | Sí o no. ANULA lo pasa a sí una única vez | ANULA | log 13, 14 |

`/__reset` vacía cuentas y operaciones, así que los dos contadores vuelven a 0001. No toca el token del equipo, que es configuración y no estado. En el original tampoco reinicia el header `X-Req` (log 1 a 295), que no reproducimos porque los headers no se comparan. Que el contador es por cuenta está confirmado (log 320): otra cuenta transfiere normal mientras AC-0001 está bloqueada.

### 7.2 Una fila de la tabla de comandos

Cada comando es una fila con los mismos campos. Las validaciones comunes (ruta, token, JSON, segmentos, control y nombre del comando) no están en la fila: las aplica el pipeline antes, en el orden de la sección 3.11. Esta es la fila completa de TRANSFER:

| Campo | Valor para TRANSFER | Evidencia |
|---|---|---|
| Nombre | `TRANSFER`, comparado en mayúsculas | probado en otros comandos (log 11, 34); supuesto para TRANSFER |
| Valida el control | Sí (solo PING no lo valida) | probado en ALTA y CONSULTA (log 2, 44) y PING (log 81); supuesto para TRANSFER |
| Aridad | 3 argumentos; otra cantidad da E302 | log 20 (ALTA), supuesto para TRANSFER |
| Argumentos y tipos | `origen`: id de cuenta, comparado como texto exacto. `destino`: id de cuenta. `monto`: `^[1-9]\d*$` hasta el tope, o E303 | log 111, 112, 136 |
| Reglas sin estado, en orden | `origen` distinto de `destino`, o E304 | log 103, 140, 141 |
| Reglas con estado, en orden | 1) existen `origen` y `destino`, o E401; 2) `origen` no está bloqueada, o E510; 3) `monto` ≤ 100.000, o E506; 4) saldo de `origen` ≥ `monto`, o E507 | log 104–106, 108–110, 305–309 |
| Rechazos que cuentan para el bloqueo | E506 y E507 suman 1 a `rechazosSeguidos` del origen; los demás errores no lo tocan | log 246–249, 266–269, 330–347 |
| Efecto | Resta `monto` al origen, suma `monto` al destino, crea la operación `TRANSFER` y pone en 0 los rechazos del origen | log 7, 8, 260–262 |
| Respuesta | 200 `{"status":"recieved","operacionId":"OP-NNNN"}` | log 7, 10 |
| Cómo la anula ANULA | Devuelve `monto` al origen y lo quita al destino, sin revisar saldo | log 13, 19, 121, 122 |

Si a las 15:30 cambia, por ejemplo, el límite, se edita la regla 3; si cambia el orden de dos errores, se reordena la lista. Ninguno de esos cambios toca el código del pipeline.

### 7.3 Concurrencia

Medimos que el original procesa en serie: diez depósitos en paralelo suman exacto y los ids siguen el orden de llegada (log 175–194), y de cinco transferencias en paralelo pasa solo una (log 198–204). El reemplazo obtiene lo mismo con una regla: el handler no hace `await` entre validar y modificar el estado. Node atiende un request por vez dentro del código síncrono, de modo que cada mensaje se valida y se aplica de forma atómica. La regla se verifica con el caso E-10.

## 8. Plan para medir

Medimos tres cosas distintas, cada una con su herramienta. El log mide que no rompemos lo que ya conocemos. Las pruebas diferenciales miden si generalizamos a secuencias que nadie armó a mano. El buscador de algoritmos de control nos deja reaccionar rápido si a las 15:30 cambia la validación. El set oculto solo se puede correr 3 veces en todo el día, así que no es nuestra herramienta de trabajo: el feedback de cada cambio sale de las diferenciales locales contra el original, y el set lo usamos tres veces para calibrar y confirmar.

| ID | Escenario | Resultado esperado | Métrica | Umbral | Cubre |
|---|---|---|---|---|---|
| E-01 | Regresión: todas las secuencias del log contra el reemplazo, con el comparador del README | Mismas respuestas | % de pasos iguales | 100 % | RF-01, RF-02, RF-03, RF-04 |
| E-02 | Diferencial: 100 secuencias nuevas con la forma del set (40 de 1 paso, 45 de 2 a 5, 15 de 6 a 12), mezcla de válidas e inválidas, primero al original y después al reemplazo | Mismas respuestas | % de secuencias idénticas | ≥ 90 % | RNF-03, RF-03 |
| E-03 | Diferencial de memoria: secuencias de 6 a 12 pasos con ANULA, saldos negativos y tres rechazos seguidos | Mismos ids, saldos y E510 | % de secuencias idénticas | ≥ 95 % | RF-05 |
| E-04 | Pares de errores combinados (log 38–44, 106, 110, 139–141) | Gana el mismo error | pasos iguales | 100 % | RF-04 |
| E-05 | 200 controles al azar, correctos y alterados, calculados sin requests | E201 y E202 donde corresponde | pasos iguales | 100 % | RF-02 |
| E-06 | Canario después de las 15:30 | Diff con id viejo, id nuevo y hora | minutos hasta detectar | ≤ 10 | RF-06 |
| E-07 | Buscador de control contra los pares (cuerpo, control) aceptados del log | Una sola fórmula que explica todos | pares explicados | 100 % | RF-02, RF-06 |
| E-08 | Las 100 secuencias de E-02 contra Cloud Run | Rápidas y gratis | p95 y USD por caso | ≤ 50 ms y 0 | RNF-01, RNF-02 |
| E-09 | Nueva revisión desplegada, primer `/health` con token | 200 | segundos hasta el 200 | ≤ 10 | RNF-04 |
| E-10 | Diez depósitos y cinco transferencias en paralelo contra el reemplazo, como en el log 175–204 | Mismo saldo final y un solo éxito | secuencias iguales | 100 % | RF-05 |
| E-11 | Las 3 corridas del set oculto (calibración, después del incidente, final) | El resultado del set se parece al de E-02 | diferencia entre el % del set y el % de E-02 | ≤ 10 puntos | RNF-03, RF-06 |

### 8.1 Las tres corridas del set oculto

| Corrida | Cuándo | Condición para gastarla | Para qué sirve |
|---|---|---|---|
| 1. Calibración | Después del primer deploy completo, con los siete comandos y E-01 al 100 % (hacia las 14:00) | E-02 ≥ 90 % | Comparar el % del set con el % de E-02. Si el set da más de 10 puntos menos, el generador no cubre algo que el set sí usa, y revisamos la mezcla de mutaciones antes de seguir. |
| 2. Después del incidente | Cuando el reemplazo ya refleja el cambio de las 15:30 (hacia las 17:30) | E-01 al 100 % sobre las líneas que no cambiaron y E-02 ≥ 90 % contra la versión nueva | Confirmar que nos adaptamos al cambio y que no rompimos lo que no cambió. |
| 3. Final | Antes de congelar el entrypoint (hacia las 19:15) | Ningún cambio de reglas después de esta corrida | Dejar registrado el resultado de la versión que se entrega. Después solo se toca el código si el canario detecta otro cambio. |

Entre corrida y corrida, cada cambio del reemplazo se valida con E-01 (regresión) y con una tanda de E-02 (diferencial). Esas dos sí dicen qué secuencia y qué paso difieren, y no consumen el cupo del set.

### 8.2 Herramientas

**Pruebas diferenciales.** Un generador arma secuencias aleatorias a partir de una gramática de los siete comandos. Usa ids que existen en el estado de la secuencia y les aplica mutaciones: control alterado o mal formado, aridad de más o de menos, montos en los bordes (0, 100.000, 100.001, 10^9), ids inexistentes, minúsculas, comandos a distancia 1 a 3, y rachas de rechazos. Cada secuencia se manda al original con el arnés, que la registra en el log con su hipótesis, y después se reproduce contra el reemplazo. Cada diferencia es una regla que no conocemos: se convierte en hipótesis, se prueba con un experimento dirigido y entra al catálogo. Una corrida de 100 secuencias cuesta unos 450 requests (incluidos los resets), y fijamos un tope de 1.500 por corrida.

**Holdout.** Las secuencias del log se armaron a mano para probar hipótesis, así que no miden generalización. Las usamos solo como regresión (E-01): si una falla, rompimos algo que ya sabíamos. La generalización la mide E-02, porque sus secuencias no las elegimos nosotros.

**Buscador de algoritmos de control.** Es un script offline que no hace requests. Toma todos los pares (cuerpo, control) aceptados del log y prueba candidatos: MOD 97-10 con distintos mapeos de letras (A=1, A=10, ASCII, con y sin relleno), Luhn, suma de códigos módulo N, sumas ponderadas por posición y polinomios con base b módulo 97. Devuelve las fórmulas que explican el 100 % de los pares. Así encontramos la fórmula actual, y es lo que corremos si el canario empieza a ver E202 donde antes no los había.

## 9. Plan de la especificación

Cada comportamiento lleva un ID por sección (ENT-xx, INT-xx, CMD-ALTA-xx, MEM-xx, ERR-xx, CAM-xx, RIE-xx), una descripción, los ids del log que lo prueban y su confianza. Cada fila del catálogo de la sección 3 pasa a ser una fila de la especificación con la misma evidencia. Cada comportamiento tiene además un caso en `evals/cases.jsonl` que cita su ID, de modo que la cadena comportamiento → línea del log → caso de prueba se puede recorrer en las dos direcciones. Un script chequea que cada id citado exista en el log y que el replay de esas líneas siga dando lo mismo. Si después de las 15:30 una línea cambia, el comportamiento queda marcado para revisión. La confianza sigue la regla de la sección 3, y ante la duda escribimos probable y no confirmado.

## 10. Pareja y presupuesto

Tenemos dos tokens con 8.000 requests cada uno y estados separados. Como el límite de 10 por segundo es por token, los dos pueden trabajar a la vez sin estorbarse.

| Etapa | Token 1 | Token 2 |
|---|---|---|
| Diseño, hasta las 12:00 | unos 530 (497 líneas más los resets sin registrar) | 958 |
| 12:00 a 13:00 | — | 54: huella del stack, tope del cuerpo y profundidad |
| 13:00 a 20:00 | Experimentos dirigidos cuando las evals del reemplazo muestren algo que el log no explica, hasta 1.500 | Canario (unos 45 requests cada 20 minutos, unos 1.000), diferencial (hasta 3.000), HALT y tandas dirigidas después de cada cambio |
| Total planificado | unos 2.000 | unos 5.000 |

Cada token admite 8.000 por día, así que a los dos les queda reserva. El canario y el diferencial van en el token 2 por turnos; el token 1 queda libre para preguntas puntuales del servidor y como respaldo si el token 2 se acerca al tope.

## 11. Riesgos

Estos son los riesgos del servicio original que un cliente nuevo no debería heredar. Irán a la sección 7 de la especificación.

| Riesgo | Evidencia | Cómo lo cerraríamos |
|---|---|---|
| ANULA no revisa saldo y deja cuentas en negativo | log 122, 231 | Rechazar la anulación si deja saldo negativo, con un código de error propio |
| El control es un dígito de verificación que cualquiera puede calcular: detecta errores de tipeo pero no autentica ni protege la integridad | sección 3.2 | Firmar el mensaje con HMAC y un secreto por cliente |
| La ruta se evalúa antes que el token, así que sin credenciales se puede averiguar qué rutas existen (404 contra 401) | log 57 | Autenticar primero y responder 401 igual para todo |
| `/health` pide token, así que un balanceador u orquestador no puede chequearlo | log 53 | `/health` público y sin datos |
| HALT es un comando destructivo y oculto al que llega cualquier cliente con un token válido, la sugerencia de E301 revela su nombre, y la confirmación es un `1` que se adivina en pocos intentos | log 171, 292, 11134 | Sacarlo de la API pública y no sugerir comandos internos |
| Tres rechazos seguidos bloquean la cuenta de origen, y un cliente que reintenta en paralelo bloquea su propia cuenta (log 200). Al mismo tiempo el bloqueo no protege nada: un depósito de cualquier monto, incluso 5, lo levanta (log 466–467) | log 200, 249, 269, 466 | Contar los rechazos por cliente en una ventana de tiempo, y desbloquear solo con una acción explícita de un operador |
| Respuestas inconsistentes (`cuentaId` frente a `cuenta_id`, `recieved`) de las que dependen los clientes actuales | log 3, 5, 6 | Publicar una versión nueva de la API y mantener la vieja |

## 12. Pendientes con su hipótesis

El tope del monto, qué rechazos cuentan para el bloqueo, su alcance, qué lo desbloquea, la posición de E510 en el orden y los desempates de la sugerencia se cerraron durante el diseño; la confirmación de HALT, el orden de E301/E302 frente a E303 y las rutas y headers raros, durante la ejecución. Están en 3.1, 3.6, 3.7, 3.9, 3.10 y 3.11 con su evidencia. En las rutas raras el reemplazo en Cloud Run responde distinto que el original en `//msg`, `/%6Dsg` y `/msg#x`, por el proxy de Google y no por el código (evals del reemplazo, no son líneas del log). Queda abierto:

| Pendiente | Hipótesis | Experimento propuesto |
|---|---|---|
| Comandos ocultos fuera del barrido | No hay más: el barrido de 76 palabras solo encontró HALT | Sondeo por sugerencia con palabras nuevas si el diferencial muestra un E301 inesperado |
| Desborde de los ids `AC-9999` y `OP-9999` | Pasan a 5 dígitos | No se prueba: cuesta 10.000 requests. Supuesto del reemplazo: seguir con 5 dígitos |
| Bloqueo después de 10 minutos | Permanente hasta un depósito o `/__reset` (sigue bloqueada a los 1, 5 y 10 min) | Re-chequear una cuenta bloqueada a los 30 minutos |
