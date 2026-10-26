# Verificación 001: MVP operativo de mi6-cli

**Estado:** verificado, con reservas (ver secciones 7 y 8) · **Fecha:** 2026-10-26 · **Tarea:** T48
**Spec:** `specs/001-mi6-mvp/spec.md` · **Plan:** `specs/001-mi6-mvp/plan.md` · **Tareas:** `specs/001-mi6-mvp/tasks.md` · **Constitución:** `docs/constitution.md`

Este documento recoge la evidencia de que la implementación cumple los criterios de finalización de la sección 8 de la spec. Todas las cifras proceden de ejecuciones reales del 2026-10-26; ninguna es una estimación.

---

## 1. Resumen

| Entorno | Python | Tests | Resultado | Omitidos | Tiempo de la suite |
|---|---|---|---|---|---|
| macOS 27.0, Apple M2 Pro (arm64) | 3.14.6 | 385 | **OK** | 0 | 1,45 s |
| Linux Debian 13 «trixie», aarch64, kernel 6.12 (Docker), usuario sin privilegios (uid 1000) | **3.11.17** (mínima soportada) | 385 | **OK** | 0 | 2,68 s |
| Linux Debian 13 «trixie», aarch64 (Docker), uid 1000 | 3.13.17 | 385 | **OK** | 0 | 2,47 s |
| Linux Debian 13, aarch64 (Docker), **root** | 3.11.17 | 385 | **OK** | 18 (previsto) | 0,52 s |

El tiempo es el que informa `unittest` («Ran 385 tests in …»). Cerca de 1 s de cada ejecución lo consumen los tests de terminal real, que usan el KDF de producción.

- **Comando:** `python -m unittest discover -s tests -t .`, siempre sobre una copia limpia del repositorio y con `pip install -e .` en un entorno virtual nuevo.
- **Dependencias instaladas:** `cryptography 50.0.2`, más `cffi 2.1.1` y `pycparser 3.12`, que son dependencias suyas. Ninguna más.
- **Tests omitidos como root:** 13 de permisos POSIX y 5 de terminal real. Se omiten porque root ignora los permisos y `mi6` se niega a ejecutarse como root (RF-6.9). Es el comportamiento que prevé el plan (sección 6.4).

### Tests por archivo

| Archivo | Tests | Archivo | Tests |
|---|---|---|---|
| `test_base.py` | 10 | `test_operations.py` | 68 |
| `test_errors.py` | 25 | `test_cli.py` | 84 |
| `test_models.py` | 31 | `test_terminal.py` | 5 |
| `test_validation.py` | 34 | `test_performance.py` | 6 |
| `test_risk.py` | 16 | `test_schema.py` | 13 (con ~120 `subTest`) |
| `test_crypto.py` | 35 | `test_storage.py` | 58 |
| | | **Total** | **385** |

---

## 2. Criterios de finalización (spec, sección 8)

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | La spec está **aprobada** y sin ningún [NECESITA ACLARACIÓN]. | ✅ Cumplido | `spec.md`: «Estado: aprobada». La sección 9 declara que no quedan dudas abiertas. |
| 2 | Todos los criterios de aceptación de RF-1 a RF-7 están cubiertos por tests automáticos que pasan en macOS y Linux. | ✅ Cumplido | Matriz de la sección 3. La suite pasa en los cuatro entornos de la sección 1. |
| 3 | Todos los casos límite de la sección 6 de la spec tienen al menos un test. | ✅ Cumplido | Matriz de la sección 4: 21 de 21 casos. |
| 4 | Un test demuestra que ningún informe aparece en claro en los datos guardados. | ✅ Cumplido | `test_crypto.MandatoryDecryptionTest.test_1_and_2_report_and_password_never_appear_in_clear` busca en los **bytes** de `missions.json` el informe en UTF-8, en su forma escapada `Ñ…` y la contraseña. Refuerzos: `test_operations.CreateFirstMissionTest.test_report_is_encrypted_with_the_agent_password` y `test_terminal.RealTerminalTest.test_full_flow_with_hidden_password`. |
| 5 | Un test demuestra que un informe se descifra con la contraseña correcta y falla con una incorrecta o con el contenido manipulado. | ✅ Cumplido | `MandatoryDecryptionTest`, pasos 3 a 6 del plan (sección 6.3). Además, `KeyCheckTest` y `ReportEncryptionTest` **cambian cada byte** del token, uno a uno, y comprueban que todos se detectan. |
| 6 | Todos los mensajes al agente están en español. | ✅ Cumplido | Todos los textos están en `mi6/cli/messages.py`. `test_cli.LayerBoundaryTest.test_spanish_text_only_in_messages` falla si aparece texto en español en cualquier otro módulo, y `MessagesTest` comprueba que existen las 34 constantes de la tabla 4.6 del plan. `UsageTest` comprueba que nunca se muestra el `usage:` en inglés de `argparse`. |
| 7 | La implementación cumple los seis principios de `docs/constitution.md`. | ⚠️ Cumplido con reserva | Sección 6. La reserva afecta al principio 2: hay divergencias respecto al plan que deben incorporarse a él (sección 7). |

---

## 3. Trazabilidad de requisitos → tests

| Requisito | Tests que lo verifican (archivo · clase o test) |
|---|---|
| **RF-1.1** Códigos 001–009 con `strip` | `test_validation.ValidateAgentCodeTest` · `test_cli.CreateCommandTest.test_piped_report_for_new_agent` (` 007 `) |
| **RF-1.2** Rechazo con código 1, sin cambios | `test_cli.RejectionTest.test_invalid_agent_code_is_access_denied` (en los tres comandos) |
| **RF-1.3** El código es una etiqueta | `test_operations.CreateExistingAgentTest.test_same_code_name_for_another_agent` · `test_cli.ListCommandTest.test_never_asks_for_password` · `test_schema.ParseValidDocumentTest.test_same_code_name_in_two_agents_is_valid` |
| **RF-2.1** Contraseña interactiva y oculta | `test_terminal.RealTerminalTest.test_full_flow_with_hidden_password` (pty real, con control de eco) · `test_cli.PromptPasswordTest` |
| **RF-2.2** La contraseña nunca se guarda ni se muestra | `MandatoryDecryptionTest.test_1_and_2…` · `test_terminal` (`assertNotIn(PASSWORD, output)`) · `KeyCheckTest.test_verifier_does_not_contain_the_constant_or_password` |
| **RF-2.3 / RF-2.4** Primera contraseña: dos veces y ≥ 8 caracteres | `test_validation.ValidateNewPasswordTest` · `test_operations.CreateRejectionsOnFirstUseTest` · `test_cli.RejectionTest.test_new_password_policy` |
| **RF-2.5 / RF-2.6** Verificación; si es incorrecta, código 1 sin cambios | `test_operations.CreateExistingAgentTest.test_wrong_password_changes_nothing` · `ArchiveMissionTest.test_wrong_password_changes_nothing` · `test_cli.RejectionTest.test_wrong_password_changes_nothing` · `test_terminal.test_wrong_password_on_real_terminal` |
| **RF-2.7** Sin terminal: código 2 | `test_terminal.RealTerminalTest.test_no_controlling_terminal_exits_2` (proceso sin terminal de control) · `test_cli.UsageTest.test_no_terminal_on_create/_archive` · `RequireTerminalTest` |
| **RF-2.8** Sin recuperación de informes | `test_cli.UsageTest` (solo existen `create`, `list` y `archive`) · `MandatoryDecryptionTest.test_4_wrong_password_is_rejected` |
| **RF-3.1** Guardar como ACTIVA y confirmar | `test_cli.CreateCommandTest.test_piped_report_for_new_agent` · `test_operations.CreateFirstMissionTest` |
| **RF-3.2** Informe por la entrada estándar o interactivo, nunca como argumento | `test_cli.CreateCommandTest.test_report_is_never_a_command_argument` · `test_interactive_report_shows_prompt_on_stderr` · `ReadReportBodyTest` · `test_terminal` (Ctrl+D real) |
| **RF-3.3** Cifrado autenticado | `test_crypto` (todas las clases) |
| **RF-3.4** Fecha y hora automáticas con zona horaria | `test_operations.CreateFirstMissionTest.test_default_now_is_current_local_time` · `test_stored_document_layout` · `test_cli.UsageTest` (no existe ninguna opción de fecha) |
| **RF-3.5 / RF-3.6** Amenaza: un dígito ASCII del 1 al 5 | `test_validation.ValidateThreatLevelTest` · `test_cli.RejectionTest.test_invalid_threat` |
| **RF-3.7** Nombre clave `[A-Za-z0-9-]{1,30}`, guardado en mayúsculas | `test_validation.ValidateCodeNameTest` · `test_cli.RejectionTest.test_invalid_code_name` |
| **RF-3.8 / RF-3.9** Informe de 1 a 500 caracteres tras NFC, controles y vacíos | `test_validation.NormalizeReportTest` · `test_cli.RejectionTest.test_invalid_report` / `test_non_utf8_report` |
| **RF-3.10** Duplicado, indicando si está activa o archivada | `test_operations.CreateExistingAgentTest.test_duplicate_*` · `PreflightCreateTest.test_detects_duplicates_without_writing` · `test_cli.RejectionTest.test_duplicates_are_rejected_before_reading_report_or_password` |
| **RF-3.11** Mismo nombre clave en dos agentes | `test_operations.CreateExistingAgentTest.test_same_code_name_for_another_agent` |
| **RF-4.1** `list` sin contraseña | `test_operations.ListActiveMissionsTest.test_needs_no_password_and_decrypts_nothing` · `test_cli.ListCommandTest.test_never_asks_for_password` |
| **RF-4.2** Solo activas, hora local, orden de registro | `test_cli.RenderTest.test_plan_example_is_reproduced_exactly` · `test_local_time_conversion` · `ListActiveMissionsTest.test_same_minute_*` / `test_clock_skew_*` |
| **RF-4.3 / RF-4.4** Riesgo global y clasificación | `test_risk` (todas las clases) · `ListActiveMissionsTest.test_lists_active_missions_and_risk` / `test_critical_risk` |
| **RF-4.5 / RF-4.6** Sin misiones o sin datos: 0 · BAJO, sin crear nada | `test_cli.ListCommandTest.test_without_data` · `ListActiveMissionsTest.test_without_data_is_empty_low_and_creates_nothing` |
| **RF-4.7** No mostrar informes | `test_cli.ListCommandTest.test_never_asks_for_password` (`assertNotIn("Estambul")`) · `test_terminal` |
| **RF-4.8** Neutralizar caracteres de control | `test_cli.RenderTest.test_sanitize_*` / `test_stored_data_is_sanitized_in_the_table` · `FailureTest.test_paths_in_errors_are_sanitized` |
| **RF-5.1** Vista previa antes de la contraseña | `test_cli.ArchiveCommandTest.test_preview_is_shown_before_password` · `test_terminal.test_full_flow_with_hidden_password` |
| **RF-5.2 / RF-5.3** Archivar y excluir del listado y del riesgo | `test_operations.ArchiveMissionTest` · `MandatoryDecryptionTest.test_6_report_still_decrypts_after_archiving` |
| **RF-5.4** No encontrada: código 1 | `test_cli.RejectionTest.test_archive_unknown_mission_never_asks_password` / `test_archive_twice` |
| **RF-5.5** Un fallo deja la misión ACTIVA | `test_operations.ArchiveMissionTest.test_failed_write_keeps_mission_active` |
| **RF-6.1** Error de E/S: código 3 sin cambios | `test_storage.WriteDocumentAtomicTest` · `test_cli.FailureTest.test_disk_full_keeps_data` |
| **RF-6.2** Permisos abiertos: código 3 y `chmod` exacto | `test_storage.CheckPermissionsTest` · `test_cli.FailureTest.test_insecure_permissions_tell_exact_chmod` · `DataProblemsTest.test_open_permissions` |
| **RF-6.3** Enlaces simbólicos | `test_storage.CheckNoSymlinksTest` / `LockTest.test_symlinked_lock_file_is_not_followed` · `DataProblemsTest.test_symlinked_*` |
| **RF-6.4 / RF-6.5** Datos corruptos: código 3 sin sobrescribir | `test_schema.ParseInvalidDocumentTest` (~120 variantes) · `test_storage.ReadDocumentTest` · `DataProblemsTest` |
| **RF-6.6** Primer uso con 0700/0600 | `test_storage.InitializeDataDirTest` · `test_operations.CreateFirstMissionTest.test_first_use_creates_private_files` |
| **RF-6.7** Restos incompletos = corrupto | `test_storage.CheckNoRemnantsTest` · `DataProblemsTest.test_orphan_temporary_file` / `test_directory_without_*` |
| **RF-6.8** «Operación en curso» al momento | `test_storage.LockTest` (flock real desde otro descriptor) · `test_cli.FailureTest.test_operation_in_progress` |
| **RF-6.9** Root o sin directorio personal | `test_storage.ResolveDataDirTest` · `test_cli.FailureTest.test_unsafe_environment` / `test_real_root_check_through_resolve_data_dir` |
| **RF-7.1 / RF-7.2** Ayuda en español; uso incorrecto: código 2; `--help`: código 0 | `test_cli.HelpTest` · `UsageTest.test_bad_usage_shows_spanish_help_and_exits_2` (13 casos) |
| **RF-7.3** Ctrl+C: código 130 sin cambios | `test_cli.InterruptTest` (6 puntos) · `test_terminal.test_ctrl_c_*` (SIGINT real) |
| **RF-7.4** Códigos 0, 1, 2, 3 y 130 | `test_cli.ErrorMappingTest.test_exit_codes` y las clases agrupadas por código |
| **RF-7.5** El rechazo indica la regla | `test_cli.MessagesTest.test_every_core_validation_rule_has_a_message` · `RejectionTest` |
| **RF-7.6** Salida sin UTF-8 | `test_cli.OutputEncodingTest` |
| **RNF-1** Seguridad | `test_crypto` · `test_operations.CreateFirstMissionTest.test_report_is_encrypted_with_the_agent_password` |
| **RNF-2** Integridad | `test_storage.WriteDocumentAtomicTest` · `test_operations.*.test_failed_*` · `CreateRejectionsOnFirstUseTest.test_interrupted_first_registration_leaves_no_remnants` |
| **RNF-3** Sin red | `test_cli.LayerBoundaryTest.test_no_network_access` · todas las ejecuciones son locales |
| **RNF-4** Idioma | Criterio 6 de la sección 2 |
| **RNF-5** macOS y Linux | Sección 1 |
| **RNF-6** Rendimiento | `test_performance` · sección 5 |
| **RNF-7** Tests reproducibles sin datos reales | `test_base.MI6TestCaseIsolationTest` / `MI6TestCaseLifecycleTest` |

---

## 4. Casos límite (spec, sección 6)

| # | Caso límite | Test principal |
|---|---|---|
| 1 | Código `000`, `0007`, `07`, `00A`, `００７` o vacío se rechaza; ` 007 ` se acepta | `test_cli.RejectionTest.test_invalid_agent_code_is_access_denied` · `test_validation.ValidateAgentCodeTest` |
| 2 | Amenaza `0`, `6`, `03`, `+3`, `3.0`, `-1`, `٣` o `tres` | `test_cli.RejectionTest.test_invalid_threat` |
| 3 | Nombre clave con `../`, `/`, espacios, tildes, cirílico, invisibles, escapes o más de 30 caracteres | `test_cli.RejectionTest.test_invalid_code_name` |
| 4 | `skyfall` y `SKYFALL` son el mismo nombre | `test_operations.CreateExistingAgentTest.test_duplicate_active_mission` |
| 5 | Duplicado con la misión anterior archivada indica «archivada» | `test_cli.RejectionTest.test_duplicates_are_rejected_before_reading_report_or_password` |
| 6 | Informe vacío, con espacios Unicode, con controles o de 501 caracteres; se aceptan saltos de línea, tildes y emojis | `test_cli.RejectionTest.test_invalid_report` · `test_validation.NormalizeReportTest` |
| 7 | Primera contraseña de 7 caracteres o con confirmación distinta | `test_cli.RejectionTest.test_new_password_policy` |
| 8 | Contraseña incorrecta al registrar o archivar | `test_cli.RejectionTest.test_wrong_password_changes_nothing` |
| 9 | Sin terminal interactiva: código 2 | `test_terminal.RealTerminalTest.test_no_controlling_terminal_exits_2` |
| 10 | Archivar dos veces, o una misión que no existe | `test_cli.RejectionTest.test_archive_twice` / `test_archive_unknown_mission_never_asks_password` |
| 11 | Sin misiones activas o sin datos: 0 · BAJO sin crear nada | `test_cli.ListCommandTest.test_without_data` |
| 12 | Límites de riesgo 5, 6, 10 y 11 | `test_risk.ComputeRiskThresholdsTest.test_boundaries` |
| 13 | Dos misiones en el mismo minuto | `test_operations.ListActiveMissionsTest.test_same_minute_keeps_registration_order` |
| 14 | Reloj atrasado, adelantado o con cambio de zona horaria | `test_operations.ListActiveMissionsTest.test_clock_skew_and_timezone_changes_do_not_change_order` |
| 15 | Permisos abiertos o enlace simbólico | `test_operations.DataProblemsTest.test_open_permissions` / `test_symlinked_*` |
| 16 | Datos corruptos, editados a mano, con el informe cifrado dañado o de versión desconocida | `DataProblemsTest.test_unparseable_json` / `test_hand_edited_invalid_record` / `test_unknown_schema_version` · `MandatoryDecryptionTest.test_5_broken_token_format_is_reported_as_corrupt` |
| 17 | Restos de datos incompletos | `DataProblemsTest.test_orphan_temporary_file` / `test_directory_without_files` |
| 18 | Dos ejecuciones a la vez | `test_operations.CreateExistingAgentTest.test_lock_contention_changes_nothing` · `test_storage.LockTest` |
| 19 | Ejecución como root o sin directorio personal | `test_cli.FailureTest.test_unsafe_environment` / `test_real_root_check_through_resolve_data_dir` |
| 20 | Ctrl+C a mitad de una operación o al pedir la contraseña | `test_cli.InterruptTest` · `test_terminal.test_ctrl_c_at_password_prompt` / `test_ctrl_c_while_typing_the_report` |
| 21 | Salida redirigida o terminal sin UTF-8 | `test_cli.OutputEncodingTest.test_ascii_stdout_does_not_fail` |

---

## 5. Rendimiento (RNF-6)

**Fixture:** un `missions.json` real, válido según el esquema, con **1.000 misiones** repartidas entre los nueve agentes: 400 del agente 007, de las cuales 300 están activas y 100 archivadas. Cada informe es un token Fernet real. Para `create` y `archive`, el agente 009 se regenera con el KDF de producción (600.000 iteraciones). Los valores son medianas, con el máximo entre paréntesis.

| Medición | Límite RNF-6 | macOS · Py 3.14.6 | Linux · Py 3.11.17 | Linux · Py 3.13.17 |
|---|---|---|---|---|
| `list_active_missions` en el núcleo (n=20) | < 1 s | 3,8 ms (4,1) | 5,1 ms (7,4) | 4,2 ms (5,3) |
| `python -m mi6 list -a 007`, proceso completo desde el lanzamiento (n=10) | < 1 s | 65,6 ms (78,0) | 137,1 ms (150,0) | 150,9 ms (170,0) |
| `create_mission` con KDF de 600.000 (n=5) | < 2 s | 61,1 ms (62,5) | 84,5 ms (88,8) | 79,8 ms (80,8) |
| `archive_mission` con KDF de 600.000 (n=5) | < 2 s | 61,1 ms (62,2) | 82,7 ms (85,5) | 79,6 ms (80,5) |
| `derive_key` solo, 600.000 iteraciones | — | 54,5 ms | 72,3 ms | 71,6 ms |

- **Comprobación automática:** `tests/test_performance.py` verifica en cada ejecución de la suite que `list` (en el núcleo y como proceso) queda por debajo de 1 s.
- **`create` y `archive`:** se miden en el núcleo, sin el tiempo de tecleo del agente. Los tests de `test_terminal.py` recorren además el flujo completo por terminal con el KDF de producción.
- **Desviación respecto al plan:** el KDF tarda unos 55–72 ms en este equipo, frente a los 0,3–0,5 s que estimaba el plan (D2). La causa son las extensiones SHA-256 del M2 Pro. La cifra de iteraciones sigue siendo la recomendada por OWASP; si se quiere un coste mayor, `kdf.iterations` puede subirse sin migrar los datos.

---

## 6. Conformidad con la constitución

| Principio | Estado | Evidencia |
|---|---|---|
| 1. Stack mínimo | ✅ | `pyproject.toml` declara solo `cryptography>=42`. `pip list` en los entornos limpios muestra únicamente `cryptography` y sus dependencias `cffi` y `pycparser`. El resto es librería estándar (tabla de dependencias del README). |
| 2. Spec antes que código | ⚠️ Con reserva | Todo el código implementa la spec 001 aprobada y no hay funcionalidad fuera de su alcance. Las divergencias de la sección 7 **están documentadas aquí y en `tasks.md`, pero aún no en `plan.md`**, y una de ellas (D-5) toca RF-7.4 de la spec. |
| 3. Núcleo aislado | ✅ | `grep -rnE "import (argparse\|sys)\|from (argparse\|sys)\|print\(\|input\(" mi6/core` no devuelve nada. `LayerBoundaryTest.test_core_has_no_terminal_access_or_cli_imports` también lo comprueba en cada ejecución, incluido que `core` no importa `mi6.cli`. |
| 4. Tests obligatorios | ✅ | Las 385 pruebas pasan con `unittest`. Cada función pública de `mi6/core/` aparece en al menos un test (comprobación automatizada del 2026-10-26). Ningún test usa la red ni el `~/.mi6` real: `MI6TestCase` aísla `HOME` y `storage.resolve_data_dir` falla si se llama. |
| 5. Persistencia local y segura | ✅ | Los datos van solo a `~/.mi6`, en JSON, con 0700/0600 y escritura atómica (`test_storage`). Los informes están cifrados (criterios 4 y 5). El repositorio no contiene ninguna clave, y `.gitignore` excluye `.mi6/`, `*.key`, `*.pem` y `.env*`. |
| 6. Idioma | ✅ | Los identificadores, comentarios y valores del JSON están en inglés; el código fuente de `mi6/core` es solo ASCII. Los textos para el agente están en español y solo en `mi6/cli/messages.py` (criterio 6). |

---

## 7. Divergencias respecto al plan y a las tareas

Son decisiones tomadas durante la implementación. **Deben incorporarse a `plan.md`** (y D-5 a la spec) para cerrar del todo el principio 2.

| ID | Divergencia | Motivo | Documento que hay que actualizar |
|---|---|---|---|
| D-1 | **Tests en `tests/` plano**, no en `tests/core/` y `tests/cli/`. La clase base es `tests/test_base.py::MI6TestCase` (el plan dice `tests/helpers.py::Mi6TestCase`). Los tests previstos en `test_edge_cases.py`, `test_acceptance.py`, `test_main.py`, `test_messages.py`, `test_prompts.py` y `test_render.py` están dentro de `test_cli.py` y `test_crypto.py`. Se añadieron `test_schema.py` y `test_terminal.py`. | Petición explícita del responsable del proyecto. | plan §1 y §6.4 |
| D-2 | **Nombres de funciones de la CLI:** `prompt_password` (plan: `read_password`), `read_report_body` (`read_report`), `sanitize_output` (`sanitize`), `format_mission_list` (`mission_table` + `empty_list`) y la función nueva `print_safe`. | Petición explícita. | plan §4, tasks T31–T35 |
| D-3 | Se acepta `--name` como alias de `--code-name`. | Petición explícita; no rompe el contrato del plan. | plan §4.1 |
| D-4 | **Vuelta atrás del primer uso:** si la primera escritura no se completa, `~/.mi6` se elimina (`storage.discard_uninitialized_data_dir`). | Sin ella, un Ctrl+C durante la derivación de la clave de la primera misión dejaría `~/.mi6` sin `missions.json`, y RF-6.7 lo trataría como corrupto para siempre. | plan §2.5 |
| D-5 | **Ctrl+D al pedir la contraseña** termina con 130 y `ABORTED_BY_AGENT`. | `getpass` lanza `EOFError`. Se trata como cancelación del agente; antes salía como «fallo inesperado» con código 3. | **spec RF-7.4** (decisión de producto pendiente) |
| D-6 | Mensajes adicionales: `ERR_OWNER`, `ERR_VALIDATION`, `UNKNOWN_PATH`, las columnas `LIST_COLUMN_*` y las tablas de traducción (`VALIDATION_MESSAGES`, `ERRNO_REASONS`…). | `ERR_PERMISSIONS` no sirve cuando el problema es el propietario (no se arregla con `chmod`), y `ERR_DATA_ACCESS` necesita la causa en español. | plan §4.6 |
| D-7 | `crypto` exige **Base64 canónico** antes de descifrar. | **Defecto encontrado en esta verificación:** en Python 3.11, un token con datos añadidos después del relleno se aceptaba, y en 3.13 no. Ahora se rechaza en todas las versiones (`test_trailing_data_after_padding_is_rejected_on_every_python`). | plan §2.4 |
| D-8 | `render.sanitize_output` sustituye también `Cs`, `Co`, `Cn`, `Zl` y `Zp`, además de `Cc` y `Cf`. | Es más estricto que el plan y evita errores de codificación y saltos de línea falsos. | plan §4.5 |
| D-9 | `storage.read_document` rechaza claves JSON duplicadas y `NaN`/`Infinity`. | Un JSON con un agente repetido perdería datos en silencio. | plan §2.3 |
| D-10 | API pública adicional del núcleo: `storage.file_lock`, `data_dir_exists`, `missions_path`, `lock_path` y `discard_uninitialized_data_dir`; `crypto.encode_salt` y `decode_salt`; `schema.is_fernet_token`. `preflight_create` devuelve los valores limpios. | Lo necesitan las operaciones y los tests. Todas estas funciones tienen tests. | plan §1 |

### Defectos encontrados y corregidos durante la verificación

1. **Diferencia entre versiones de Python en el descifrado** (D-7). Solo se detectó al ejecutar la suite en Linux con Python 3.11. En macOS solo hay 3.14.
2. **`EOFError` tratado como fallo inesperado** (D-5). Se detectó con `test_cli.InterruptTest.test_ctrl_d_at_password_prompt`.
3. **Requisitos sin tarea asignada:** RF-1.3, RF-2.8 y RNF-3 no aparecían en ninguna línea «Cubre» de `tasks.md`. Se ha añadido la cobertura en la tabla de `tasks.md` y un test específico para RNF-3.

---

## 8. Límites de esta verificación

- **Windows:** fuera de alcance (spec, sección 7; RNF-5). No se ha probado y no funciona, porque usa `fcntl` y `/dev/tty`.
- **macOS:**
  - Solo se ha probado en un equipo (Apple M2 Pro, macOS 27.0) y con **Python 3.14.6**, la única versión instalada.
  - La compatibilidad con 3.11 está verificada solo en Linux.
- **Linux:**
  - Solo se ha probado en **contenedores Docker** (Debian 13, aarch64, kernel `linuxkit` 6.12) sobre el mismo equipo.
  - No se ha probado en x86_64, en otras distribuciones ni en una máquina Linux física.
  - El sistema de archivos del contenedor es `overlayfs`; no se ha probado `ext4` ni `btrfs` directamente.
- **Python 3.12:** no se ha probado. Sí 3.11, 3.13 y 3.14.
- **Terminal:**
  - Los tests de `test_terminal.py` usan un **pseudo-terminal real** (`pty`), con `getpass`, eco, Ctrl+D y SIGINT reales.
  - No se ha probado a mano con emuladores de terminal concretos (Terminal.app, iTerm2, GNOME Terminal) ni por SSH.
- **Concurrencia:**
  - Se ha verificado con `flock` real entre descriptores del mismo proceso y entre procesos.
  - **No** se ha probado sobre NFS, que no está soportado (plan D4).
  - Queda una ventana de microsegundos entre crear `missions.lock` y tomar el bloqueo en el **primer uso**. Si dos ejecuciones simultáneas caen en ella, la segunda recibe «expediente dañado» en lugar de «operación en curso», sin pérdida de datos. Se acepta.
- **Durabilidad:** se llama a `fsync` del archivo y de la carpeta. No se ha simulado un corte de luz real. Si falla el `fsync` de la carpeta **después** de `os.replace`, se informa de un error aunque el expediente nuevo ya esté escrito.
- **Rendimiento:** son medidas de un solo equipo (sección 5). En hardware más lento el KDF será más lento, aunque hay más de 20 veces de margen respecto al límite de 2 s.
- **Caso abierto de la spec:** un informe formado solo por U+200D (ZWJ) **se acepta**, porque RF-3.9 solo rechaza los informes que son solo espacios. Está documentado en `test_validation.NormalizeReportTest.test_zwj_only_report_is_accepted_per_current_spec`. Si debe rechazarse, primero hay que cambiar la spec.
- **Fuera de alcance de la verificación:** auditoría criptográfica externa, análisis estático de seguridad y pruebas de fuzzing.

---

## 9. Cómo reproducir esta verificación

```bash
# macOS o Linux, con usuario normal (no root)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -t .

# Linux con Python 3.11 desde macOS, con Docker
docker run --rm -v "$PWD":/src:ro --user 1000:1000 -e HOME=/tmp/h python:3.11-slim sh -c '
  mkdir -p /tmp/h /tmp/w && chmod 700 /tmp/h
  tar -C /src --exclude=.venv --exclude=.git -cf - . | tar -C /tmp/w -xf -
  cd /tmp/w && python -m venv /tmp/v && /tmp/v/bin/pip install -q -e . &&
  /tmp/v/bin/python -m unittest discover -s tests -t .'
```
