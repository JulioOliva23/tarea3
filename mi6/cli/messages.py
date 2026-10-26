"""Every text the agent reads, in Spanish with MI6 tone (constitution, principle 6; plan, section 4.6).

This module imports nothing. ``{placeholders}`` are filled by the CLI with
values that have already been sanitized. The lookup tables at the end
translate the data carried by domain exceptions (field and rule, errno name,
reason, status, risk level) into agent-facing text.
"""

# --- Results -----------------------------------------------------------------

CREATE_OK = (
    "Expediente {code_name} registrado, amenaza nivel {threat}. "
    "El informe ha sido cifrado, agente {agent}."
)
LIST_HEADER = "MISIONES ACTIVAS · AGENTE {agent}"
LIST_COLUMN_CODE_NAME = "NOMBRE CLAVE"
LIST_COLUMN_THREAT = "AMENAZA"
LIST_COLUMN_CREATED = "REGISTRO"
LIST_RISK = "RIESGO GLOBAL: {total} · {level}"
LIST_EMPTY = "Sin misiones activas, agente {agent}. Disfrute del martini."
ARCHIVE_PREVIEW = "Va a archivar {code_name} (amenaza {threat}). Introduzca su contraseña para confirmar."
ARCHIVE_OK = "Misión {code_name} archivada. Expediente sellado."

# --- Prompts -----------------------------------------------------------------

REPORT_PROMPT = "Redacte el informe (máx. 500 caracteres). Pulse Ctrl+D en una línea vacía para terminar."
PASSWORD_PROMPT = "Contraseña de campo: "
PASSWORD_NEW = (
    "Primera misión del agente {agent}. "
    "Establezca su contraseña de campo (mínimo 8 caracteres): "
)
PASSWORD_REPEAT = "Repítala para confirmar: "

# --- Rejections (exit code 1) ------------------------------------------------

ERR_AGENT_CODE = "Acceso denegado. El código de agente debe ser 001–009."
ERR_THREAT = "Nivel de amenaza no válido. Use un número del 1 al 5."
ERR_CODE_NAME = "Nombre clave no válido: entre 1 y 30 caracteres, solo letras sin tilde, dígitos y guiones."
ERR_REPORT_EMPTY = "El informe está vacío. Q no acepta expedientes en blanco."
ERR_REPORT_LENGTH = "El informe supera los 500 caracteres ({length}). Sea más conciso, agente."
ERR_REPORT_CHARS = "El informe contiene caracteres de control no permitidos."
ERR_REPORT_ENCODING = "El informe no es texto UTF-8 válido."
ERR_PASSWORD_SHORT = "La contraseña debe tener al menos 8 caracteres. Registro cancelado."
ERR_PASSWORD_MISMATCH = "Las contraseñas no coinciden. Registro cancelado."
ERR_VALIDATION = "Dato no válido en {field}. Revise el formato, agente."
ERR_AUTH = "Acceso denegado: contraseña incorrecta. No se ha modificado nada."
ERR_DUPLICATE = "Ya existe una misión {code_name} ({status_es}) a su nombre."
ERR_NOT_FOUND = "La misión {code_name} no está entre sus misiones activas."

# --- CLI usage (exit code 2) -------------------------------------------------

ERR_USAGE = "Orden no reconocida o incompleta."
ERR_NO_TERMINAL = "Se requiere una terminal interactiva para introducir la contraseña."

# --- Data and environment failures (exit code 3) -----------------------------

ERR_DATA_ACCESS = "No se puede acceder al expediente local ({path}): {reason}."
ERR_PERMISSIONS = "Permisos inseguros en {path} ({current}). Ejecute: chmod {expected} {path}"
ERR_OWNER = "{path} no pertenece a su usuario del sistema. Operación abortada. Contacte con Q-Branch."
ERR_SYMLINK = "{path} es un enlace simbólico. Operación abortada por seguridad."
ERR_CORRUPT = "Expediente dañado o irreconocible ({path}). No se ha tocado nada. Contacte con Q-Branch."
ERR_IN_PROGRESS = "Operación en curso desde otra terminal. Inténtelo de nuevo en unos segundos."
ERR_ROOT = "No ejecute mi6 como root. Operación abortada."
ERR_NO_HOME = "No se encuentra el directorio personal del agente. Operación abortada."
UNEXPECTED = "Fallo inesperado. Operación abortada. Informe a Q-Branch."
UNKNOWN_PATH = "ruta desconocida"

# --- Cancellation (exit code 130) --------------------------------------------

ABORTED_BY_AGENT = "Operación abortada por el agente. Sin cambios."

# --- Help (exit code 0 when asked for, 2 after a usage error) ----------------

HELP = """\
mi6 · Registro operativo de misiones del MI6

Uso:
  mi6 create  --agent CÓDIGO --code-name NOMBRE --threat NIVEL  < informe.txt
  mi6 list    --agent CÓDIGO
  mi6 archive --agent CÓDIGO --code-name NOMBRE
  mi6 --help

Órdenes:
  create   Registra una misión ACTIVA. El informe se lee de la entrada estándar
           o se redacta en la terminal (Ctrl+D para terminar) y queda cifrado
           con su contraseña de campo.
  list     Muestra sus misiones activas y su riesgo global. No pide contraseña.
  archive  Archiva una misión activa. Su contraseña sirve de confirmación.

Opciones:
  -a, --agent CÓDIGO       Código de agente, de 001 a 009.
  -n, --code-name NOMBRE   Nombre clave: de 1 a 30 letras sin tilde, dígitos
                           o guiones. También se acepta --name.
  -t, --threat NIVEL       Nivel de amenaza, del 1 al 5 (solo en create).
  -h, --help               Muestra esta ayuda.

Ejemplos:
  mi6 create -a 007 -n SKYFALL -t 4 < informe.txt
  mi6 list -a 007
  mi6 archive -a 007 -n SKYFALL

Aviso de Q-Branch: no use «echo "..." | mi6 create»; el informe quedaría en
el historial del shell. Redirija desde un archivo o redáctelo en la terminal.

Riesgo global: BAJO (0 a 5), MEDIO (6 a 10), CRÍTICO (11 o más).
Códigos de salida: 0 éxito · 1 rechazo · 2 uso incorrecto o sin terminal ·
3 fallo de datos o de entorno · 130 cancelado por el agente."""

# --- Lookup tables -----------------------------------------------------------

STATUS_LABELS = {
    "active": "ACTIVA",
    "archived": "ARCHIVADA",
}

DUPLICATE_STATUS_LABELS = {
    "active": "activa",
    "archived": "archivada",
}

RISK_LABELS = {
    "low": "BAJO",
    "medium": "MEDIO",
    "critical": "CRÍTICO",
}

# (ValidationError.field, ValidationError.rule) -> message.
VALIDATION_MESSAGES = {
    ("agent_code", "format"): ERR_AGENT_CODE,
    ("threat_level", "range"): ERR_THREAT,
    ("threat_level", "type"): ERR_THREAT,
    ("code_name", "empty"): ERR_CODE_NAME,
    ("code_name", "length"): ERR_CODE_NAME,
    ("code_name", "chars"): ERR_CODE_NAME,
    ("code_name", "type"): ERR_CODE_NAME,
    ("report", "empty"): ERR_REPORT_EMPTY,
    ("report", "length"): ERR_REPORT_LENGTH,
    ("report", "chars"): ERR_REPORT_CHARS,
    ("report", "encoding"): ERR_REPORT_ENCODING,
    ("password", "too_short"): ERR_PASSWORD_SHORT,
    ("password", "mismatch"): ERR_PASSWORD_MISMATCH,
}

FIELD_LABELS = {
    "agent_code": "el código de agente",
    "threat_level": "el nivel de amenaza",
    "code_name": "el nombre clave",
    "report": "el informe",
    "password": "la contraseña",
}

# UnsafeEnvironmentError.reason -> message.
UNSAFE_ENVIRONMENT_MESSAGES = {
    "root": ERR_ROOT,
    "no_home": ERR_NO_HOME,
}

# DataAccessError.os_error_name (symbolic errno) -> reason shown in ERR_DATA_ACCESS.
ERRNO_REASONS = {
    "EACCES": "permiso denegado",
    "EPERM": "operación no permitida por el sistema",
    "ENOSPC": "no queda espacio en el disco",
    "EDQUOT": "cuota de disco agotada",
    "EROFS": "el sistema de archivos es de solo lectura",
    "ENOENT": "la ruta no existe",
    "ENOTDIR": "la ruta no es una carpeta",
    "EISDIR": "se esperaba un archivo y hay una carpeta",
    "EIO": "error de entrada/salida del disco",
    "EMFILE": "demasiados archivos abiertos por el proceso",
    "ENFILE": "demasiados archivos abiertos en el sistema",
    "ELOOP": "demasiados enlaces simbólicos en la ruta",
    "ENAMETOOLONG": "la ruta es demasiado larga",
    "EBUSY": "el recurso está ocupado",
    "EXDEV": "la operación cruza sistemas de archivos",
    "ENOLCK": "el sistema no admite más bloqueos",
    "ENXIO": "el dispositivo no está disponible",
    "EAGAIN": "recurso temporalmente no disponible",
}
ERRNO_UNKNOWN = "error del sistema {name}"
