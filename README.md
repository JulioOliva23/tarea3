# mi6-cli

Registro local y cifrado de misiones para agentes de campo del MI6.

`mi6` permite a un agente, desde la terminal y sin red:

1. **Registrar** un informe de misión con su nivel de amenaza. El informe queda cifrado desde el primer momento.
2. **Listar** sus misiones activas junto con su **riesgo global**.
3. **Archivar** una misión concluida para que deje de contar como activa.

El proyecto sigue un desarrollo guiado por especificación. Estos documentos mandan sobre el código:

| Documento | Contenido |
|---|---|
| [`docs/constitution.md`](docs/constitution.md) | Los seis principios innegociables |
| [`specs/001-mi6-mvp/spec.md`](specs/001-mi6-mvp/spec.md) | Qué hace el MVP (requisitos RF y RNF, casos límite) |
| [`specs/001-mi6-mvp/plan.md`](specs/001-mi6-mvp/plan.md) | Cómo está construido (arquitectura, formatos, decisiones) |
| [`specs/001-mi6-mvp/tasks.md`](specs/001-mi6-mvp/tasks.md) | Las 48 tareas de implementación y su cobertura |
| [`specs/001-mi6-mvp/verification.md`](specs/001-mi6-mvp/verification.md) | Evidencia de que se cumplen los criterios de finalización |

---

## Arquitectura

```text
mi6/
├── __main__.py        python -m mi6  →  mi6.cli.main.main()
├── cli/               INTERFAZ: lee argumentos, llama al núcleo, da formato
│   ├── main.py        argparse en español, despacho, excepciones → códigos de salida
│   ├── prompts.py     /dev/tty, contraseña oculta (getpass), lectura del informe
│   ├── render.py      tabla de misiones, saneado de caracteres de control
│   └── messages.py    TODOS los textos que lee el agente (español)
└── core/              NÚCLEO: reglas y datos, sin terminal
    ├── validation.py  formato de código, nombre clave, amenaza, informe, contraseña
    ├── crypto.py      PBKDF2-HMAC-SHA256 + Fernet, verificador de contraseña
    ├── risk.py        suma y clasificación del riesgo (función pura)
    ├── schema.py      validación estricta del JSON leído de disco
    ├── storage.py     ruta, permisos, enlaces simbólicos, flock, escritura atómica
    ├── operations.py  casos de uso: create, list, archive
    ├── models.py      dataclasses inmutables y enums
    └── errors.py      excepciones de dominio con datos, sin texto para el agente
```

**Aislamiento estricto del núcleo (principio 3):**

- `mi6/core/` no importa `argparse` ni `sys`, no usa `print()` ni `input()` y nunca importa nada de `mi6/cli/`.
- El núcleo comunica los fallos con **excepciones que llevan datos** (`field`, `rule`, `path`, `reason`…), nunca con frases. `mi6/cli/main.py` traduce cada excepción a un texto de `messages.py` y a un código de salida.
- El núcleo recibe siempre la carpeta de datos (`data_dir`) y la hora (`now`) como parámetros. Así, los tests trabajan en carpetas temporales y con una hora fija.
- La suite lo comprueba automáticamente (`tests/test_cli.py`, `LayerBoundaryTest`).

**Flujo de `create`:**

1. Se validan el código, el nombre clave y la amenaza, y se buscan duplicados **sin contraseña**.
2. Se comprueba que hay terminal y se lee el informe.
3. Se pide la contraseña.
4. Con el bloqueo exclusivo tomado, **se vuelve a validar todo**, se cifra y se escribe de forma atómica.

---

## Dependencias

Principio 1 de la constitución: Python 3.11 o posterior y la librería estándar. La única dependencia externa permitida es `cryptography`.

| Necesidad | Solución | Origen | Por qué |
|---|---|---|---|
| Cifrado autenticado del informe | `cryptography.fernet.Fernet` | **`cryptography`** (única dependencia) | La librería estándar no trae ningún cifrado simétrico. Fernet ya incluye AES, HMAC, vector de inicialización y versión del formato, y detecta una contraseña incorrecta o un token manipulado sin que haya que montarlo a mano (plan, D1). |
| Derivar la clave desde la contraseña | `hashlib.pbkdf2_hmac` (SHA-256, 600.000 iteraciones) | estándar | Da el mismo resultado que el PBKDF2 de `cryptography` sin añadir nada. Argon2 exigiría otra dependencia y `scrypt` depende de la versión de OpenSSL del sistema (D5). |
| Sal y aleatoriedad | `secrets` | estándar | Generador criptográfico del sistema operativo. |
| Argumentos y ayuda en español | `argparse` (con ayuda propia) | estándar | `click` y `typer` serían dependencias externas (D6). |
| Contraseña oculta | `getpass` + `/dev/tty` | estándar | No se muestra en pantalla y no compite con el informe, que llega por la entrada estándar (D7). |
| Persistencia | `json` + `tempfile` + `os.replace` + `os.fsync` | estándar | El principio 5 exige JSON. La escritura es atómica (D3). |
| Concurrencia | `fcntl.flock` (no bloqueante) | estándar | El sistema libera el bloqueo aunque el proceso muera (D4). |
| Normalización de texto | `unicodedata` (NFC) | estándar | La misma contraseña o el mismo informe da el mismo resultado desde cualquier teclado. |
| Tests | `unittest`, `unittest.mock`, `pty`, `subprocess` | estándar | Principio 4: sin pytest. |

`cryptography` arrastra a su vez `cffi` y `pycparser`. No son dependencias del proyecto.

---

## Instalación

Requisitos: **macOS o Linux**, **Python 3.11 o posterior**. Windows queda fuera de alcance (`fcntl`, `/dev/tty`).

```bash
git clone <url-del-repositorio> mi6-cli
cd mi6-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
mi6 --help
```

El comando `mi6` queda disponible dentro del entorno virtual. También funciona `python -m mi6`.

---

## Uso

```text
mi6 create  -a CÓDIGO -n NOMBRE -t NIVEL   < informe.txt
mi6 list    -a CÓDIGO
mi6 archive -a CÓDIGO -n NOMBRE
mi6 --help
```

| Opción | Forma larga | Valores |
|---|---|---|
| `-a` | `--agent` | Código de agente `001` a `009` |
| `-n` | `--code-name` (alias `--name`) | 1 a 30 caracteres `A-Z a-z 0-9 -`; se guarda en mayúsculas |
| `-t` | `--threat` | Un dígito del `1` al `5` (solo en `create`) |
| `-h` | `--help` | Muestra la ayuda en español |

### Registrar una misión

```bash
mi6 create -a 007 -n SKYFALL -t 4 < informe.txt
```

```text
Primera misión del agente 007. Establezca su contraseña de campo (mínimo 8 caracteres):
Repítala para confirmar:
Expediente SKYFALL registrado, amenaza nivel 4. El informe ha sido cifrado, agente 007.
```

- **El informe:** nunca va como argumento. Llega por la entrada estándar o se redacta en la terminal; si se redacta, se termina con **Ctrl+D** en una línea vacía. Admite de 1 a 500 caracteres, saltos de línea, tildes, eñes y emojis.
- **La contraseña:**
  - La primera misión de un código **establece** la contraseña: se pide dos veces y debe tener al menos 8 caracteres.
  - Las siguientes misiones solo la piden una vez.
  - Se lee siempre desde la terminal y **nunca se muestra**.

> **Aviso de Q-Branch:** no use `echo "texto" | mi6 create …`. El informe quedaría guardado en el historial del shell. Redirija desde un archivo (`< informe.txt`), y bórrelo después si procede, o redáctelo en la terminal.

### Listar las misiones activas

```bash
mi6 list -a 007
```

```text
MISIONES ACTIVAS · AGENTE 007
NOMBRE CLAVE                    AMENAZA  REGISTRO
SKYFALL                         4        2026-10-20 09:15
GOLDENEYE                       3        2026-10-26 14:32

RIESGO GLOBAL: 7 · MEDIO
```

- **Sin contraseña:** `list` no la pide y nunca muestra el texto de los informes.
- **Riesgo global:** es la suma de las amenazas de las misiones activas. Se clasifica como **BAJO** (0–5), **MEDIO** (6–10) o **CRÍTICO** (11 o más).
- **Fechas:** se muestran en hora local.
- **Sin datos:** si todavía no hay datos, muestra `RIESGO GLOBAL: 0 · BAJO` y no crea nada en disco.

### Archivar una misión

```bash
mi6 archive -a 007 -n SKYFALL
```

```text
Va a archivar SKYFALL (amenaza 4). Introduzca su contraseña para confirmar.
Contraseña de campo:
Misión SKYFALL archivada. Expediente sellado.
```

- **Efecto:** la misión deja de contar en el listado y en el riesgo. Su informe sigue cifrado e intacto.
- **Nombre clave:** no se puede reutilizar para otra misión del mismo agente.
- **Fuera de alcance del MVP:** no se pueden listar, descifrar, editar ni borrar las misiones archivadas.

---

## Códigos de salida

| Código | Significado | Ejemplos |
|---|---|---|
| `0` | Éxito, o ayuda pedida con `--help` | Misión registrada, listado mostrado |
| `1` | Rechazo por validación o por una regla de negocio | Código `000`, amenaza `6`, contraseña incorrecta, nombre clave duplicado, misión no encontrada |
| `2` | Uso incorrecto de la CLI, o falta de terminal interactiva | Orden desconocida, faltan o sobran argumentos, `--report`, ejecución sin terminal |
| `3` | Fallo de datos, de permisos o de entorno | Datos corruptos, permisos abiertos, enlace simbólico, operación en curso, ejecución como root, disco lleno |
| `130` | Cancelación por el agente | Ctrl+C en cualquier momento, o Ctrl+D al pedir la contraseña |

Ningún rechazo ni fallo modifica los datos. Los mensajes de error explican la causa y nunca muestran trazas internas.

---

## Seguridad y datos locales

Todo se guarda en `~/.mi6/`. No hay red, sincronización ni exportación.

| Ruta | Permisos | Contenido |
|---|---|---|
| `~/.mi6/` | `0700` | Carpeta de datos |
| `~/.mi6/missions.json` | `0600` | Expediente de todos los agentes. Los informes van **cifrados**. |
| `~/.mi6/missions.lock` | `0600` | Archivo vacío para el bloqueo `flock` |
| `~/.mi6/.missions.json.tmp-*` | `0600` | Temporal de la escritura atómica. Solo existe durante una escritura. |

**Política POSIX.** Cada operación comprueba, antes de leer o escribir, que:

- la carpeta y los archivos pertenecen al usuario actual;
- no dan **ningún** permiso al grupo ni a otros usuarios (`modo & 0o077 == 0`);
- ninguno es un enlace simbólico (además, todo se abre con `O_NOFOLLOW`);
- `mi6` no se ejecuta como **root** y existe un directorio personal.

Si algo falla, la operación se cancela con código 3 e indica **exactamente** qué hacer, por ejemplo `chmod 600 /home/agente/.mi6/missions.json`. `mi6` **nunca corrige los permisos por su cuenta**.

**Cifrado.** Cada agente tiene una sal aleatoria de 16 bytes:

- La contraseña, normalizada a NFC, pasa por **PBKDF2-HMAC-SHA256 con 600.000 iteraciones** (la cifra que recomienda OWASP) y produce una clave Fernet.
- `key_check` es un valor conocido cifrado con esa clave. Permite detectar una contraseña incorrecta sin guardar la contraseña ni la clave.
- Fernet es un cifrado autenticado: cualquier byte manipulado en un token se detecta.

**Integridad.** Toda escritura sigue estos pasos: temporal `0600` en la misma carpeta → `fsync` → `os.replace` → `fsync` de la carpeta.

- Un error, un Ctrl+C o un corte de luz nunca deja el expediente a medias.
- Si la primera misión no llega a escribirse, `~/.mi6` se elimina de nuevo.

**Concurrencia.** `create` y `archive` toman un bloqueo exclusivo y `list` uno compartido, siempre sin esperar. Si otra terminal está escribiendo, el comando termina al momento con *«Operación en curso»*.

### Riesgos aceptados (spec, sección 5.1)

- **Datos en claro:** el código, el nombre clave, la amenaza, la fecha y el estado no se cifran, para poder listar y detectar duplicados sin contraseña. Cualquiera con acceso a su usuario del sistema puede leerlos.
- **Contraseña perdida = informes perdidos:** no existe ninguna forma de recuperarlos.
- **El código 00 es una etiqueta, no una identidad:** cualquiera con acceso a su usuario puede *listar* las misiones de cualquier código, pero no registrar ni archivar sin la contraseña.
- **NFS no soportado:** `flock` no es fiable en directorios personales en NFS.

### Procedimiento de Q-Branch ante datos dañados o incompletos

`mi6` termina con código 3 y *«Expediente dañado o irreconocible (…). No se ha tocado nada»* en estos casos:

- `missions.json` no se puede interpretar, tiene un formato o una versión desconocidos, o contiene algún registro inválido o duplicado;
- falta `missions.json` o `missions.lock`;
- queda algún temporal `.missions.json.tmp-*`.

Los pasos a seguir son:

1. **No borre nada.** Copie la carpeta tal cual: `cp -a ~/.mi6 ~/mi6-respaldo-$(date +%Y%m%d)`.
2. Compruebe que ningún otro `mi6` se está ejecutando (`pgrep -fl mi6`).
3. **Temporal huérfano** (`.missions.json.tmp-*`) con un `missions.json` válido: es un resto de una escritura interrumpida. El expediente bueno es `missions.json`, así que se puede borrar el temporal.
4. **Carpeta sin `missions.json`** y sin temporales: si nunca llegó a registrarse ninguna misión, se puede borrar `~/.mi6` entera.
5. **`missions.json` dañado:** valide el JSON (`python -m json.tool ~/.mi6/missions.json`) y compárelo con el formato de la sección 2.2 del plan. Los informes cifrados no se pueden reconstruir sin la contraseña de cada agente.

---

## Pruebas

```bash
source .venv/bin/activate
python -m unittest discover -s tests -t .
```

Los tests solo usan `unittest`. Nunca tocan el `~/.mi6` real: cada test trabaja en un directorio temporal con `HOME` aislado, y `storage.resolve_data_dir` falla si alguien lo llama. No usan la red.

| Archivo | Qué cubre |
|---|---|
| `test_validation.py`, `test_risk.py`, `test_models.py`, `test_errors.py` | Reglas puras, umbrales del riesgo, modelos inmutables, jerarquía de excepciones |
| `test_crypto.py` | Derivación, verificador, manipulación de cada byte y **prueba obligatoria de descifrado** |
| `test_schema.py`, `test_storage.py` | JSON corrupto, permisos, enlaces simbólicos, flock real, escritura atómica |
| `test_operations.py` | Casos de uso completos, duplicados, fallos sin cambios en disco |
| `test_cli.py` | Los cinco códigos de salida, mensajes, ayuda, saneado y salida no UTF-8 |
| `test_terminal.py` | `python -m mi6` en un **pseudo-terminal real**: contraseña sin eco, Ctrl+C real y ejecución sin terminal |
| `test_performance.py` | RNF-6 con 1.000 misiones: `list` en el núcleo y como proceso |

Los tests de permisos y de terminal se saltan automáticamente si se ejecutan como root, porque root ignora los permisos y `mi6` se niega a ejecutarse como root.

### Rendimiento (RNF-6)

Medición del 2026-10-26 sobre un expediente con **1.000 misiones**. `create` y `archive` usan el KDF de producción (600.000 iteraciones). Son medianas.

| Equipo | `list` (núcleo) | `python -m mi6 list` (proceso completo) | `create` | `archive` | Límite RNF-6 |
|---|---|---|---|---|---|
| MacBook, Apple M2 Pro, macOS 27.0, Python 3.14.6 | 3,8 ms | 65,6 ms | 61,1 ms | 61,1 ms | `list` < 1 s; `create`/`archive` < 2 s |
| Linux Debian 13 aarch64 (Docker, mismo equipo), Python 3.11.17 | 5,1 ms | 137,1 ms | 84,5 ms | 82,7 ms | ídem |

- **Qué se mide en `create` y `archive`:** el tiempo del núcleo (`operations`) con el expediente lleno, sin contar el tiempo que tarda el agente en teclear.
- **El KDF en este equipo:** 600.000 iteraciones de PBKDF2 tardan unos 55–72 ms, menos que los 0,3–0,5 s que estimaba el plan. La cifra de iteraciones sigue siendo la recomendada por OWASP.
- **Cómo repetir la medición:** la de `list` se hace sola en cada ejecución de la suite (`tests/test_performance.py`). Para medir `create` a mano:

```bash
time (mi6 create -a 007 -n PRUEBA -t 1 < informe.txt)   # incluye teclear la contraseña
```
