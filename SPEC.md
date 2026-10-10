# Especificación del servicio "caja negra"

Describe el servicio tal como responde desde las 15:57 del 10 de octubre (versión 2), que es la vigente al cierre de la ejecución. Lo que cambió respecto de la versión de la mañana está en la sección 6.

**Evidencia.** Los números son ids de `experimentos.jsonl`. Cada línea tiene los campos del README (`id`, `seq`, `x_req`, `hipotesis`, `request`, `status`, `response`, `conclusion`) y además `token` (t1 o t2, nunca el token en sí), `ts` (hora UTC) y, solo cuando la sonda se sale de un `POST /msg` normal, `metodo`, `ruta`, `auth`, `content_type` o `headers`. Los ids 1–497 se grabaron sin registrar el `POST /__reset` de inicio de secuencia ni la hora: cada secuencia de ese rango empieza tras un reset que no tiene línea propia. Los ids 10001–10958 se renumeraron desde otro archivo y conservan su número viejo en `id_original`.

**Confianza.** *Confirmado*: lo vimos en dos o más líneas, en secuencias distintas. *Probable*: lo vimos una vez o lo inferimos. *Supuesto*: no lo probamos; es lo que hace nuestro reemplazo.

**Convención.** "Error E303" significa el cuerpo `{"error":"E303","mensaje":…}` con el status y el mensaje de la sección 5.

## 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ENT-01 | Existen tres rutas: `POST /msg`, `POST /__reset` y `GET /health`. Cualquier otra ruta, o un método distinto en una ruta conocida, da error E404, con o sin token | 57–65, 12651 | confirmado |
| ENT-02 | `HEAD`, `OPTIONS` y `PATCH` a `/msg`, y `HEAD /health`, dan 404; en HEAD sin cuerpo | 10967–10970 | probable |
| ENT-03 | La ruta se compara exacta: `/msg/` y `/MSG` dan E404 | 66, 67 | probable |
| ENT-04 | La ruta no se normaliza ni se decodifica: `//msg`, `/msg%2F`, `/%6Dsg`, `/./msg`, `/msg/.`, `/msg%00` y una ruta de 9.001 caracteres dan E404. La query se ignora (`/msg?x=1`, `/msg?`, una query de 9.000 caracteres) y `/msg#x` en la línea del request funciona como `/msg` | 68, 501–507, 1422–1424 | probable |
| ENT-05 | Autenticación con `Authorization: Bearer <token>`, comparada exacta salvo los espacios finales (ver ENT-18). Sin header, sin el esquema `Bearer`, con un token inventado, con esquema Basic, con `bearer` en minúscula o con dos espacios después de `Bearer`: error E001 | 50, 51, 52, 510, 511, 1427 | confirmado |
| ENT-06 | `POST /__reset` con token responde 200 `{"ok":true}`; sin token o con un token inventado, E001 | 55, 56, 570, 571, 10040, 12554, 12850 | confirmado |
| ENT-07 | `GET /health` con token responde 200 `{"ok":true}`; sin token, E001 | 53, 54, 11136, 11208, 11209 | confirmado |
| ENT-08 | Un cuerpo de más de 8.192 bytes, contados en bytes y no en caracteres, da error E101 (413). 8.192 pasa | 10976, 10977, 10987, 10989 | confirmado |
| ENT-09 | El cuerpo tiene que ser JSON estricto: texto, JSON truncado, cuerpo vacío, `NaN`, `Infinity`, coma final o BOM al inicio dan error E100 | 69, 70, 71, 10962–10966 | confirmado |
| ENT-10 | Más de 20 niveles de anidamiento dan E100 aunque `m` sea válido; arrays y objetos cuentan igual y el objeto exterior es el nivel 1 | 10999, 11007, 11011, 11012, 10992–10996, 11000–11005 | confirmado |
| ENT-11 | Sin un campo `m` de tipo string (objeto vacío, `M`, número, null, array) da error E102 | 72–78, 12657 | confirmado |
| ENT-12 | Las claves extra junto a `m` se ignoran, incluso un número fuera de rango como `1e400`; un `m` de 5.000 caracteres se procesa | 79, 80, 10973 | probable |
| ENT-13 | El header `Content-Type` no se mira: ausente o `text/plain` con un cuerpo JSON válido responde normal | 508, 509 | probable |
| ENT-14 | Todas las respuestas con cuerpo son JSON con `Content-Type: application/json; charset=utf-8`. El header `X-Req` cuenta los `/msg` autenticados del token y `/__reset` no lo reinicia (los headers no se comparan) | 10959–10970, 11860, 11862 | confirmado |
| ENT-15 | Solo vale el token del equipo; cualquier otro token recibe E001 y no tiene estado propio | — | supuesto |
| ENT-16 | Si la clave `m` aparece dos veces en el JSON, vale la última: `{"m":5,"m":"PING;64"}` responde pong | 1290, 1315 | confirmado |
| ENT-17 | `{"__proto__":{"m":"PING;64"}}` no cuenta como `m`: error E102 | 1291, 1316 | confirmado |
| ENT-18 | Un espacio o un tab al final del header `Authorization` se ignoran: el token sigue valiendo | 1425, 1426 | probable |
| ENT-19 | Los escapes del JSON se decodifican antes de leer `m`: `{"m":"PING\u003b64"}` y `{"\u006d":"PING;64"}` responden pong | 1410, 1411 | probable |
| ENT-20 | `GET /health` ignora el cuerpo y la query, y `POST /__reset` ignora la query | 1429, 1430, 1435 | probable |
| ENT-21 | El tope de 8.192 bytes se mide sobre el cuerpo crudo, antes de decodificar escapes: 8.300 bytes de `\u0041` dan E101 aunque decodificados sean menos | 1440 | probable |

## 2. Integridad

`m` tiene la forma `COMANDO;arg1;…;control`. Se parte por `;`: el último segmento es el control y el resto es el cuerpo.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| INT-01 | Sin ningún `;` (incluido `m` vacío): error E103 | 31, 36, 46, 12658 | confirmado |
| INT-02 | Algún segmento vacío (`PING;`, `;`, `PING;64;`, `ALTA;;85`): error E104. Los segmentos no se recortan | 30, 37, 45, 47, 84 | confirmado |
| INT-03 | El control tiene que ser de uno o dos dígitos ASCII; si no (`5X`, `114`, `+14`, `14.0`, `14 `, `014`, `１４` en ancho completo, 6.000 dígitos): error E201 | 17, 39, 131–135, 1409, 1443 | confirmado |
| INT-04 | Control esperado: del cuerpo se descarta todo lo que no sea letra A–Z o dígito (`;`, `-`, espacios, tildes, `ñ`, `ß`), se pasa a mayúsculas, cada letra se reemplaza por su posición (A=1 … Z=26, sin ceros a la izquierda) y los dígitos quedan igual. Eso da un número N y el control es `98 − (N·100 mod 97)`. Ejemplo: `PING` → P=16, I=9, N=14, G=7 → N = 169147 → control 64 | 1–20, 11782, 12854 | confirmado |
| INT-05 | Los caracteres no ASCII se descartan antes de pasar a mayúsculas: `ß` no cuenta como `SS` | 32, 222, 278, 279 | confirmado |
| INT-06 | El control se compara como texto: `03` no vale aunque el esperado sea 3. Si no coincide: error E202 | 2, 21, 24, 38, 40, 44 | confirmado |
| INT-07 | PING no valida el control: `PING;XX`, `PING;0`, `PING;161` y `PING;-33` responden pong | 25–29, 81, 82, 1442 | confirmado |
| INT-08 | El nombre del comando no distingue mayúsculas (`CONSULTa` funciona), pero solo en ASCII: `tranſfer` y `pıng` no son comandos. Tampoco se le quitan espacios: `PING ` no es PING | 11, 34, 35, 86, 91, 12641, 1239, 1241, 1261, 1263 | confirmado |

## 3. Comandos

Las respuestas de error siguen el orden de la sección 5: si un mensaje tiene varios problemas, responde el primero.

**PING;control**

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-PING-01 | 200 `{"pong":true}`, sin estado | 1, 49, 81 | confirmado |
| CMD-PING-02 | Con argumentos: error E302 | 43, 83 | confirmado |

**ALTA;nombre;control**: crea una cuenta con saldo 0.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-ALTA-01 | 201 `{"cuentaId":"AC-0001"}`; la siguiente es `AC-0002`, con cuatro dígitos | 3, 4, 22, 48, 114 | confirmado |
| CMD-ALTA-02 | Acepta cualquier nombre no vacío: con tildes, numérico, con espacios, un solo espacio, solo símbolos, de 3.000 caracteres, en ancho completo o con letras como `ſ` y `K` (signo kelvin), y nombres repetidos | 32, 137, 138, 219–221, 12625, 12627, 1403, 1405, 1407 | confirmado |
| CMD-ALTA-03 | El nombre queda guardado como titular de la cuenta (ver CMD-TRANSFER-06) | 11782, 11788 | confirmado |
| CMD-ALTA-04 | Con dos o más argumentos (también con 3.500): error E302 | 20, 1441 | confirmado |
| CMD-ALTA-05 | Pasadas las 9.999 cuentas se sigue numerando con cuatro dígitos mínimos | — | supuesto |

**CONSULTA;cuenta;control**

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-CONSULTA-01 | 200 `{"cuenta_id":"AC-0001","saldo":"0.00"}`. La clave es `cuenta_id` (en ALTA es `cuentaId`). El saldo es un string: el saldo interno entero dividido por 100, con dos decimales. Un saldo de 40.000 se ve como `"400.00"` y uno de 991 como `"9.91"` | 12635, 12638, 12671, 12680, 12780, 12787 | confirmado |
| CMD-CONSULTA-02 | Un saldo negativo se ve con signo: `"-10.00"` | 12789 | probable |
| CMD-CONSULTA-03 | Cuenta inexistente: error E401. El id se compara exacto (`ac-0001`, `AC-1`, `AC-0001 `, `ＡＣ－０００１` en ancho completo o con una `А` cirílica no existen) | 15, 100, 101, 115, 136, 1419, 1420 | confirmado |
| CMD-CONSULTA-04 | Sin argumento: error E302 | 142 | probable |

**DEPOSITO;cuenta;monto;control**

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-DEPOSITO-01 | 200 `{"status":"recieved","operacionId":"OP-0001"}` (así, con "recieved") y suma el monto al saldo | 6, 18, 93 | confirmado |
| CMD-DEPOSITO-02 | Monto válido: entero de 1 a 10 dígitos sin ceros a la izquierda, signos, espacios ni decimales (`^[1-9][0-9]{0,9}$`). 0, negativos, `10.50`, `1e3`, `007`, `+5`, `１０` en ancho completo o 11 dígitos: error E303 | 94–99, 144, 206–213, 365–374, 12784, 1408 | confirmado |
| CMD-DEPOSITO-03 | No hay límite por depósito | 93, 271–276, 12670 | confirmado |
| CMD-DEPOSITO-04 | Cuenta inexistente: error E401 | 100, 101, 11349, 12119 | confirmado |
| CMD-DEPOSITO-05 | El saldo no tiene tope ni desborda | 12671; en v1: 379, 382 | probable |

**TRANSFER;origen;destino;monto;control**

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-TRANSFER-01 | 200 `{"status":"recieved","operacionId":"OP-0002"}`; resta del origen y suma al destino | 7, 12758, 1337 | confirmado |
| CMD-TRANSFER-02 | Monto con las mismas reglas que DEPOSITO: si no, error E303 | 111, 112, 12580 | confirmado |
| CMD-TRANSFER-03 | Origen igual a destino: error E304 | 103, 140, 12629 | confirmado |
| CMD-TRANSFER-04 | Origen o destino inexistente: error E401 | 104, 105, 106, 12667 | confirmado |
| CMD-TRANSFER-05 | Entre cuentas de titulares distintos, un monto mayor que 50.000 da error E506. 50.000 pasa; 50.001, 75.000, 99.999 y 100.000 no | 12640, 12754, 12756, 12758, 12760, 12854, 12856 | confirmado |
| CMD-TRANSFER-06 | Entre dos cuentas del mismo titular no hay límite: pasan 150.000 y 9.999.999.999. Si no alcanza el saldo, el error es E507 aunque el monto pase del límite | 11782, 11794, 12604, 12685, 11575, 11805, 1295, 1320 | confirmado |
| CMD-TRANSFER-07 | El titular se compara exacto, sin recortar ni normalizar: `Ana` y `ana`, `Ana` y ` Ana`, `José` y `Jose` son titulares distintos | 11800, 12609, 12614 | confirmado |
| CMD-TRANSFER-08 | El límite es por transferencia, no acumulado: varias transferencias seguidas dentro del límite pasan todas. Medido en v1, con seis de 100.000 seguidas; en v2 no lo repetimos | 386–392 | probable |
| CMD-TRANSFER-09 | Saldo del origen menor que el monto: error E507 | 16, 246, 12557 | confirmado |
| CMD-TRANSFER-10 | Una cuenta bloqueada (sección 4) recibe error E510 | 12565, 12676 | confirmado |
| CMD-TRANSFER-11 | La comparación del titular es byte a byte, sin normalizar Unicode ni truncar: `José` con tilde compuesta y con tilde combinada son distintos, y dos nombres de 4.001 caracteres que solo difieren en el último también | 1413–1416, 1447–1450 | probable |

**ANULA;operación;control**

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-ANULA-01 | 200 `{"ok":true,"anulada":"OP-0003"}` y revierte el efecto: un depósito resta el monto de la cuenta; una transferencia lo devuelve al origen y lo resta del destino | 121, 124, 125, 1117, 1141, 12620 | confirmado |
| CMD-ANULA-02 | Anular de nuevo la misma operación: 200 `{"ok":false,"motivo":"ya anulada"}` | 11736, 12194; en v1: 14, 10015, 11027 | confirmado |
| CMD-ANULA-03 | No revisa saldos: puede dejar una cuenta en negativo | 12789; en v1: 122, 231 | confirmado |
| CMD-ANULA-04 | Operación inexistente o con otro formato (`op-0003`, `OP-1`, `OP-0000`, `OP-00001`, un id `AC-`): error E402 | 126–128, 223–225 | confirmado |

**HALT;argumento;control** (comando no documentado)

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-HALT-01 | Con un argumento distinto de `1` (se probaron 20, entre ellos `AC-0001`, `CONFIRMAR`, `SI`, `YES`, `0`, `01`, ` 1`): error E520 (409) y el servicio sigue respondiendo | 292, 294, 11068–11128, 11178–11193 | confirmado |
| CMD-HALT-02 | `HALT;1` con el control correcto detiene el servicio para el token: el mismo request ya responde error E599 (503). También en minúsculas (`halt;1`) | 11134, 11199, 12623 | confirmado |
| CMD-HALT-03 | Sin argumentos o con dos: error E302 | 293, 11159 | confirmado |
| CMD-HALT-04 | Mandar el mismo HALT dos veces, o agregar `confirmacion` o `confirm` al JSON, no confirma | 11152, 11153, 11165, 11171 | probable |

**Comando desconocido**

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-OTRO-01 | Un comando que no existe da 400 `{"error":"E301","mensaje":"comando desconocido "}`, con un espacio al final del mensaje | 12, 89, 159–169 | confirmado |
| CMD-OTRO-02 | Si el nombre (en mayúsculas ASCII, sin recortar espacios) está a distancia de Levenshtein ≤ 2 de un comando, se agrega `"sugerencia":"<COMANDO>"`. Las trasposiciones cuentan como dos cambios | 35, 85–88, 147–152, 234, 235 | confirmado |
| CMD-OTRO-03 | En un empate gana el comando que va primero en orden alfabético (ALTA, ANULA, CONSULTA, DEPOSITO, HALT, PING, TRANSFER). La sugerencia incluye HALT | 171, 238, 239, 393–398 | confirmado |
| CMD-OTRO-04 | No hay más comandos: 76 palabras bancarias y administrativas, con el control bien calculado, dan E301 | 159–174, 280–291, 400–447 | probable |
| CMD-OTRO-05 | La distancia se cuenta en caracteres (code points), no en unidades UTF-16 ni en grafemas: `PI😀😀` sugiere PING, y `PI` más un emoji de familia (5 code points) no sugiere nada | 1289, 1314, 1402 | confirmado |
| CMD-OTRO-06 | Los caracteres de control cuentan como cualquier otro: `PING\u0007` sugiere PING. Cadenas con HTML o SQL son solo comandos desconocidos | 1433, 1431, 1432 | probable |

## 4. Memoria entre requests

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| MEM-01 | Cada token tiene su estado. `POST /__reset` lo vuelve al inicio: sin cuentas ni operaciones, contadores en cero, sin bloqueos y sin HALT | 11138–11140, 11210, 11211, 12555, 12851 | confirmado |
| MEM-02 | Las cuentas se numeran `AC-0001`, `AC-0002`… en orden de creación. Las operaciones se numeran `OP-0001`… con un solo contador para depósitos y transferencias | 3, 4, 6, 7, 519, 520, 531, 12851–12853 | confirmado |
| MEM-03 | Solo una operación exitosa toma número: una transferencia rechazada y ANULA no consumen | 9, 129, 531, 11738, 12183 | confirmado |
| MEM-04 | Rechazos seguidos: cada TRANSFER rechazada por E506 o E507 suma uno a la cuenta de origen. Con tres seguidos la cuenta queda bloqueada y la siguiente TRANSFER desde ella da E510, aunque el monto y el saldo alcancen | 200, 12557–12565, 12590–12593, 743, 765 | confirmado |
| MEM-05 | Solo cuentan E506 y E507: tres E303, E304 o E401 seguidos no bloquean, y un E303 en medio no corta la racha | 330–333, 337–340, 344–347, 351–354, 12579–12583 | confirmado |
| MEM-06 | Una TRANSFER exitosa desde la cuenta pone la racha en cero | 258–262, 12570–12575 | confirmado |
| MEM-07 | La racha es por cuenta de origen, aunque cambie el destino | 12590–12593 | probable |
| MEM-08 | El bloqueo es por cuenta: otra cuenta transfiere normal, y la bloqueada puede recibir | 320, 321, 456 | confirmado |
| MEM-09 | Solo un depósito exitoso en la cuenta la desbloquea y pone la racha en cero. Recibir una transferencia o ANULA no la desbloquean. En v1 siguió bloqueada a los 1, 5 y 10 minutos, en una sola secuencia (492–495) | 250, 323, 324, 466, 467, 456, 970, 993, 1003, 1011, 492–495 | confirmado |
| MEM-10 | Un depósito rechazado (E303) no desbloquea, y anular el depósito que desbloqueó no vuelve a bloquear: hacen falta otros tres rechazos | 12584, 12585, 12560–12565, 1141, 1142, 1212, 1213 | confirmado |
| MEM-11 | Cada E510 seguido de la misma cuenta incrementa `intentos` (1, 2, 3… se vio hasta 6); tras el depósito que desbloquea, el próximo E510 vuelve a empezar en 1 | 12772–12774, 12583, 12585, 12779, 1458–1463 | confirmado |
| MEM-12 | El titular de cada cuenta (el nombre del ALTA) decide si una transferencia tiene límite (CMD-TRANSFER-05 a 07) | 11782, 11788 | confirmado |
| MEM-13 | Después de `HALT;1` el token queda detenido hasta el próximo reset: todo `POST /msg` con token da E599, incluso PING, JSON inválido o un cuerpo demasiado grande. `GET /health` sigue en 200 | 11135, 11137, 11202–11207, 11320, 11324, 11136, 11209 | confirmado |
| MEM-14 | Los mensajes se procesan de a uno: con depósitos o ALTA en paralelo no se pierde ninguno y los ids siguen el orden de llegada | 175–194 | probable |
| MEM-15 | Un bloqueo no expira solo, tampoco después de 10 minutos | — | supuesto |
| MEM-16 | Cuentas y operaciones se buscan por id exacto: nombres internos de JavaScript como `constructor`, `__proto__`, `toString`, `hasOwnProperty` o `valueOf` dan E401 (cuentas) o E402 (operaciones) | 1285–1288, 1299–1306, 1310–1313 | confirmado |

## 5. Errores

Cada respuesta tiene un solo error: el de la primera validación que falla, en el orden de la tabla.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ERR-01 | E404 → 404 `{"error":"E404","mensaje":"ruta desconocida"}`. Primero de todos, antes que el token | 57, 10985 | confirmado |
| ERR-02 | E001 → 401 `{"error":"E001","mensaje":"no autorizado"}`. Antes que el cuerpo y su tamaño | 296–298, 10984 | confirmado |
| ERR-03 | E599 → 503 `{"error":"E599","mensaje":"service halted"}`. Solo con el token detenido; después de E404 y E001 y antes que todo lo demás, incluido el tamaño | 11200, 11201, 11202–11207, 11320, 11324 | confirmado |
| ERR-04 | E101 → 413 `{"error":"E101","mensaje":"cuerpo demasiado grande"}` | 10977, 10987 | confirmado |
| ERR-05 | E100 → 400 `{"error":"E100","mensaje":"json inválido"}` | 69, 11007 | confirmado |
| ERR-06 | E102 → 400 `{"error":"E102","mensaje":"falta m"}` | 72, 73, 12657 | confirmado |
| ERR-07 | E103 → 400 `{"error":"E103","mensaje":"falta control"}` | 31, 36, 12658 | confirmado |
| ERR-08 | E104 → 400 `{"error":"E104","mensaje":"segmento vacío"}` | 30, 37, 12659 | confirmado |
| ERR-09 | E201 → 400 `{"error":"E201","mensaje":"control mal formado"}`. Antes que el comando y la aridad | 17, 39, 41 | confirmado |
| ERR-10 | E202 → 400 `{"error":"E202","mensaje":"control inválido"}`. Antes que el comando y la aridad | 2, 38, 40, 44 | confirmado |
| ERR-11 | E301 → 400 `{"error":"E301","mensaje":"comando desconocido "}`, con `sugerencia` si corresponde | 12, 85 | confirmado |
| ERR-12 | E302 → 400 `{"error":"E302","mensaje":"aridad inválida"}` | 20, 43 | confirmado |
| ERR-13 | E520 → 409 `{"error":"E520","mensaje":"operación destructiva: detiene el servicio; reenvía con confirmación"}`, en el lugar de E301/E302 | 292, 11068 | confirmado |
| ERR-14 | E303 → 400 `{"error":"E303","mensaje":"monto inválido"}`. Después del comando y la aridad; antes que E304 y E401 | 11328–11330, 11333–11335, 139, 141 | confirmado |
| ERR-15 | E304 → 400 `{"error":"E304","mensaje":"origen y destino iguales"}`. Antes que E401 y que E510 | 140, 306, 12677 | confirmado |
| ERR-16 | E401 → 404 `{"error":"E401","mensaje":"cuenta inexistente"}` y E402 → 404 `{"error":"E402","mensaje":"operación inexistente"}`. Antes que E510, E506 y E507 | 15, 106, 126, 307 | confirmado |
| ERR-17 | E510 → 423 `{"error":"E510","mensaje":"cuenta bloqueada","intentos":1}` (ver MEM-11). Va antes que E506 y E507: en v2, transferencias por encima del límite dan E510 si la cuenta está bloqueada (809, 899–901); en v1 se midió lo mismo con 409 (308, 309) | 12565, 12676, 12772, 809, 810, 899–901, 308, 309 | confirmado |
| ERR-18 | E506 → 422 `{"error":"E506","mensaje":"límite excedido"}`. Antes que E507 | 12640, 12854, 110 | confirmado |
| ERR-19 | E507 → 422 `{"error":"E507","mensaje":"saldo insuficiente"}` | 16, 246, 12557 | confirmado |
| ERR-20 | Orden completo: E404 → E001 → E599 → E101 → E100 → E102 → E103 → E104 → E201 → E202 → E301/E302/E520 → E303 → E304 → E401/E402 → E510 → E506 → E507 | 57, 10985, 296–298, 10984, 11200, 11201, 11320, 11324, 38–41, 11328–11330, 139–141, 307, 809, 899, 110 | confirmado |
| ERR-21 | Un caso que no medimos responde con el error que le toca según ese orden | — | supuesto |

## 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CAM-01 | **Cómo lo detectamos.** Un canario repite cada 20 minutos la misma secuencia de 59 pasos (los 20 ejemplos y un caso por cada error y comando) y compara cada respuesta, con tipos estrictos, contra la última corrida aceptada como base | 12355–12413 (base de v1), 12631–12689 | confirmado |
| CAM-02 | **Desde cuándo.** La última corrida igual a la base de la mañana terminó a las 15:35:11 UTC−5 (20:35:11 UTC); la primera respuesta distinta es de las 15:57:17 (20:57:17 UTC). El cambio ocurrió en ese intervalo. Dos corridas posteriores, a las 16:01 y 16:05, son idénticas entre sí | 12495–12553, 12565, 12631–12689, 12691–12749 | confirmado |
| CAM-03 | **Saldo.** Antes: un número entero (`"saldo":40000`). Ahora: un string con el entero dividido por 100 y dos decimales (`"saldo":"400.00"`). Se confirmó con saldos internos de 0, 100, 1.000, 991 y −1.000 | antes 8, 19; ahora 12638, 12649, 12780, 12787, 12789 | confirmado |
| CAM-04 | **Cuenta bloqueada.** Antes: 409 `{"error":"E510","mensaje":"cuenta bloqueada"}`. Ahora: 423 con `"intentos"`. Se confirmó bloqueando una cuenta e insistiendo: 1, 2, 3, y vuelve a 1 tras el depósito que desbloquea | antes 249, 308; ahora 12565, 12676, 12772–12774, 12779 | confirmado |
| CAM-05 | **Límite por transferencia** entre titulares distintos. Antes: 100.000 (100.000 pasaba). Ahora: 50.000. Los 100.000 del ejemplo 10 de `ejemplos.jsonl` pasaron a dar E506, y por eso las operaciones siguientes del canario cambian de número. El corte se encontró barriendo montos: 50.000 pasa; 50.001, 75.000, 90.000, 99.000, 99.999 y 100.000 no | antes 10, 109; ahora 12640, 12754–12764, 12762, 12764, 12854, 12856 | confirmado |
| CAM-06 | **Confirmación con el otro token.** Las 35 secuencias del token 1 se repitieron sobre v2: 45 pasos responden distinto que en v1 y los 45 los explican estos tres cambios; ninguno queda sin explicar | 513–1011 | confirmado |
| CAM-07 | **Lo que no cambió.** El resto de los 59 pasos del canario, la regla del bloqueo, el titular, ANULA y HALT responden igual en v2 | 12554–12629, 12631–12689 | confirmado |
| CAM-08 | El canario siguió corriendo contra la base de v2 hasta el cierre, para ver un segundo cambio o una reversión | 12691–12749 | probable |

## 7. Riesgos

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| RIE-01 | ANULA no revisa saldo y deja cuentas en negativo. Lo cerraríamos rechazando la anulación con un error propio | 12789; en v1: 122, 231 | confirmado |
| RIE-02 | El control es un dígito de verificación que cualquiera calcula: detecta errores de tipeo, pero no autentica. Lo cerraríamos firmando el mensaje con HMAC y un secreto por cliente | 1–20, 11782 | confirmado |
| RIE-03 | La ruta se evalúa antes que el token: sin credenciales se puede saber qué rutas existen (404 frente a 401). Lo cerraríamos autenticando primero | 57, 50, 12651, 12652 | confirmado |
| RIE-04 | `/health` pide token, así que un balanceador no puede chequearlo. Lo dejaríamos público y sin datos | 53, 11208 | confirmado |
| RIE-05 | HALT detiene el servicio, cualquier cliente con token llega a él, la sugerencia de E301 revela su nombre y la confirmación es un `1`. Lo sacaríamos de la API pública y no sugeriríamos comandos internos | 171, 292, 11134, 238, 239, 393–398 | confirmado |
| RIE-06 | Tres reintentos rechazados bloquean la cuenta (un cliente que reintenta en paralelo se bloquea solo) y un depósito de cualquier monto la libera, así que el bloqueo no protege. Lo cerraríamos contando rechazos en una ventana de tiempo y desbloqueando por acción de un operador | 200, 466, 467 | confirmado |
| RIE-07 | El límite de transferencia no aplica entre cuentas del mismo titular, y el titular es un nombre libre: abrir dos cuentas con el mismo nombre evita el límite | 11782, 12604 | confirmado |
| RIE-08 | El servicio cambió formato, status y límite sin aviso ni versión (saldo como string, E510 de 409 a 423): un cliente que leía el saldo como número se rompe. Lo cerraríamos versionando la API | 12638, 12565 | confirmado |
| RIE-09 | Respuestas inconsistentes de las que dependen los clientes: `cuentaId` frente a `cuenta_id`, `recieved` | 3, 5, 6, 12851, 12853, 12780 | confirmado |
