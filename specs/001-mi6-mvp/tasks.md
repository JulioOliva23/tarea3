# Tareas 001: MVP operativo de mi6-cli

**Spec:** `specs/001-mi6-mvp/spec.md` (aprobada) · **Plan:** `specs/001-mi6-mvp/plan.md` (aprobado) · **Constitución:** `docs/constitution.md`

## Reglas de ejecución

- **Orden:** las tareas se hacen en orden. Ninguna empieza antes de que estén cerradas sus dependencias (**Depende de**).
- **Tamaño:** cada tarea dura como máximo 30 minutos. Si se alarga, se divide antes de seguir.
- **Tests:** cada tarea incluye los tests unitarios de lo que crea (principio 4). Los tests usan siempre directorios temporales, nunca `~/.mi6`.
- **Commit:** una tarea se cierra con un commit propio, en inglés, después de que `python -m unittest discover -s tests` pase entero.
- **Divergencias:** si una tarea obliga a apartarse del plan o de la spec, se actualiza primero el documento y después el código (principio 2).

---

## Fase 1: Entorno y seguridad de archivos

- [ ] **T01 · Esqueleto del proyecto** (~20 min)
  - Módulo: `pyproject.toml`, `mi6/__init__.py`, `mi6/core/__init__.py`, `mi6/cli/__init__.py`, `tests/__init__.py`, `tests/core/__init__.py`, `tests/cli/__init__.py`
  - Cubre: principio 1 de la constitución, RNF-5
  - Detalle: `requires-python >= 3.11`; única dependencia: `cryptography`; script `mi6 = mi6.cli.main:main`, que se implementará en T41.
  - Depende de: —
  - Hecho cuando: `pip install -e .` termina sin errores con `cryptography` como única dependencia y `python -m unittest discover -s tests` informa de 0 tests sin errores.

- [ ] **T02 · Excepciones de dominio** (~20 min)
  - Módulo: `mi6/core/errors.py`, `tests/core/test_errors.py`
  - Cubre: base de RF-1.2, RF-2.4, RF-2.6, RF-3.10, RF-5.4 y RF-6.1 a RF-6.9 (tabla de excepciones del plan, sección 1)
  - Detalle: `Mi6Error` y todas sus subclases, con los atributos de datos (`field`, `rule`, `path`, `current_mode`, `expected_mode`, `reason`, `code_name`, `status`). Ningún texto en español.
  - Depende de: T01
  - Hecho cuando: `test_errors.py` comprueba para cada excepción de la tabla del plan su clase base y sus atributos, y pasa.

- [ ] **T03 · Ruta de datos y comprobaciones de entorno** (~20 min)
  - Módulo: `mi6/core/storage.py` (`resolve_data_dir`), `tests/core/test_storage.py`
  - Cubre: RF-6.9
  - Detalle: devuelve `Path.home() / ".mi6"`. Lanza `UnsafeEnvironmentError("root")` si `os.geteuid() == 0` y `UnsafeEnvironmentError("no_home")` si `Path.home()` falla o devuelve una ruta relativa.
  - Depende de: T02
  - Hecho cuando: con `os.geteuid` y `Path.home` parcheados, los tests de root, de directorio personal ausente y de ruta válida pasan.

- [ ] **T04 · Clase base de tests** (~20 min)
  - Módulo: `tests/helpers.py` (`Mi6TestCase`)
  - Cubre: RNF-7, principio 4
  - Detalle: `setUp` crea un `TemporaryDirectory` y define `self.data_dir = <tmp>/.mi6` y `self.now` (una fecha fija con zona horaria). Además parchea `storage.resolve_data_dir` para que falle con `AssertionError`.
  - Depende de: T03
  - Hecho cuando: un test que hereda de `Mi6TestCase` y llama a `resolve_data_dir()` falla con `AssertionError`, y `self.data_dir` no existe al empezar cada test.

- [ ] **T05 · Detección de enlaces simbólicos** (~20 min)
  - Módulo: `mi6/core/storage.py` (`check_no_symlinks`), `tests/core/test_storage.py`
  - Cubre: RF-6.3
  - Detalle: hace `os.lstat` sobre `data_dir`, `missions.json` y `missions.lock` si existen, y lanza `SymlinkError(path)` en cuanto encuentra un enlace simbólico.
  - Depende de: T04
  - Hecho cuando: los tests que crean con `os.symlink` un enlace en cada una de las tres rutas reciben `SymlinkError` con la ruta correcta, y el caso sin enlaces no lanza nada.

- [ ] **T06 · Comprobación de permisos y propietario** (~25 min)
  - Módulo: `mi6/core/storage.py` (`check_permissions`), `tests/core/test_storage.py`
  - Cubre: RF-6.2
  - Detalle: si `st_mode & 0o077 != 0` o el propietario no es `os.geteuid()`, lanza `InsecurePermissionsError` con el modo actual y el esperado (`0700` para la carpeta, `0600` para los archivos). Nunca cambia los permisos. Los tests se saltan con `skipUnless` si se ejecutan como root.
  - Depende de: T05
  - Hecho cuando: los tests con la carpeta en `0755` y el JSON en `0644` reciben la excepción con `current_mode` y `expected_mode` correctos, y los modos en disco siguen iguales después.

- [ ] **T07 · Inicialización del primer uso** (~20 min)
  - Módulo: `mi6/core/storage.py` (`initialize_data_dir`), `tests/core/test_storage.py`
  - Cubre: RF-6.6
  - Detalle: hace `mkdir` con `0700` y un `chmod` explícito, y crea `missions.lock` vacío con `0600` y `O_NOFOLLOW`. No crea `missions.json`.
  - Depende de: T06
  - Hecho cuando: después de llamarla con un `umask` de `0o000`, el test comprueba que la carpeta tiene `0700`, el lock tiene `0600` y `missions.json` no existe.

- [ ] **T08 · Bloqueos exclusivo y compartido** (~30 min)
  - Módulo: `mi6/core/storage.py` (`exclusive_lock`, `shared_lock`), `tests/core/test_storage.py`
  - Cubre: RF-6.8, RF-4.6
  - Detalle: gestores de contexto con `fcntl.flock` y `LOCK_NB`. Si no se puede tomar el bloqueo → `OperationInProgressError`. `shared_lock` abre el lock sin `O_CREAT`; si no existe → `CorruptDataError("incomplete")`.
  - Depende de: T07
  - Hecho cuando: un test que toma `LOCK_EX` con otro descriptor hace que tanto `exclusive_lock` como `shared_lock` lancen `OperationInProgressError`, y dos `shared_lock` a la vez no fallan.

- [ ] **T09 · Detección de restos incompletos** (~20 min)
  - Módulo: `mi6/core/storage.py` (`check_no_remnants`), `tests/core/test_storage.py`
  - Cubre: RF-6.7
  - Detalle: lanza `CorruptDataError("incomplete")` si `data_dir` existe y falta `missions.lock` o `missions.json`, o si hay algún `.missions.json.tmp-*`.
  - Depende de: T08
  - Hecho cuando: los tres casos de prueba (carpeta vacía, solo el lock, temporal huérfano) lanzan la excepción y un `data_dir` completo no lanza nada.

- [ ] **T10 · Lectura del expediente** (~20 min)
  - Módulo: `mi6/core/storage.py` (`read_document`), `tests/core/test_storage.py`
  - Cubre: RF-6.1, RF-6.5, RF-4.6
  - Detalle: abre con `O_NOFOLLOW` y lee el JSON como UTF-8. Un JSON inválido → `CorruptDataError("unreadable")`; un `OSError` → `DataAccessError`. Devuelve un `dict` sin validar.
  - Depende de: T09
  - Hecho cuando: los tests con un JSON válido, uno truncado, uno con bytes que no son UTF-8 y otro sin permiso de lectura devuelven el `dict` o lanzan la excepción esperada.

- [ ] **T11 · Escritura atómica** (~30 min)
  - Módulo: `mi6/core/storage.py` (`write_document_atomic`), `tests/core/test_storage.py`
  - Cubre: RF-6.1, RF-7.3, RNF-2
  - Detalle: `mkstemp` en `data_dir`, escritura, `fsync`, `os.replace` y `fsync` de la carpeta. Ante cualquier `BaseException` borra el temporal y relanza.
  - Depende de: T10
  - Hecho cuando: con `os.replace` parcheado para lanzar `OSError` y `KeyboardInterrupt`, el `missions.json` previo sigue byte a byte igual y no queda ningún `.missions.json.tmp-*`.

## Fase 2: Modelos y validaciones

- [ ] **T12 · Modelos de dominio** (~25 min)
  - Módulo: `mi6/core/models.py`, `tests/core/test_models.py`
  - Cubre: RF-3.4, RF-4.2, RF-5.2 y el modelo de datos del plan, secciones 2.2 y 2.3
  - Detalle: enums `MissionStatus` (`active`, `archived`) y `RiskLevel` (`low`, `medium`, `critical`). Dataclasses inmutables `KdfParams`, `Mission`, `AgentRecord`, `RiskReport` y `MissionsDocument`, cada una con `to_dict()`.
  - Depende de: T02
  - Hecho cuando: `MissionsDocument.to_dict()`, construido con los datos del ejemplo del plan, produce exactamente las mismas claves y tipos que el JSON de la sección 2.2.

- [ ] **T13 · Validación del código de agente y de la amenaza** (~20 min)
  - Módulo: `mi6/core/validation.py` (`validate_agent_code`, `validate_threat_level`), `tests/core/test_validation.py`
  - Cubre: RF-1.1, RF-1.2, RF-3.5, RF-3.6
  - Detalle: `strip()` y después `re.fullmatch` con `00[1-9]` y `[1-5]`. Devuelve el código limpio y la amenaza como `int`.
  - Depende de: T02
  - Hecho cuando: con `subTest`, ` 007 ` y `3` se aceptan, y `000`, `0007`, `07`, `00A`, `００７`, el vacío, `0`, `6`, `03`, `+3`, `3.0`, `-1`, `٣` y `tres` lanzan la excepción correcta.

- [ ] **T14 · Validación del nombre clave** (~15 min)
  - Módulo: `mi6/core/validation.py` (`validate_code_name`), `tests/core/test_validation.py`
  - Cubre: RF-3.7, RF-3.9
  - Detalle: `re.fullmatch("[A-Za-z0-9-]{1,30}")` sin `strip`; devuelve el nombre en mayúsculas.
  - Depende de: T13
  - Hecho cuando: `skyfall` devuelve `SKYFALL`, y los casos `../x`, `A B`, `ÁGUILA`, la versión cirílica de `SKYFALL`, el nombre con un ZWSP, el que contiene `\x1b` y el de 31 caracteres lanzan `ValidationError(field="code_name")`.

- [ ] **T15 · Normalización y validación del informe** (~30 min)
  - Módulo: `mi6/core/validation.py` (`normalize_report`), `tests/core/test_validation.py`
  - Cubre: RF-3.8, RF-3.9
  - Detalle: convierte `\r\n` en `\n`, hace `strip()` y normaliza a NFC. La longitud tiene que estar entre 1 y 500. Se rechazan los caracteres `Cc` salvo `\n` y `\t`, los `Cf` salvo U+200D, y los `Cs`, `Co` y `Cn`.
  - Depende de: T13
  - Hecho cuando: los textos con tildes, eñes, 👨‍👩‍👧 y saltos de línea se aceptan, y el vacío, el de solo NBSP, el que contiene `\x1b[2J` o U+202E y el de 501 caracteres se rechazan, cada uno con su `rule`.

- [ ] **T16 · Política de contraseña** (~15 min)
  - Módulo: `mi6/core/validation.py` (`validate_new_password`), `tests/core/test_validation.py`
  - Cubre: RF-2.3, RF-2.4
  - Detalle: normaliza a NFC, exige al menos 8 caracteres y que la confirmación coincida. Lanza `PasswordPolicyError(rule="too_short" | "mismatch")`.
  - Depende de: T13
  - Hecho cuando: los tests con 7 caracteres, con confirmación distinta y con 8 caracteres válidos dan `too_short`, `mismatch` y aceptación, respectivamente.

- [ ] **T17 · Esquema: estructura general y agentes** (~25 min)
  - Módulo: `mi6/core/schema.py` (`parse_document`, primera parte), `tests/core/test_schema.py`
  - Cubre: RF-6.4, RF-6.5
  - Detalle: valida `schema_version == 1`, las claves exactas en cada nivel, las claves de agente con `00[1-9]`, el bloque `kdf` (algoritmo, `iterations >= 1`, sal de 16 bytes en Base64) y el formato Fernet de `key_check`. Cualquier fallo → `CorruptDataError("invalid")`.
  - Depende de: T12, T13
  - Hecho cuando: el ejemplo del plan se acepta y cada variante rota (versión 2, clave extra, clave que falta, agente `010`, sal de 15 bytes, `key_check` que no es Fernet) lanza `CorruptDataError`.

- [ ] **T18 · Esquema: misiones** (~25 min)
  - Módulo: `mi6/core/schema.py` (`parse_document`, segunda parte), `tests/core/test_schema.py`
  - Cubre: RF-6.4, RF-3.10
  - Detalle: valida `code_name` en mayúsculas, `threat_level` como `int` y no `bool` entre 1 y 5, `status` válido, `created_at` con zona horaria, `report_token` con formato Fernet y que no haya duplicados dentro de un agente. Devuelve un `MissionsDocument`.
  - Depende de: T14, T17
  - Hecho cuando: `threat_level: true`, `threat_level: 6`, `status: "lost"`, una fecha sin zona horaria, un token truncado y un `SKYFALL` repetido en el mismo agente lanzan `CorruptDataError`, y el ejemplo del plan da un `MissionsDocument`.

## Fase 3: Criptografía y contraseñas

- [ ] **T19 · Derivación de clave** (~20 min)
  - Módulo: `mi6/core/crypto.py` (`DEFAULT_ITERATIONS`, `new_salt`, `derive_key`), `tests/core/test_crypto.py`
  - Cubre: RF-3.3, RNF-1
  - Detalle: `new_salt()` usa `secrets.token_bytes(16)`. `derive_key` normaliza la contraseña a NFC, aplica `hashlib.pbkdf2_hmac("sha256", ..., dklen=32)` y codifica el resultado en Base64 URL-safe.
  - Depende de: T01
  - Hecho cuando: la misma contraseña y sal dan la misma clave, una sal distinta da otra clave, la contraseña en NFC y en NFD dan la misma clave, y `DEFAULT_ITERATIONS == 600_000`.

- [ ] **T20 · Verificador de contraseña** (~20 min)
  - Módulo: `mi6/core/crypto.py` (`make_key_check`, `verify_key`), `tests/core/test_crypto.py`
  - Cubre: RF-2.5, RF-2.6
  - Detalle: `make_key_check` cifra con Fernet la constante `b"mi6:key-check:v1"`. `verify_key` la descifra y la compara; si recibe `InvalidToken` o el resultado no coincide → `AuthenticationError`.
  - Depende de: T19
  - Hecho cuando: con `iterations=1_000`, la clave correcta se verifica, y la incorrecta o un `key_check` con un carácter cambiado lanzan `AuthenticationError`.

- [ ] **T21 · Cifrado y descifrado del informe** (~20 min)
  - Módulo: `mi6/core/crypto.py` (`encrypt_report`, `decrypt_report`), `tests/core/test_crypto.py`
  - Cubre: RF-3.3, RNF-1
  - Detalle: Fernet sobre el informe codificado en UTF-8. `InvalidToken` → `AuthenticationError`.
  - Depende de: T20
  - Hecho cuando: el ciclo de cifrar y descifrar `"Ñandú 🦩 en Estambul"` devuelve el original, dos cifrados del mismo texto dan tokens distintos, y una clave incorrecta o un token manipulado lanzan `AuthenticationError`.

## Fase 4: Lógica central de misiones

- [ ] **T22 · Cálculo del riesgo global** (~20 min)
  - Módulo: `mi6/core/risk.py` (`compute_risk`), `tests/core/test_risk.py`
  - Cubre: RF-4.3, RF-4.4, RF-4.5, RF-5.3
  - Detalle: implementa el pseudocódigo de la sección 3 del plan, con las constantes `LOW_MAX = 5` y `MEDIUM_MAX = 10`.
  - Depende de: T12
  - Hecho cuando: una lista vacía da `0`/`LOW`, solo archivadas dan `0`/`LOW`, 5, 6, 10 y 11 dan `LOW`, `MEDIUM`, `MEDIUM` y `CRITICAL`, el orden se conserva y la lista de entrada no cambia.

- [ ] **T23 · Carga segura del expediente y `agent_exists`** (~25 min)
  - Módulo: `mi6/core/operations.py` (`_load_document`, `agent_exists`), `tests/core/test_operations.py`
  - Cubre: RF-6.1 a RF-6.5, RF-6.7, RF-4.6
  - Detalle: `_load_document` encadena `check_no_symlinks`, `check_permissions`, `check_no_remnants`, `read_document` y `parse_document`, siempre con el bloqueo ya tomado. Si `data_dir` no existe, devuelve un documento vacío sin crear nada.
  - Depende de: T11, T18
  - Hecho cuando: `agent_exists` devuelve `False` sin crear `data_dir` cuando no existe, `True` y `False` según el expediente de ejemplo, y propaga `CorruptDataError` con un JSON roto.

- [ ] **T24 · `preflight_create`** (~20 min)
  - Módulo: `mi6/core/operations.py` (`preflight_create`), `tests/core/test_operations.py`
  - Cubre: RF-1.2, RF-3.6, RF-3.9, RF-3.10, RF-3.11
  - Detalle: valida el código, el nombre clave y la amenaza, y comprueba si hay duplicados con un bloqueo compartido. No pide la contraseña y no escribe nada.
  - Depende de: T23
  - Hecho cuando: `SKYFALL` para 007 lanza `DuplicateMissionError(status=active)`, `SPECTRE` lanza `DuplicateMissionError(status=archived)`, `SKYFALL` para 005 se acepta, y `missions.json` no cambia en ningún caso.

- [ ] **T25 · `create_mission` para un agente nuevo** (~30 min)
  - Módulo: `mi6/core/operations.py` (`create_mission`), `tests/core/test_operations.py`
  - Cubre: RF-2.3, RF-2.4, RF-3.1, RF-3.3, RF-3.4, RF-6.6
  - Detalle: dentro de `exclusive_lock`: hace el primer uso con `initialize_data_dir` si hace falta, valida la política de contraseña, crea la sal y `key_check`, cifra el informe, fija `created_at = now.isoformat(timespec="seconds")` con zona horaria y escribe de forma atómica. Acepta `kdf_iterations` (por defecto `DEFAULT_ITERATIONS`) y `now`.
  - Depende de: T16, T21, T24
  - Hecho cuando: partiendo de un `data_dir` inexistente, el test crea la misión y comprueba los modos `0700` y `0600`, `status == "active"`, el `created_at` esperado y que la contraseña con una confirmación distinta no deja nada en el disco.

- [ ] **T26 · `create_mission` para un agente existente** (~20 min)
  - Módulo: `mi6/core/operations.py` (`create_mission`), `tests/core/test_operations.py`
  - Cubre: RF-2.5, RF-2.6, RF-3.10, RF-3.11, RF-4.2
  - Detalle: dentro del bloqueo exclusivo vuelve a validar todo, verifica `key_check` con la sal guardada, cifra con la misma clave y añade la misión al final de la lista.
  - Depende de: T25
  - Hecho cuando: con la contraseña correcta, la segunda misión queda en la posición 2, y con la incorrecta se lanza `AuthenticationError` y el archivo sigue byte a byte igual.

- [ ] **T27 · `list_active_missions`** (~20 min)
  - Módulo: `mi6/core/operations.py` (`list_active_missions`), `tests/core/test_operations.py`
  - Cubre: RF-4.1, RF-4.2, RF-4.3, RF-4.5, RF-4.6, RF-5.3
  - Detalle: no recibe contraseña. Usa un bloqueo compartido, filtra por agente y delega en `compute_risk`.
  - Depende de: T22, T23
  - Hecho cuando: el expediente de ejemplo da 007 → SKYFALL y GOLDENEYE con `7`/`MEDIUM`, y un `data_dir` inexistente da `0`/`LOW` y sigue sin existir después.

- [ ] **T28 · `get_active_mission` y `archive_mission`** (~30 min)
  - Módulo: `mi6/core/operations.py` (`get_active_mission`, `archive_mission`), `tests/core/test_operations.py`
  - Cubre: RF-5.1, RF-5.2, RF-5.3, RF-5.4, RF-2.5, RF-2.6
  - Detalle: `get_active_mission` busca sin contraseña. `archive_mission`, dentro del bloqueo exclusivo, recarga, comprueba que la misión sigue activa, verifica `key_check`, cambia `status` a `"archived"` sin tocar `report_token` y escribe de forma atómica.
  - Depende de: T26
  - Hecho cuando: archivar SKYFALL con la contraseña correcta lo saca de `list_active_missions`, archivarlo otra vez lanza `MissionNotFoundError`, y con la contraseña incorrecta se lanza `AuthenticationError` sin cambios.

- [ ] **T29 · Garantías ante fallos en las operaciones** (~20 min)
  - Módulo: `tests/core/test_operations.py`
  - Cubre: RF-5.5, RF-6.8, RF-7.3, RNF-2
  - Detalle: añade tests de `create_mission` y `archive_mission` con `os.replace` parcheado para lanzar `OSError` o `KeyboardInterrupt`, y con un bloqueo exclusivo externo tomado.
  - Depende de: T28
  - Hecho cuando: en los seis escenarios (dos operaciones por tres fallos) el `missions.json` previo sigue byte a byte igual y no quedan temporales.

## Fase 5: Interfaz CLI y mensajes

- [ ] **T30 · Catálogo de mensajes** (~25 min)
  - Módulo: `mi6/cli/messages.py`, `tests/cli/test_messages.py`
  - Cubre: RNF-4, RF-7.5, RF-7.2 (`HELP`)
  - Detalle: todas las constantes de la tabla 4.6 del plan con sus `{marcadores}`, y el texto completo de `HELP` con los tres comandos, las banderas y ejemplos con `< informe.txt`.
  - Depende de: T01
  - Hecho cuando: el test recorre la lista de constantes del plan y comprueba que cada una existe, no está vacía y se puede formatear con sus marcadores sin lanzar `KeyError`.

- [ ] **T31 · Saneado y traducciones de pantalla** (~20 min)
  - Módulo: `mi6/cli/render.py` (`sanitize`, `format_local_datetime`, `status_label`, `risk_label`), `tests/cli/test_render.py`
  - Cubre: RF-4.2, RF-4.8
  - Detalle: `sanitize` sustituye los caracteres `Cc` y `Cf` por `?`. Las fechas se muestran como `astimezone()` con el formato `%Y-%m-%d %H:%M`. `active` y `archived` se traducen a `ACTIVA` y `ARCHIVADA`, y `low`, `medium` y `critical` a `BAJO`, `MEDIO` y `CRÍTICO`.
  - Depende de: T12, T30
  - Hecho cuando: `sanitize("A\x1b[2JB‮")` devuelve `"A?[2JB?"`, `2026-10-20T09:15:42+01:00` se muestra como `2026-10-20 09:15` con `TZ=Europe/London`, y las cinco traducciones coinciden.

- [ ] **T32 · Tabla de misiones y línea de riesgo** (~20 min)
  - Módulo: `mi6/cli/render.py` (`mission_table`, `risk_line`, `empty_list`), `tests/cli/test_render.py`
  - Cubre: RF-4.2, RF-4.3, RF-4.4, RF-4.5, RF-4.7
  - Detalle: genera el formato de la sección 4.5 del plan a partir de un `RiskReport`, sin incluir nunca el informe.
  - Depende de: T22, T31
  - Hecho cuando: el `RiskReport` de 007 del ejemplo produce exactamente el bloque de la sección 4.5 del plan, y un informe vacío produce `LIST_EMPTY` con `0 · BAJO`.

- [ ] **T33 · Comprobación de terminal interactiva** (~15 min)
  - Módulo: `mi6/cli/prompts.py` (`NoTerminalError`, `require_terminal`), `tests/cli/test_prompts.py`
  - Cubre: RF-2.7
  - Detalle: abre y cierra `/dev/tty` con `O_RDWR | O_NOCTTY`. Si recibe un `OSError` → `NoTerminalError`.
  - Depende de: T01
  - Hecho cuando: con `os.open` parcheado para lanzar `OSError`, la función lanza `NoTerminalError`, y con `os.open` devolviendo un descriptor falso termina sin error y lo cierra.

- [ ] **T34 · Lectura de la contraseña** (~20 min)
  - Módulo: `mi6/cli/prompts.py` (`read_password`, `read_new_password`), `tests/cli/test_prompts.py`
  - Cubre: RF-2.1, RF-2.2, RF-2.3
  - Detalle: usa `getpass.getpass` con `warnings` configurado para convertir `GetPassWarning` en error. `read_new_password` pide la contraseña dos veces y devuelve las dos (la comparación es cosa de `core`).
  - Depende de: T30, T33
  - Hecho cuando: con `getpass` parcheado, `read_new_password` devuelve las dos entradas en orden, y una `GetPassWarning` simulada acaba en `NoTerminalError`.

- [ ] **T35 · Lectura del informe** (~20 min)
  - Módulo: `mi6/cli/prompts.py` (`read_report`), `tests/cli/test_prompts.py`
  - Cubre: RF-3.2, RF-3.9
  - Detalle: si la entrada estándar no es una terminal, la lee entera. Si lo es, muestra `REPORT_PROMPT` y lee hasta Ctrl+D. Un `UnicodeDecodeError` → `ValidationError(field="report", rule="encoding")`.
  - Depende de: T34
  - Hecho cuando: los tests con `StringIO` como tubería, con un `isatty` parcheado a `True` y con un `TextIOWrapper(BytesIO(b"\xff"))` devuelven el texto, muestran el aviso y lanzan `encoding`, respectivamente.

- [ ] **T36 · Parser de argumentos en español** (~30 min)
  - Módulo: `mi6/cli/main.py` (`build_parser`, `UsageError`), `tests/cli/test_main.py`
  - Cubre: RF-7.1, RF-7.2, RF-3.2
  - Detalle: `argparse` con `add_help=False`, un `-h/--help` propio, `error()` sobrescrito para lanzar `UsageError`, y los subcomandos `create`, `list` y `archive` con `-a`, `-n` y `-t` según la tabla 4.1 del plan.
  - Depende de: T30
  - Hecho cuando: `["--help"]` y `["list", "-h"]` muestran `HELP` y devuelven 0, y `[]`, `["foo"]`, `["list"]` y `["create", ..., "--report", "x"]` devuelven 2 con `ERR_USAGE`, todo sin una sola palabra en inglés en la salida.

- [ ] **T37 · Mapa de excepciones, Ctrl+C y codificación** (~25 min)
  - Módulo: `mi6/cli/main.py` (`main`, `_error_message`), `tests/cli/test_main.py`
  - Cubre: RF-7.3, RF-7.4, RF-7.5, RF-7.6
  - Detalle: `main(argv=None, data_dir=None) -> int`. Hace `reconfigure(errors="replace")` de la salida estándar y la de error. Traduce cada excepción a su mensaje y código según la tabla 4.7 del plan. `KeyboardInterrupt` → 130, cualquier otra excepción → `UNEXPECTED` y 3, sin traza.
  - Depende de: T02, T36
  - Hecho cuando: un test parametrizado inyecta cada excepción de la tabla 4.7 en un comando simulado y comprueba el código de salida y la constante de mensaje correspondientes.

- [ ] **T38 · Flujo del comando `create`** (~30 min)
  - Módulo: `mi6/cli/main.py` (`_run_create`), `tests/cli/test_main.py`
  - Cubre: RF-3.1, RF-2.3, RF-2.7, RF-3.2, RF-3.10
  - Detalle: sigue la secuencia de la sección 4.4 del plan: `preflight_create`, `require_terminal`, `read_report`, `agent_exists`, una o dos contraseñas, `create_mission` y `CREATE_OK`.
  - Depende de: T28, T35, T37
  - Hecho cuando: con la entrada estándar y `getpass` simulados, un agente nuevo recibe `CREATE_OK` y código 0, un duplicado devuelve 1 sin pedir el informe, y sin terminal devuelve 2.

- [ ] **T39 · Flujo del comando `list`** (~15 min)
  - Módulo: `mi6/cli/main.py` (`_run_list`), `tests/cli/test_main.py`
  - Cubre: RF-4.1 a RF-4.8
  - Detalle: llama a `list_active_missions` y a `render`, sin pedir contraseña.
  - Depende de: T32, T37
  - Hecho cuando: con el expediente de ejemplo, `["list", "-a", "007"]` devuelve 0 y la salida contiene `RIESGO GLOBAL: 7 · MEDIO`, y con `getpass` parcheado para fallar no se llama nunca.

- [ ] **T40 · Flujo del comando `archive`** (~20 min)
  - Módulo: `mi6/cli/main.py` (`_run_archive`), `tests/cli/test_main.py`
  - Cubre: RF-5.1 a RF-5.4
  - Detalle: `get_active_mission`, `ARCHIVE_PREVIEW`, `require_terminal`, `read_password`, `archive_mission` y `ARCHIVE_OK`.
  - Depende de: T38
  - Hecho cuando: con `getpass` simulado, `ARCHIVE_PREVIEW` sale antes de la petición de contraseña y el resultado es 0, una misión inexistente devuelve 1 sin pedir contraseña, y una contraseña incorrecta devuelve 1 con `ERR_AUTH`.

- [ ] **T41 · Punto de entrada** (~10 min)
  - Módulo: `mi6/__main__.py`, `pyproject.toml`
  - Cubre: RF-7.2, RF-7.4
  - Detalle: `__main__.py` llama a `sys.exit(main())`.
  - Depende de: T40
  - Hecho cuando: `python -m mi6 --help` y `mi6 --help` muestran la ayuda en español y `echo $?` imprime `0`.

## Fase 6: Tests finales

- [ ] **T42 · Test de descifrado (criterio de finalización)** (~25 min)
  - Módulo: `tests/core/test_acceptance.py`
  - Cubre: RF-3.3, RF-5.2, RNF-1, sección 8 de la spec
  - Detalle: los seis pasos de la sección 6.3 del plan.
  - Depende de: T29
  - Hecho cuando: el test confirma que ni el informe ni la contraseña aparecen en los bytes de `missions.json`, que se descifra con la contraseña correcta antes y después de archivar, y que falla con la incorrecta y con el token manipulado.

- [ ] **T43 · Casos límite de entrada (spec, sección 6)** (~25 min)
  - Módulo: `tests/cli/test_edge_cases.py`
  - Cubre: RF-1.2, RF-2.4, RF-2.6, RF-3.6, RF-3.9, RF-3.10, RF-4.2, RF-4.4, RF-5.4
  - Detalle: un `subTest` por cada caso de entrada de la sección 6 de la spec, ejecutado de principio a fin a través de `main()`.
  - Depende de: T41
  - Hecho cuando: todos los casos de entrada de la sección 6 de la spec tienen un `subTest` con el código de salida y el mensaje esperados, y pasan.

- [ ] **T44 · Casos límite de datos y entorno (spec, sección 6)** (~25 min)
  - Módulo: `tests/cli/test_edge_cases.py`
  - Cubre: RF-4.6, RF-6.2, RF-6.3, RF-6.5, RF-6.7, RF-6.8, RF-6.9, RF-7.3, RF-7.6
  - Detalle: permisos abiertos, enlace simbólico, JSON corrupto, restos, bloqueo ocupado, root, sin directorio personal, Ctrl+C y salida en ASCII, todo a través de `main()`.
  - Depende de: T43
  - Hecho cuando: cada caso de datos y entorno de la sección 6 de la spec devuelve su código (3, 130 o 0) y su mensaje, y `missions.json` sigue byte a byte igual en todos.

- [ ] **T45 · Rendimiento** (~20 min)
  - Módulo: `tests/core/test_performance.py`, `README.md` (sección de medición manual)
  - Cubre: RNF-6
  - Detalle: genera un expediente con 1.000 misiones (`kdf_iterations=1_000`) y mide `list_active_missions`. Documenta la medición manual de `create` con 600.000 iteraciones.
  - Depende de: T27
  - Hecho cuando: el test de `list` con 1.000 misiones pasa por debajo de 1 s, y la medición manual de `create` con 600.000 iteraciones, por debajo de 2 s, queda anotada en el README con el equipo y la fecha.

- [ ] **T46 · Auditoría de la constitución** (~20 min)
  - Módulo: todo el repositorio
  - Cubre: principios 1 a 6 de la constitución
  - Detalle: comprueba que no hay imports prohibidos en `core/`, que no hay texto en español fuera de `messages.py`, que cada función pública de `core/` tiene un test y que las dependencias de `pyproject.toml` son solo `cryptography`.
  - Depende de: T44
  - Hecho cuando: `grep -rnE "import (argparse|sys)|from (argparse|sys)|print\(|input\(" mi6/core` no devuelve nada y la lista de funciones públicas de `core/` coincide con la de funciones con test.

- [ ] **T47 · README para agentes y Q-Branch** (~25 min)
  - Módulo: `README.md`
  - Cubre: RNF-4, RF-3.2, RF-6.7, sección 5.1 de la spec
  - Detalle: está en español. Explica la instalación y los tres comandos con ejemplos. Recomienda `< informe.txt` y advierte de que `echo` deja el informe en el historial. Recoge los riesgos aceptados (sección 5.1 de la spec) y el procedimiento de Q-Branch ante datos corruptos o restos.
  - Depende de: T45
  - Hecho cuando: un desarrollador que no ha leído la spec puede instalar la CLI, registrar, listar y archivar una misión siguiendo solo el README.

- [ ] **T48 · Verificación final en macOS y Linux** (~20 min)
  - Módulo: todo el repositorio, `specs/001-mi6-mvp/spec.md` (sección 8)
  - Cubre: RNF-5, RNF-7, sección 8 de la spec
  - Detalle: ejecuta toda la batería en las dos plataformas y marca cada criterio de finalización de la spec.
  - Depende de: T46, T47
  - Hecho cuando: `python -m unittest discover -s tests` pasa entero en macOS y en Linux y todos los criterios de la sección 8 de la spec tienen una prueba asociada que pasa.
