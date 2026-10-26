# Plan técnico 001: MVP operativo de mi6-cli

**Estado:** aprobado · **Spec:** `specs/001-mi6-mvp/spec.md` (aprobada) · **Constitución:** `docs/constitution.md` · **Fecha:** 2026-10-26

Este plan describe **cómo** se construye lo que pide la spec. No contiene código ejecutable: solo estructura, contratos, formatos y pseudocódigo. Cada sección indica qué requisitos cubre.

---

## 1. Estructura de carpetas y archivos

**Cubre:** principio 3 de la constitución, RNF-7, y reparte RF-1 a RF-7 entre los módulos.

```text
mi6-cli/
├── pyproject.toml            # Python >=3.11, única dependencia: cryptography; script "mi6"
├── README.md                 # Instalación y uso para el agente (en español)
├── docs/
│   └── constitution.md
├── specs/
│   └── 001-mi6-mvp/
│       ├── spec.md
│       └── plan.md
├── mi6/
│   ├── __init__.py
│   ├── __main__.py           # Permite "python -m mi6"; solo delega en mi6.cli.main
│   ├── core/                 # Lógica operativa: sin argparse, sys, print() ni input()
│   │   ├── __init__.py
│   │   ├── errors.py         # Jerarquía de excepciones de dominio
│   │   ├── models.py         # Dataclasses y enums: Mission, AgentRecord, RiskReport...
│   │   ├── validation.py     # Reglas de formato (código, amenaza, nombre clave, informe, contraseña)
│   │   ├── crypto.py         # Derivación de clave, verificador y cifrado Fernet
│   │   ├── risk.py           # Cálculo del riesgo global
│   │   ├── schema.py         # Validación estructural del JSON cargado (datos corruptos)
│   │   ├── storage.py        # Ruta de datos, permisos, enlaces simbólicos, bloqueo, lectura y escritura atómica
│   │   └── operations.py     # Casos de uso: preflight_create, create_mission, list_active_missions,
│   │                         #   get_active_mission, archive_mission, agent_exists
│   └── cli/                  # Interfaz de terminal: lee, llama al núcleo y da formato
│       ├── __init__.py
│       ├── main.py           # argparse, despacho de comandos, mapa de excepciones a códigos de salida
│       ├── prompts.py        # Terminal interactiva, contraseña (getpass), lectura del informe
│       ├── render.py         # Tabla de misiones, riesgo, neutralización de caracteres de control
│       └── messages.py       # TODOS los textos en español que ve el agente
└── tests/
    ├── __init__.py
    ├── helpers.py            # Clase base con directorio temporal y protección de ~/.mi6 real
    ├── core/
    │   ├── test_errors.py
    │   ├── test_models.py
    │   ├── test_validation.py
    │   ├── test_crypto.py
    │   ├── test_risk.py
    │   ├── test_schema.py
    │   ├── test_storage.py
    │   ├── test_operations.py
    │   ├── test_acceptance.py    # Test de descifrado (criterio de finalización)
    │   └── test_performance.py   # RNF-6 con 1.000 misiones
    └── cli/
        ├── test_messages.py
        ├── test_main.py
        ├── test_prompts.py
        ├── test_render.py
        └── test_edge_cases.py    # Casos límite de la spec, de principio a fin a través de main()
```

### Responsabilidades y fronteras

| Módulo | Responsabilidad | Requisitos | Puede importar |
|---|---|---|---|
| `core/validation.py` | Reglas puras de formato. No hace E/S. | RF-1.1, RF-2.3, RF-3.5, RF-3.7, RF-3.8, RF-3.9 | `re`, `unicodedata` |
| `core/crypto.py` | PBKDF2 y Fernet; verificador de contraseña | RF-2.5, RF-2.6, RF-3.3, RNF-1 | `hashlib`, `base64`, `secrets`, `unicodedata`, `cryptography.fernet` |
| `core/risk.py` | Suma y clasificación del riesgo | RF-4.3, RF-4.4, RF-5.3 | (nada externo) |
| `core/schema.py` | Valida el JSON cargado | RF-6.4 | `datetime`, `base64` |
| `core/storage.py` | Ruta, permisos, enlaces simbólicos, bloqueo, lectura y escritura atómica | RF-6.1 a RF-6.9, RF-4.6, RNF-2 | `os`, `stat`, `fcntl`, `json`, `tempfile`, `pathlib` |
| `core/operations.py` | Orquesta los casos de uso dentro del bloqueo; `_load_document` encadena las comprobaciones de `storage` con `schema.parse_document` | RF-2, RF-3, RF-4, RF-5 | los módulos de `core/`, `datetime` |
| `cli/prompts.py` | Contraseña oculta, comprobar `/dev/tty`, leer el informe | RF-2.1, RF-2.7, RF-3.2 | `getpass`, `os`, `sys` |
| `cli/render.py` | Formato de pantalla y saneado de caracteres | RF-4.2, RF-4.8, RF-7.6 | `unicodedata`, `datetime` |
| `cli/messages.py` | Constantes de texto en español | RNF-4, RF-7.5 | (nada) |
| `cli/main.py` | Argumentos, flujo, códigos de salida, Ctrl+C | RF-7.1 a RF-7.4 | `argparse`, `sys`, `mi6.core`, `mi6.cli.*` |

**Reglas de frontera:**
- `core/` nunca importa nada de `cli/`.
- `core/` comunica los fallos lanzando **excepciones con datos** (campo, regla, valor actual), nunca con texto para el agente. `cli/` traduce cada excepción a un mensaje de `messages.py` y a un código de salida.
- `core/` recibe siempre el directorio de datos (`data_dir`) como parámetro, para que los tests puedan usar uno temporal. Solo `cli/` llama a `storage.resolve_data_dir()` para obtener `~/.mi6`.
- `core/` recibe la hora actual como parámetro opcional (`now`), para que los tests sean deterministas.

### Excepciones de dominio (`core/errors.py`)

| Excepción | Cuándo | Datos que lleva | Código de salida |
|---|---|---|---|
| `Mi6Error` | Base de todas | — | — |
| `ValidationError` | Formato inválido | `field`, `rule` | 1 |
| `InvalidAgentCodeError(ValidationError)` | RF-1.2 | — | 1 |
| `PasswordPolicyError(ValidationError)` | RF-2.4 | `rule` (`too_short` o `mismatch`) | 1 |
| `AuthenticationError` | Contraseña incorrecta (RF-2.6) | — | 1 |
| `DuplicateMissionError` | RF-3.10 | `code_name`, `status` | 1 |
| `MissionNotFoundError` | RF-5.4 | `code_name` | 1 |
| `StorageError` | Base de los fallos de datos | `path` | 3 |
| `DataAccessError(StorageError)` | E/S fallida (RF-6.1) | `path`, `os_error_name` | 3 |
| `InsecurePermissionsError(StorageError)` | RF-6.2 | `path`, `current_mode`, `expected_mode` | 3 |
| `SymlinkError(StorageError)` | RF-6.3 | `path` | 3 |
| `CorruptDataError(StorageError)` | RF-6.5, RF-6.7 | `path`, `reason` | 3 |
| `OperationInProgressError(StorageError)` | RF-6.8 | — | 3 |
| `UnsafeEnvironmentError(StorageError)` | RF-6.9 | `reason` (`root` o `no_home`) | 3 |

En `cli/` hay dos excepciones propias de la interfaz: `UsageError` (código 2, RF-7.1) y `NoTerminalError` (código 2, RF-2.7).

---

## 2. Modelo de datos JSON

**Cubre:** RF-2.2, RF-2.3, RF-2.5, RF-3.3, RF-3.4, RF-3.10, RF-3.11, RF-4.2, RF-5.2, RF-6.2, RF-6.4, RF-6.6, RF-6.7, RNF-1, RNF-2, sección 5.1 de la spec.

### 2.1 Contenido de `~/.mi6/`

| Ruta | Permisos | Propósito |
|---|---|---|
| `~/.mi6/` | `0700` | Carpeta de datos. Su existencia marca que ya no es el primer uso. |
| `~/.mi6/missions.json` | `0600` | Expediente con todas las misiones de todos los agentes. |
| `~/.mi6/missions.lock` | `0600` | Archivo vacío que solo sirve para el bloqueo con `fcntl.flock`. |
| `~/.mi6/.missions.json.tmp-XXXX` | `0600` | Archivo temporal de la escritura atómica. Solo existe durante una escritura. |

### 2.2 Ejemplo de expediente

Los valores de `salt`, `key_check` y `report_token` son **ilustrativos y están recortados**. Un token Fernet real mide más de 100 caracteres.

```json
{
  "schema_version": 1,
  "agents": {
    "007": {
      "kdf": {
        "algorithm": "pbkdf2_hmac_sha256",
        "iterations": 600000,
        "salt": "q3Jx9mW2bT8vYp1LzK0aNg=="
      },
      "key_check": "gAAAAABnHf3k9vQ2...Xh8=",
      "missions": [
        {
          "code_name": "SKYFALL",
          "threat_level": 4,
          "status": "active",
          "created_at": "2026-10-20T09:15:42+01:00",
          "report_token": "gAAAAABnFL1e2Rk7...pQ0="
        },
        {
          "code_name": "SPECTRE",
          "threat_level": 5,
          "status": "archived",
          "created_at": "2026-10-22T23:04:10+01:00",
          "report_token": "gAAAAABnGCk8Wf3Z...aM4="
        },
        {
          "code_name": "GOLDENEYE",
          "threat_level": 3,
          "status": "active",
          "created_at": "2026-10-26T14:32:07+00:00",
          "report_token": "gAAAAABnHf5j0LcY...tE2="
        }
      ]
    },
    "006": {
      "kdf": {
        "algorithm": "pbkdf2_hmac_sha256",
        "iterations": 600000,
        "salt": "Zt4Hc1oPq8sWv0mN2xRyJA=="
      },
      "key_check": "gAAAAABnHa02Mz1T...Lw8=",
      "missions": [
        {
          "code_name": "SKYFALL",
          "threat_level": 2,
          "status": "active",
          "created_at": "2026-10-25T18:47:55+01:00",
          "report_token": "gAAAAABnG9xQ7bNe...Vu1="
        }
      ]
    }
  }
}
```

Con estos datos, el riesgo de 007 es 4 + 3 = **7 (MEDIO)**, porque SPECTRE está archivada y no cuenta. 006 puede tener su propio SKYFALL (RF-3.11). Las dos fechas de 007 tienen desfases distintos por el cambio al horario de invierno del 25 de octubre (RF-3.4).

### 2.3 Tipos y reglas de cada campo

| Ruta JSON | Tipo | Regla de validación (`core/schema.py`, RF-6.4) |
|---|---|---|
| `schema_version` | int | Exactamente `1`. Cualquier otro valor se trata como versión desconocida, es decir, corrupto. |
| `agents` | object | Las claves cumplen `00[1-9]` (RF-1.1). |
| `agents.<code>.kdf.algorithm` | string | Exactamente `"pbkdf2_hmac_sha256"`. |
| `agents.<code>.kdf.iterations` | int | Mayor o igual que 1. |
| `agents.<code>.kdf.salt` | string | Base64 estándar que decodifica a exactamente 16 bytes. |
| `agents.<code>.key_check` | string | Formato de token Fernet (ver más abajo). |
| `agents.<code>.missions` | array | Orden = orden de registro (RF-4.2). Sin `code_name` repetido. |
| `missions[].code_name` | string | Cumple `[A-Z0-9-]{1,30}` (ya en mayúsculas). |
| `missions[].threat_level` | int | Del 1 al 5. **Atención:** en Python, `True` es un `int`, así que hay que rechazar `bool` de forma explícita. |
| `missions[].status` | string | `"active"` o `"archived"`. |
| `missions[].created_at` | string | ISO 8601 que `datetime.fromisoformat` acepta **y** con zona horaria (`tzinfo` no nulo). |
| `missions[].report_token` | string | Formato de token Fernet. |

- **Claves:** cualquier clave desconocida o que falte, en cualquier nivel, hace que el expediente se considere corrupto.
- **Formato de token Fernet sin descifrar:** Base64 URL-safe, primer byte `0x80` (la versión de Fernet) y al menos 73 bytes en total. Así se detecta un token dañado (caso límite de la sección 6 de la spec) sin conocer la contraseña.
- **Textos internos:** `status` y los niveles de riesgo se guardan en inglés (principio 6). `render.py` los traduce a `ACTIVA`, `ARCHIVADA`, `BAJO`, `MEDIO` y `CRÍTICO`.

### 2.4 Derivación de clave, sal y verificador

**Cubre:** RF-2.2, RF-2.3, RF-2.5, RF-2.6, RF-3.3, RNF-1.

1. **Normalizar:** la contraseña se normaliza a Unicode NFC y se codifica en UTF-8. Así, la misma contraseña escrita desde teclados distintos produce la misma clave.
2. **Sal:** al establecer la contraseña (primera misión del código, RF-2.3) se generan 16 bytes aleatorios con `secrets.token_bytes(16)`. Se guardan en Base64 en `kdf.salt`. Hay **una sal por agente**, no por misión (ver la decisión D2).
3. **Derivación:** `hashlib.pbkdf2_hmac("sha256", contraseña, sal, iterations, dklen=32)` produce 32 bytes, y su codificación en Base64 URL-safe es la clave Fernet. El número de iteraciones se guarda en `kdf.iterations` para poder subirlo en el futuro sin romper los expedientes existentes.
4. **Verificador:** `key_check` es el cifrado Fernet de la constante `b"mi6:key-check:v1"`. Para comprobar una contraseña (RF-2.5) se deriva la clave y se descifra `key_check`. Si falla con `InvalidToken` o el resultado no coincide, se lanza `AuthenticationError` (RF-2.6).
5. **Informe:** `report_token` es el cifrado Fernet del informe validado, codificado en UTF-8 (RF-3.3). Fernet usa un vector de inicialización aleatorio en cada cifrado, así que reutilizar la clave del agente para varias misiones es seguro.
6. **Lo que nunca se guarda:** ni la contraseña ni la clave derivada se guardan, se muestran o se registran (RF-2.2). La clave solo vive en memoria durante una operación.

### 2.5 Escritura atómica y primer uso

**Cubre:** RF-4.6, RF-6.1, RF-6.6, RF-6.7, RNF-2.

**Primer uso** significa que `~/.mi6/` no existe. Solo `create` puede crearlo, en este orden:

1. `mkdir` con permisos `0700` y un `chmod` explícito.
2. Crear `missions.lock` con permisos `0600`.
3. Tomar el bloqueo exclusivo.
4. Hacer la escritura atómica.

**Datos incompletos (RF-6.7):** si `~/.mi6/` existe pero falta `missions.lock` o `missions.json`, o queda algún `.missions.json.tmp-*`, se lanza `CorruptDataError(reason="incomplete")`. La comprobación se hace siempre **con el bloqueo tomado**, para no confundir una escritura en curso de otra ejecución con un resto.

**Escritura atómica**, siempre con el bloqueo exclusivo tomado:

1. Serializar con `json.dumps(..., ensure_ascii=False, indent=2)`.
2. Crear el temporal con `tempfile.mkstemp(dir=data_dir, prefix=".missions.json.tmp-")`, que ya crea el archivo con permisos `0600`.
3. Escribir, hacer `flush` y `os.fsync` del archivo.
4. `os.replace(temporal, missions.json)`, que es atómico dentro del mismo sistema de archivos.
5. Hacer `os.fsync` del descriptor de la carpeta, para que el cambio de nombre sobreviva a un corte de luz.
6. Si cualquier paso lanza una excepción, **incluida `KeyboardInterrupt`**, se borra el temporal y se relanza la excepción. Como el `missions.json` original no se ha tocado, se cumple RF-7.3.

### 2.6 Comprobaciones de seguridad del entorno

**Cubre:** RF-6.2, RF-6.3, RF-6.9.

Se ejecutan en este orden al empezar cada operación:

1. **Root:** si `os.geteuid() == 0` → `UnsafeEnvironmentError("root")`.
2. **Directorio personal:** si `Path.home()` falla o no devuelve una ruta absoluta → `UnsafeEnvironmentError("no_home")`.
3. **Enlaces simbólicos:** `os.lstat` sobre `~/.mi6`, `missions.json` y `missions.lock`. Si alguno es un enlace simbólico → `SymlinkError`. Además, los archivos se abren con `os.O_NOFOLLOW` para cerrar la ventana entre la comprobación y el uso.
4. **Permisos:** si `st_mode & 0o077 != 0` en la carpeta o en los archivos, o si su propietario no es `os.geteuid()` → `InsecurePermissionsError` con el modo actual y el esperado. El CLI construye con ellos el `chmod` exacto que hay que ejecutar.

**Alcance:** se comprueban `~/.mi6` y su contenido, no los directorios superiores al directorio personal. Tener el directorio personal en NFS no está soportado (ver D4).

---

## 3. Algoritmo del riesgo global

**Cubre:** RF-4.3, RF-4.4, RF-4.5, RF-5.3.

```text
CONSTANTES
    LOW_MAX    = 5      # 0..5   → LOW      ("BAJO")
    MEDIUM_MAX = 10     # 6..10  → MEDIUM   ("MEDIO")
                        # 11..   → CRITICAL ("CRÍTICO")

FUNCIÓN compute_risk(missions) → RiskReport
    # missions: lista de Mission de UN agente (activas y archivadas)
    total ← 0
    active ← lista vacía
    PARA CADA mission EN missions (en orden de registro):
        SI mission.status = ACTIVE:
            total ← total + mission.threat_level
            añadir mission a active
        # las archivadas se ignoran (RF-5.3)

    SI total ≤ LOW_MAX:
        level ← LOW
    SI NO, SI total ≤ MEDIUM_MAX:
        level ← MEDIUM
    SI NO:
        level ← CRITICAL

    DEVOLVER RiskReport(active_missions = active, total = total, level = level)
```

**Propiedades que deben verificar los tests (`test_risk.py`):**
- **Sin misiones activas:** una lista vacía o con solo archivadas da `total = 0` y `LOW` (RF-4.5).
- **Límites:** 5 da `LOW`, 6 da `MEDIUM`, 10 da `MEDIUM` y 11 da `CRITICAL`.
- **Orden:** el resultado conserva el orden de entrada (RF-4.2).
- **Función pura:** no hace E/S, no usa la hora y no muta la lista recibida.

---

## 4. Contrato de la CLI

**Cubre:** RF-1.2, RF-2.1, RF-2.3, RF-2.7, RF-3.1, RF-3.2, RF-4.1, RF-4.2, RF-4.8, RF-5.1, RF-5.2, RF-7.1 a RF-7.6, RNF-4.

### 4.1 Sinopsis

```text
mi6 create  --agent CODE --code-name NAME --threat LEVEL   < informe.txt
mi6 list    --agent CODE
mi6 archive --agent CODE --code-name NAME
mi6 --help | -h
mi6 <command> --help | -h
```

| Bandera | Corta | Comandos | Obligatoria | Validación (en `core`) |
|---|---|---|---|---|
| `--agent` | `-a` | todos | sí | RF-1.1 |
| `--code-name` | `-n` | `create`, `archive` | sí | RF-3.7 |
| `--threat` | `-t` | `create` | sí | RF-3.5 |
| `--help` | `-h` | todos | no | Muestra la ayuda en español y termina con 0 (RF-7.2) |

- **Sin `--report`:** **no existe** ninguna bandera para el informe (RF-3.2). Si alguien escribe `--report`, la CLI lo trata como un argumento desconocido y termina con código 2.
- **Ayuda en español:** `argparse` se crea con `add_help=False` y se registra un `-h/--help` propio, porque la ayuda por defecto está en inglés. El texto completo de la ayuda está en `messages.py`.
- **Errores de argumentos:** el método `error()` de `ArgumentParser` se sobrescribe para lanzar `UsageError` en lugar de imprimir en inglés y salir. `main` lo captura, muestra la ayuda en español y devuelve 2 (RF-7.1).
- **`main` para tests:** la firma es `main(argv=None, data_dir=None) -> int`. Devuelve el código de salida en lugar de llamar a `sys.exit`, que solo se llama en el punto de entrada. Así los tests pueden pasar un `data_dir` temporal.

### 4.2 Lectura del informe (`create`)

| Situación | Comportamiento |
|---|---|
| La entrada estándar **no** es una terminal (`mi6 create ... < informe.txt`) | Se lee toda la entrada estándar. |
| La entrada estándar **es** una terminal | Se muestra `REPORT_PROMPT` y se lee hasta Ctrl+D. |
| Bytes que no son UTF-8 válido | `ValidationError(field="report", rule="encoding")` y código 1. |

**Normalización antes de validar** (en `core/validation.py`, RF-3.8 y RF-3.9):
1. Convertir `\r\n` en `\n`.
2. Quitar los espacios del principio y del final con `str.strip()`, que también elimina los espacios Unicode.
3. Normalizar a NFC.
4. Comprobar la longitud: de 1 a 500 puntos de código. Un emoji compuesto cuenta varios.
5. Rechazar los caracteres de categoría Unicode `Cc` salvo `\n` y `\t`, los `Cf` salvo U+200D (el ZWJ de los emojis compuestos), y los `Cs`, `Co` y `Cn`. Así se rechazan las secuencias ANSI y los caracteres que invierten la dirección del texto.

**Para el README:** `echo "texto" | mi6 create ...` deja el informe en el historial del shell. La forma recomendada es redirigir desde un archivo o escribirlo de forma interactiva.

### 4.3 Contraseña

**Cubre:** RF-2.1, RF-2.3, RF-2.7.

1. **Comprobar la terminal:** antes de pedir nada, `prompts.require_terminal()` intenta abrir `/dev/tty` con `os.open(..., O_RDWR | O_NOCTTY)` y lo cierra. Si falla → `NoTerminalError` y código 2.
2. **Leer la contraseña:** `getpass.getpass()` lee de `/dev/tty`, así que funciona aunque la entrada estándar traiga el informe. La advertencia `getpass.GetPassWarning` se convierte en error, para que nunca se lea la contraseña con eco ni desde la entrada estándar.
3. **Primera misión de un código:** se pide dos veces, con `PASSWORD_NEW` y `PASSWORD_REPEAT`. La comparación y la longitud mínima las valida `core` (RF-2.3 y RF-2.4).

### 4.4 Flujo de cada comando

**`create`**
1. `operations.preflight_create(data_dir, agent, code_name, threat)`. Valida el código, el nombre clave y la amenaza, y comprueba si el nombre ya existe **con datos en claro**, sin pedir la contraseña. Así el agente no escribe el informe para luego recibir un "duplicado".
2. `prompts.require_terminal()` (RF-2.7).
3. Leer el informe (sección 4.2) y validarlo con `validation.normalize_report()`.
4. `operations.agent_exists(...)`: si el código es nuevo, pedir la contraseña dos veces; si no, una vez.
5. `operations.create_mission(...)`. Dentro del bloqueo **vuelve a validar todo**, porque los datos pueden haber cambiado desde el paso 1. Después deriva la clave, comprueba `key_check` o crea la sal y el verificador, cifra, añade la misión y escribe de forma atómica.
6. Mostrar `CREATE_OK` y devolver 0.

**`list`** (RF-4.1: no pide contraseña)
1. `operations.list_active_missions(data_dir, agent)` devuelve un `RiskReport`.
   - Si `~/.mi6` no existe, devuelve un informe vacío sin crear nada (RF-4.6).
   - Si existe, toma un bloqueo **compartido** no bloqueante sobre `missions.lock`, que **no se crea** si falta (RF-6.7).
2. `render.mission_table(...)` y `render.risk_line(...)`, o `LIST_EMPTY` si no hay misiones activas.

**`archive`**
1. `operations.get_active_mission(data_dir, agent, code_name)`, sin contraseña. Si no hay una misión activa con ese nombre → `MissionNotFoundError` (RF-5.4).
2. Mostrar `ARCHIVE_PREVIEW` con el nombre clave y la amenaza (RF-5.1).
3. `prompts.require_terminal()` y pedir la contraseña una vez.
4. `operations.archive_mission(...)`. Dentro del bloqueo exclusivo: recargar, comprobar que la misión sigue activa, verificar `key_check`, cambiar `status` a `"archived"` y escribir de forma atómica. Si falla cualquier paso, el archivo queda intacto (RF-5.5).
5. Mostrar `ARCHIVE_OK` y devolver 0.

**Común a todos (`main`)**
- **Codificación de salida (RF-7.6):** al arrancar se ejecuta `sys.stdout.reconfigure(errors="replace")`, y lo mismo para `sys.stderr`.
- **Dónde se escribe:** los resultados van a la salida estándar y los errores a la salida de error.
- **Ctrl+C (RF-7.3):** `KeyboardInterrupt`, en cualquier punto, se convierte en `ABORTED_BY_AGENT` y código 130.
- **Fallo inesperado:** cualquier otra excepción no prevista muestra `UNEXPECTED` y devuelve 3, sin mostrar la traza.

### 4.5 Salida de `list`

```text
MISIONES ACTIVAS · AGENTE 007
NOMBRE CLAVE                    AMENAZA  REGISTRO
SKYFALL                         4        2026-10-20 09:15
GOLDENEYE                       3        2026-10-26 14:32

RIESGO GLOBAL: 7 · MEDIO
```

- **Fechas:** se muestran en hora local con `datetime.fromisoformat(created_at).astimezone()` y el formato `%Y-%m-%d %H:%M` (RF-4.2). En el ejemplo, la zona local es Londres.
- **Saneado (RF-4.8):** antes de imprimir, todo dato que viene del expediente pasa por `render.sanitize()`, que sustituye por `?` los caracteres `Cc` y `Cf`.

### 4.6 Mensajes (`cli/messages.py`)

Los `{marcadores}` se rellenan con valores ya saneados.

| Constante | Texto | Código | Requisito |
|---|---|---|---|
| `CREATE_OK` | `Expediente {code_name} registrado, amenaza nivel {threat}. El informe ha sido cifrado, agente {agent}.` | 0 | RF-3.1 |
| `LIST_HEADER` | `MISIONES ACTIVAS · AGENTE {agent}` | 0 | RF-4.2 |
| `LIST_RISK` | `RIESGO GLOBAL: {total} · {level}` | 0 | RF-4.3, RF-4.4 |
| `LIST_EMPTY` | `Sin misiones activas, agente {agent}. Disfrute del martini.` + `LIST_RISK` con 0 · BAJO | 0 | RF-4.5 |
| `ARCHIVE_PREVIEW` | `Va a archivar {code_name} (amenaza {threat}). Introduzca su contraseña para confirmar.` | — | RF-5.1 |
| `ARCHIVE_OK` | `Misión {code_name} archivada. Expediente sellado.` | 0 | RF-5.2 |
| `REPORT_PROMPT` | `Redacte el informe (máx. 500 caracteres). Pulse Ctrl+D en una línea vacía para terminar.` | — | RF-3.2 |
| `PASSWORD_PROMPT` | `Contraseña de campo: ` | — | RF-2.1 |
| `PASSWORD_NEW` | `Primera misión del agente {agent}. Establezca su contraseña de campo (mínimo 8 caracteres): ` | — | RF-2.3 |
| `PASSWORD_REPEAT` | `Repítala para confirmar: ` | — | RF-2.3 |
| `ERR_AGENT_CODE` | `Acceso denegado. El código de agente debe ser 001–009.` | 1 | RF-1.2 |
| `ERR_THREAT` | `Nivel de amenaza no válido. Use un número del 1 al 5.` | 1 | RF-3.6 |
| `ERR_CODE_NAME` | `Nombre clave no válido: entre 1 y 30 caracteres, solo letras sin tilde, dígitos y guiones.` | 1 | RF-3.9 |
| `ERR_REPORT_EMPTY` | `El informe está vacío. Q no acepta expedientes en blanco.` | 1 | RF-3.9 |
| `ERR_REPORT_LENGTH` | `El informe supera los 500 caracteres ({length}). Sea más conciso, agente.` | 1 | RF-3.9 |
| `ERR_REPORT_CHARS` | `El informe contiene caracteres de control no permitidos.` | 1 | RF-3.9 |
| `ERR_REPORT_ENCODING` | `El informe no es texto UTF-8 válido.` | 1 | RF-3.9 |
| `ERR_PASSWORD_SHORT` | `La contraseña debe tener al menos 8 caracteres. Registro cancelado.` | 1 | RF-2.4 |
| `ERR_PASSWORD_MISMATCH` | `Las contraseñas no coinciden. Registro cancelado.` | 1 | RF-2.4 |
| `ERR_AUTH` | `Acceso denegado: contraseña incorrecta. No se ha modificado nada.` | 1 | RF-2.6 |
| `ERR_DUPLICATE` | `Ya existe una misión {code_name} ({status_es}) a su nombre.` | 1 | RF-3.10 |
| `ERR_NOT_FOUND` | `La misión {code_name} no está entre sus misiones activas.` | 1 | RF-5.4 |
| `ERR_USAGE` | `Orden no reconocida o incompleta.` + ayuda | 2 | RF-7.1 |
| `ERR_NO_TERMINAL` | `Se requiere una terminal interactiva para introducir la contraseña.` | 2 | RF-2.7 |
| `ERR_DATA_ACCESS` | `No se puede acceder al expediente local ({path}): {reason}.` | 3 | RF-6.1 |
| `ERR_PERMISSIONS` | `Permisos inseguros en {path} ({current}). Ejecute: chmod {expected} {path}` | 3 | RF-6.2 |
| `ERR_SYMLINK` | `{path} es un enlace simbólico. Operación abortada por seguridad.` | 3 | RF-6.3 |
| `ERR_CORRUPT` | `Expediente dañado o irreconocible ({path}). No se ha tocado nada. Contacte con Q-Branch.` | 3 | RF-6.5, RF-6.7 |
| `ERR_IN_PROGRESS` | `Operación en curso desde otra terminal. Inténtelo de nuevo en unos segundos.` | 3 | RF-6.8 |
| `ERR_ROOT` | `No ejecute mi6 como root. Operación abortada.` | 3 | RF-6.9 |
| `ERR_NO_HOME` | `No se encuentra el directorio personal del agente. Operación abortada.` | 3 | RF-6.9 |
| `UNEXPECTED` | `Fallo inesperado. Operación abortada. Informe a Q-Branch.` | 3 | — |
| `ABORTED_BY_AGENT` | `Operación abortada por el agente. Sin cambios.` | 130 | RF-7.3 |
| `HELP` | Texto completo de la ayuda con los tres comandos, las banderas y ejemplos | 0 | RF-7.2 |

### 4.7 Códigos de salida (RF-7.4)

| Código | Excepciones que lo producen |
|---|---|
| 0 | Ninguna (éxito o ayuda explícita) |
| 1 | `ValidationError` y sus subclases, `AuthenticationError`, `DuplicateMissionError`, `MissionNotFoundError` |
| 2 | `UsageError`, `NoTerminalError` |
| 3 | `StorageError` y sus subclases; cualquier excepción inesperada |
| 130 | `KeyboardInterrupt` |

---

## 5. Decisiones técnicas

**Cubre:** RNF-1, RNF-2, RNF-5, RNF-6, RF-6.8, y los principios 1 y 5 de la constitución.

### D1. Fernet con PBKDF2 frente a AES directo

- **Elegido:** Fernet (de `cryptography`) con una clave derivada por PBKDF2-HMAC-SHA256 de 600.000 iteraciones, que es la cifra recomendada por OWASP para SHA-256.
- **Descartado:** AES directo con las primitivas de bajo nivel de `cryptography` (por ejemplo, AES-GCM o AES-CBC con HMAC montados a mano).
- **Por qué:**
  - Fernet ya es **cifrado autenticado**: detecta una contraseña incorrecta o un token manipulado (RNF-1).
  - Gestiona solo el vector de inicialización, el relleno, el MAC y la versión del formato.
  - Con AES directo, un desarrollador junior tendría que gestionar los nonces, que nunca pueden repetirse, el relleno y la comparación del MAC en tiempo constante. Cualquier error ahí rompe la seguridad sin que ningún test lo note.
- **Coste aceptado:**
  - Fernet usa AES-128, suficiente para este modelo de amenaza.
  - El token incluye la hora de cifrado en claro, que ya está en `created_at`.
  - Fernet cifra el mensaje completo en memoria, lo que no importa con 500 caracteres.

### D2. Sal y verificador por agente frente a sal por misión

- **Elegido:** una sal y un `key_check` por agente.
- **Descartado:** una sal por misión.
- **Por qué:**
  - Con una sal por agente, cada operación deriva la clave **una sola vez**, unos 0,3 a 0,5 s, y cumple RNF-6 (menos de 2 s).
  - Con una sal por misión, verificar la contraseña obligaría a descifrar alguna misión.
  - El verificador permite rechazar una contraseña incorrecta (RF-2.6) de forma explícita y uniforme.
  - Fernet ya usa un vector de inicialización distinto en cada cifrado, así que compartir la clave no debilita el cifrado.

### D3. JSON con escritura atómica frente a SQLite

- **Elegido:** un único `missions.json`, escrito con un temporal más `os.replace` y `fsync` (sección 2.5).
- **Descartado:** SQLite (`sqlite3`, que también está en la librería estándar).
- **Por qué:**
  - El principio 5 de la constitución exige JSON.
  - Con menos de 1.000 misiones, reescribir el archivo entero es inmediato.
  - Q-Branch puede inspeccionar el JSON con cualquier editor.
  - SQLite crea archivos auxiliares (`-journal`, `-wal`) cuyos permisos y restos habría que vigilar aparte (RF-6.2 y RF-6.7).
  - Un junior entiende mejor un JSON validado que un esquema SQL con migraciones.
- **Coste aceptado:**
  - Hay que implementar a mano la atomicidad y la validación del esquema (`schema.py`).
  - El bloqueo no viene incluido (ver D4).

### D4. Bloqueo con `fcntl.flock` frente a alternativas

- **Elegido:** `fcntl.flock` sobre el archivo `missions.lock`, siempre en modo no bloqueante (`LOCK_NB`).
  - **Exclusivo** (`LOCK_EX`) para `create` y `archive`.
  - **Compartido** (`LOCK_SH`) para `list`.
  - Si no se puede tomar → `OperationInProgressError` al momento (RF-6.8).
- **Descartado:**
  1. **Archivo de bloqueo creado con `O_EXCL`:** si el proceso muere, el bloqueo queda huérfano y bloquea para siempre.
  2. **Bloquear `missions.json` directamente:** `os.replace` cambia el inodo, así que dos procesos podrían bloquear archivos distintos.
  3. **No bloquear:** dos `create` simultáneos perderían una misión.
- **Por qué:**
  - El núcleo del sistema operativo libera el bloqueo de `flock` cuando el proceso termina, aunque sea con un cierre forzado.
  - El archivo de bloqueo tiene un inodo estable.
  - `fcntl` solo existe en Unix, pero Windows está fuera de alcance (RNF-5).
- **Límites:**
  - `flock` no es fiable en NFS, así que un directorio personal en NFS no está soportado.
  - `list` no crea el archivo de bloqueo si no existe (RF-4.6).

### D5. PBKDF2 con `hashlib` frente a `cryptography`, scrypt o Argon2

- **Elegido:** `hashlib.pbkdf2_hmac`, de la librería estándar.
- **Por qué:** el principio 1 prefiere la librería estándar, y el resultado es idéntico al de la clase `PBKDF2HMAC` de `cryptography`.
- **Descartado:**
  - **Argon2:** exige una dependencia nueva, lo que viola el principio 1.
  - **scrypt (`hashlib.scrypt`):** es más resistente a GPU, pero su disponibilidad depende de la versión de OpenSSL de cada sistema.
- **Para el futuro:** como `kdf.algorithm` y `kdf.iterations` están en el JSON, el algoritmo puede cambiarse más adelante.

### D6. `argparse` con ayuda propia frente a `click` o `typer`

- **Elegido:** `argparse` con `add_help=False` y un `error()` sobrescrito.
- **Descartado:** `click` y `typer`, que son dependencias externas (principio 1).
- **Coste aceptado:** el texto de la ayuda se escribe a mano en `messages.py`, lo que también garantiza que esté entero en español (RNF-4).

### D7. Contraseña por `/dev/tty` frente a variable de entorno o entrada estándar

- **Elegido:** `getpass`, más una comprobación previa de `/dev/tty`.
- **Descartado:**
  - **Variable de entorno (`MI6_PASSWORD`):** es visible en `/proc/<pid>/environ` y en el historial del shell.
  - **Leerla de la entrada estándar:** choca con el informe, que ya usa la entrada estándar, y facilita guardarla en scripts.
- **Consecuencia aceptada:** no se puede automatizar `create` ni `archive` sin terminal (RF-2.7).

### D8. Validación duplicada: antes y dentro del bloqueo

- **Elegido:** `preflight_create` y `get_active_mission` validan sin bloqueo para dar una respuesta rápida al agente, y la operación final vuelve a validar todo con el bloqueo exclusivo tomado.
- **Descartado:** mantener el bloqueo durante los diálogos interactivos. Mientras el agente escribe el informe, cualquier otra terminal recibiría "operación en curso".

---

## 6. Estrategia de testing

**Cubre:** RNF-7, la sección 8 de la spec (criterios de finalización) y el principio 4 de la constitución.

### 6.1 Reglas generales

- **Ejecución:** `python -m unittest discover -s tests`, solo con `unittest`, sin pytest.
- **Clase base `tests/helpers.Mi6TestCase`:**
  - **Datos temporales:** en `setUp` crea un `tempfile.TemporaryDirectory()` y define `self.data_dir = <tmp>/.mi6`. En `tearDown` lo borra.
  - **Protección del directorio real:** parchea `mi6.core.storage.resolve_data_dir` para que **falle** si algún test intenta usar el `~/.mi6` real (principio 4).
  - **Hora fija:** ofrece `self.now`, una fecha fija con zona horaria, para que `created_at` sea predecible.
  - **Contraseñas rápidas:** todos los tests crean los agentes con `kdf_iterations=1_000`, un parámetro opcional de `create_mission` que en producción vale 600.000. Así la batería tarda segundos. Un test aparte comprueba que el valor por defecto es 600.000.
- **Tests de la CLI:**
  - Llaman a `main(argv, data_dir=self.data_dir)` y comprueban el **código devuelto**.
  - Capturan la salida estándar y la de error con `contextlib.redirect_stdout` y `redirect_stderr`, usando `io.StringIO`.
  - Comprueban que el texto contiene la constante de `messages.py` que corresponde, no una cadena copiada.
- **Sin red ni terminal real:** ningún test necesita una terminal real ni red.

### 6.2 Simulación de la entrada estándar y de la contraseña

| Qué se simula | Cómo |
|---|---|
| Informe por tubería | `mock.patch("sys.stdin", io.StringIO("Objetivo neutralizado en Estambul."))`. `StringIO.isatty()` devuelve `False`, así que se usa la lectura completa. |
| Informe interactivo | Un `io.StringIO` con un `isatty` parcheado a `True`. |
| Bytes que no son UTF-8 | `sys.stdin` sustituido por un `io.TextIOWrapper(io.BytesIO(b"\xff\xfe"), encoding="utf-8")`. Se espera código 1 y `ERR_REPORT_ENCODING`. |
| Contraseña | `mock.patch("mi6.cli.prompts.getpass.getpass", side_effect=["clave-segura-1", "clave-segura-1"])` para un agente nuevo, o con un solo valor para uno existente. |
| Con y sin terminal | `mock.patch("mi6.cli.prompts.require_terminal")` para el caso normal, o con `side_effect=NoTerminalError` para comprobar el código 2 (RF-2.7). |
| Ctrl+C | `getpass` con `side_effect=KeyboardInterrupt`. Se comprueba el código 130 y que `missions.json` sigue byte a byte igual. |
| Salida sin UTF-8 | `sys.stdout` sustituido por un `io.TextIOWrapper(io.BytesIO(), encoding="ascii")`. Se comprueba que `list` con tildes termina con 0 (RF-7.6). |

### 6.3 Test de descifrado (criterio de finalización)

En `tests/core/test_crypto.py` y `tests/core/test_operations.py`:

1. **Registrar:** crear una misión con el informe `"Ñandú 🦩 en Estambul"` y la contraseña `"clave-segura-1"`.
2. **Sin texto en claro:** leer `missions.json` como **bytes** y comprobar que el informe no aparece ni en UTF-8 ni en su forma escapada `Ñ`. La contraseña tampoco debe aparecer.
3. **Descifrar con la contraseña correcta:** con `crypto.derive_key` y `crypto.decrypt_report`, usando la sal y las iteraciones del JSON, el resultado es el texto original normalizado.
4. **Contraseña incorrecta:** con `"clave-segura-2"` se lanza `AuthenticationError`.
5. **Token manipulado:** con un carácter cambiado en `report_token`, el descifrado lanza `AuthenticationError`, y `schema.py` lo marca como corrupto si el formato deja de ser un token Fernet válido.
6. **Archivar:** después de archivar, el token sigue descifrándose con la contraseña correcta (RF-5.2 no lo toca).

### 6.4 Matriz de cobertura

| Archivo de test | Qué cubre | Requisitos |
|---|---|---|
| `test_errors.py` | Jerarquía de excepciones y sus atributos de datos | Base de RF-1 a RF-6 |
| `test_models.py` | `to_dict()` de los modelos coincide con el JSON de la sección 2.2 | RF-3.4, RF-4.2, RF-5.2 |
| `test_messages.py` | Todas las constantes de la tabla 4.6 existen y se pueden formatear | RNF-4, RF-7.5 |
| `test_acceptance.py` | Test de descifrado de la sección 6.3 | RF-3.3, RF-5.2, RNF-1 |
| `test_edge_cases.py` | Cada caso límite de la sección 6 de la spec a través de `main()` | RF-1 a RF-7 |
| `test_performance.py` | `list` con 1.000 misiones en menos de 1 s | RNF-6 |
| `test_validation.py` | Códigos válidos e inválidos, amenazas, nombres clave e informes de la sección 6 de la spec, recorridos con `subTest` | RF-1.1, RF-3.5, RF-3.7 a RF-3.9, RF-2.3 |
| `test_crypto.py` | Derivación determinista, verificador, ida y vuelta del cifrado, contraseña incorrecta, token manipulado, NFC de la contraseña | RF-2.5, RF-2.6, RF-3.3, RNF-1 |
| `test_risk.py` | Vacío, solo archivadas, límites 5, 6, 10 y 11, orden y pureza | RF-4.3 a RF-4.5, RF-5.3 |
| `test_schema.py` | Cada regla de la tabla 2.3 rota una a una (versión 2, `threat_level: true`, fecha sin zona horaria, duplicados, clave extra...) | RF-6.4 |
| `test_storage.py` | Primer uso con modos `0700` y `0600`, permisos `0644` y `0755` (con `os.chmod`), enlaces simbólicos (con `os.symlink`), restos (`mkdir` sin JSON, temporal huérfano), atomicidad (`os.replace` parcheado para lanzar `OSError` o `KeyboardInterrupt`), bloqueo ocupado, root (`os.geteuid` parcheado a 0), sin directorio personal (`Path.home` parcheado para lanzar `RuntimeError`) | RF-6.1 a RF-6.9, RNF-2 |
| `test_operations.py` | Flujos completos de create, list y archive en el núcleo, duplicado activo y archivado, mismo nombre en dos agentes, archivar dos veces, contraseña incorrecta sin cambios, `list` sin datos que no crea nada, orden de registro con dos misiones en el mismo minuto, reloj atrasado | RF-2 a RF-5 |
| `test_render.py` | Formato de fecha local, traducción de estados y niveles, `sanitize` con `\x1b[2J` y U+202E | RF-4.2, RF-4.8 |
| `test_prompts.py` | `require_terminal` con `os.open` parcheado, `GetPassWarning` convertida en error, lectura del informe por tubería e interactiva | RF-2.1, RF-2.7, RF-3.2 |
| `test_main.py` | Cada fila de la tabla 4.6 con su código de salida, `--report` rechazado con 2, `-h` con 0, orden desconocida con 2, Ctrl+C con 130, error inesperado con 3 | RF-7.1 a RF-7.6, RNF-4 |

**Bloqueo ocupado sin subprocesos:** los bloqueos de `flock` pertenecen a cada archivo abierto. Si el propio test abre `missions.lock` con otro descriptor y toma `LOCK_EX`, la operación bajo prueba recibe `OperationInProgressError`. No hace falta lanzar procesos.

**Tests de entorno:** los de permisos y enlaces simbólicos se saltan con `skipUnless` si se ejecutan como root (root ignora los permisos) o fuera de macOS y Linux (RNF-5 y RNF-7).

**Rendimiento (RNF-6):** un test en `test_performance.py` genera 1.000 misiones con `kdf_iterations=1_000` y comprueba que `list_active_missions` tarda menos de 1 s. La medición con 600.000 iteraciones (menos de 2 s) es una prueba manual documentada en el README, para no hacer lenta la batería.

---

## 7. Cumplimiento de la constitución

| Principio | Cómo lo cumple el plan |
|---|---|
| 1. Stack mínimo | Solo `cryptography` como dependencia externa; `argparse`, `hashlib`, `fcntl`, `json`, `getpass` y `unittest` son de la librería estándar (D1, D5, D6). |
| 2. Spec antes que código | El plan parte de la spec aprobada y referencia sus RF en cada sección. |
| 3. Núcleo aislado | `core/` no importa `argparse` ni `sys` ni usa `print()` ni `input()`; comunica con excepciones con datos y recibe `data_dir` y `now` como parámetros. |
| 4. Tests obligatorios | Cada función pública de `core/` está en la matriz 6.4; la clase base impide tocar `~/.mi6` real. |
| 5. Persistencia segura | `~/.mi6/missions.json` con `0600`, carpeta `0700`, escritura atómica (2.5), informes cifrados desde el registro y ningún secreto en el repositorio (2.4). |
| 6. Idioma | Identificadores y valores del JSON en inglés; todos los textos para el agente en `cli/messages.py` (4.6). |

## 8. Siguiente paso

Desglosar este plan en tareas ordenadas en `specs/001-mi6-mvp/tasks.md`: errores y modelos, luego validación, cripto, riesgo, esquema, almacenamiento, operaciones y, al final, la CLI. Cada tarea irá acompañada de sus tests.
