# Constitución de mi6-cli

Seis principios innegociables. Un cambio que incumpla alguno no se integra.

1. **Stack mínimo:** Python 3.11+ y librería estándar. La única dependencia externa permitida es `cryptography`, y cualquier otra necesita justificación escrita en la spec y aprobación previa.
2. **Spec antes que código:** ninguna funcionalidad se implementa sin una spec en `specs/`. Si el código y la spec no coinciden, primero se actualiza la spec y después el código.
3. **Núcleo aislado de la terminal:** `mi6/core/` no importa `argparse` ni `sys`, y no usa `print()` ni `input()`. `mi6/cli/` solo lee los argumentos, llama al núcleo y da formato a la salida.
4. **Tests obligatorios:** cada función pública de `mi6/core/` tiene al menos un test con `unittest`. `python -m unittest` debe pasar antes de cada commit. Los tests no usan la red ni el directorio `~/.mi6/` real; trabajan en directorios temporales.
5. **Persistencia local y segura:** los datos se guardan solo en `~/.mi6/`, en JSON, con permisos `0600` y escritura atómica. Las bitácoras se guardan cifradas. Ninguna clave aparece en el código ni en el repositorio.
6. **Idioma:** los identificadores, comentarios y commits van en inglés. Todo lo que lee el agente va en español con tono MI6 y está en `mi6/cli/messages.py`.
