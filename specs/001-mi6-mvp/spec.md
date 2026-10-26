# Spec 001: MVP operativo de mi6-cli

**Estado:** aprobada · **Fecha:** 2026-10-26 · **Constitución:** `docs/constitution.md`

> Esta spec solo pasa a **aprobada** cuando no le queda ningún [NECESITA ACLARACIÓN]. El plan técnico no empieza antes de esa aprobación.

## 1. Contexto y objetivo operativo

Los agentes de campo del MI6 necesitan llevar un registro local y discreto de sus misiones sin depender de la red ni de los sistemas centrales. Hoy no tienen una forma rápida de saber cuánto riesgo acumulan entre todas sus misiones abiertas, ni de cerrar una misión dejando su informe protegido.

**Objetivo:** que un agente pueda, desde la terminal, (1) registrar un informe de misión con su nivel de amenaza, que queda cifrado desde el primer momento, (2) ver sus misiones activas junto con su riesgo global y (3) archivar una misión concluida para que deje de contar como activa.

## 2. Usuarios

- **Agente de campo:** usuario principal. Registra, consulta y archiva sus propias misiones. Se identifica con su código 00 y protege sus informes con una contraseña personal.
- **Q-Branch:** mantiene la herramienta. Necesita un comportamiento predecible, mensajes de error que expliquen la causa y datos que no se corrompan con un fallo, para poder dar soporte sin ver el contenido de los informes.

## 3. Historias de usuario

- **HU-1:** Como agente de campo, quiero registrar un informe de misión con su nivel de amenaza para dejar constancia de lo que tengo abierto sin que nadie pueda leerlo.
- **HU-2:** Como agente de campo, quiero ver mis misiones activas y mi riesgo global para decidir si puedo aceptar más trabajo.
- **HU-3:** Como agente de campo, quiero archivar una misión concluida para que deje de contar en mi riesgo y quede guardada de forma protegida.
- **HU-4:** Como Q-Branch, quiero que cualquier fallo deje los datos intactos y explique la causa para poder dar soporte sin perder información.

## 4. Requisitos funcionales

### Datos de una misión

Cada misión tiene: código del agente, nombre clave, nivel de amenaza, informe, fecha y hora de registro, y estado (activa o archivada). Solo el informe se guarda cifrado; el resto de los datos queda en claro (ver riesgos aceptados, sección 5.1).

Los textos `ACTIVA`, `ARCHIVADA`, `BAJO`, `MEDIO` y `CRÍTICO` son textos que ve el agente. Esta spec no fija cómo se representan internamente.

### RF-1 Código 00

- **RF-1.1:** El sistema deberá aceptar como código de agente solo los valores `001` a `009`, formados únicamente por dígitos ASCII, después de quitar los espacios del principio y del final.
- **RF-1.2:** Si el código de agente no cumple RF-1.1, entonces el sistema deberá rechazar la operación con un mensaje de acceso denegado que indique el formato esperado, terminar con código de salida 1 y no modificar ningún dato.
- **RF-1.3:** El sistema deberá tratar el código 00 como una etiqueta que separa las misiones de cada agente, no como una prueba de identidad. La identidad se demuestra con la contraseña (RF-2).

### RF-2 Contraseña del agente

- **RF-2.1:** Cuando el sistema necesite la contraseña, deberá pedirla de forma interactiva y sin mostrarla en pantalla.
- **RF-2.2:** El sistema no deberá guardar, mostrar ni registrar la contraseña en ningún sitio.
- **RF-2.3:** Cuando un código registre su primera misión, el sistema deberá pedir la contraseña dos veces y establecerla para ese código solo si ambas coinciden y tiene al menos 8 caracteres.
- **RF-2.4:** Si al establecer la contraseña las dos entradas no coinciden o tiene menos de 8 caracteres, entonces el sistema deberá rechazar el registro, indicar el motivo y no guardar nada.
- **RF-2.5:** Cuando un código que ya tiene contraseña registre o archive una misión, el sistema deberá comprobar que la contraseña introducida es la establecida para ese código.
- **RF-2.6:** Si la contraseña es incorrecta, entonces el sistema deberá rechazar la operación, terminar con código de salida 1 y no modificar ningún dato.
- **RF-2.7:** Si no hay una terminal interactiva para pedir la contraseña, entonces el sistema deberá rechazar la operación y terminar con código de salida 2.
- **RF-2.8:** El sistema no deberá ofrecer ninguna forma de recuperar los informes de un código si se pierde su contraseña.

### RF-3 Registrar un informe de misión (HU-1)

- **RF-3.1:** Cuando el agente registre una misión con un código válido, un nombre clave, un nivel de amenaza, un informe y la contraseña correcta, el sistema deberá guardarla como `ACTIVA` y confirmarlo con un mensaje que incluya el nombre clave.
- **RF-3.2:** El sistema deberá recibir el informe de forma interactiva o por la entrada estándar, nunca como argumento del comando.
- **RF-3.3:** Cuando se guarde una misión, el sistema deberá cifrar su informe con un cifrado autenticado que dependa de la contraseña del agente, de forma que el informe nunca quede en claro en el disco.
- **RF-3.4:** Cuando se registre una misión, el sistema deberá asignarle automáticamente la fecha y hora actuales con su zona horaria. El agente no podrá indicar otra fecha.
- **RF-3.5:** El sistema deberá aceptar como nivel de amenaza solo un único dígito ASCII del 1 al 5, después de quitar los espacios del principio y del final.
- **RF-3.6:** Si el nivel de amenaza no cumple RF-3.5, entonces el sistema deberá rechazar el registro, indicar el rango válido y no guardar nada.
- **RF-3.7:** El sistema deberá aceptar como nombre clave solo de 1 a 30 caracteres entre `A-Z`, `a-z`, `0-9` y `-`, y deberá guardarlo en mayúsculas.
- **RF-3.8:** El sistema deberá aceptar como informe de 1 a 500 caracteres, contados después de normalizar el texto Unicode. Se permiten saltos de línea, tabuladores, tildes, eñes y emojis.
- **RF-3.9:** Si el nombre clave o el informe incumplen RF-3.7 o RF-3.8, contienen caracteres de control no permitidos o solo tienen espacios (incluidos los espacios Unicode), entonces el sistema deberá rechazar el registro, indicar qué campo falla y qué regla incumple, y no guardar nada.
- **RF-3.10:** Si el agente ya tiene una misión con el mismo nombre clave, entonces el sistema deberá rechazar el registro, indicar si esa misión está activa o archivada y no modificar nada.
- **RF-3.11:** Donde dos agentes distintos usen el mismo nombre clave, el sistema deberá tratarlas como misiones independientes.

### RF-4 Listar misiones activas y riesgo global (HU-2)

- **RF-4.1:** Cuando el agente pida su lista de misiones, el sistema deberá mostrarla sin pedir la contraseña.
- **RF-4.2:** Cuando el agente pida su lista de misiones, el sistema deberá mostrar solo sus misiones `ACTIVA`, con nombre clave, nivel de amenaza y fecha y hora de registro en hora local (`AAAA-MM-DD HH:MM`), en el orden en que se registraron.
- **RF-4.3:** Cuando el agente pida su lista de misiones, el sistema deberá mostrar su riesgo global, que es la suma de los niveles de amenaza de sus misiones activas.
- **RF-4.4:** El sistema deberá clasificar el riesgo global como `BAJO` (0 a 5), `MEDIO` (6 a 10) o `CRÍTICO` (11 o más) y mostrar la clasificación junto al valor.
- **RF-4.5:** Si el agente no tiene misiones activas, entonces el sistema deberá indicarlo con un mensaje, mostrar riesgo global 0 (`BAJO`) y terminar con código de salida 0.
- **RF-4.6:** Si todavía no existen datos, entonces el sistema deberá comportarse como en RF-4.5 sin crear nada en el disco.
- **RF-4.7:** El sistema no deberá mostrar el texto de los informes en el listado.
- **RF-4.8:** Cuando el sistema muestre en pantalla cualquier dato guardado, deberá neutralizar los caracteres de control.

### RF-5 Archivar una misión concluida (HU-3)

- **RF-5.1:** Cuando el agente pida archivar una de sus misiones activas por su nombre clave, el sistema deberá mostrar el nombre clave y el nivel de amenaza de esa misión antes de pedir la contraseña. Introducir la contraseña cuenta como confirmación.
- **RF-5.2:** Cuando la contraseña sea correcta, el sistema deberá cambiar el estado de la misión a `ARCHIVADA` y confirmarlo con un mensaje.
- **RF-5.3:** Mientras una misión esté `ARCHIVADA`, el sistema no deberá incluirla en el listado ni en el riesgo global.
- **RF-5.4:** Si el nombre clave no corresponde a ninguna misión activa del agente, entonces el sistema deberá indicar que la misión no está entre sus misiones activas, terminar con código de salida 1 y no modificar ningún dato.
- **RF-5.5:** Si el archivado falla por cualquier motivo, entonces el sistema deberá dejar la misión `ACTIVA` y sin cambios e informar de la causa.

### RF-6 Datos locales y fallos (HU-4)

- **RF-6.1:** Si los datos locales no se pueden leer o escribir (permisos, carpeta inaccesible, disco lleno), entonces el sistema deberá cancelar la operación con un mensaje que explique la causa, terminar con código de salida 3 y dejar los datos existentes sin modificar.
- **RF-6.2:** Si la carpeta de datos o los datos tienen cualquier permiso de lectura, escritura o ejecución para el grupo o para otros usuarios, entonces el sistema deberá cancelar la operación con código de salida 3 e indicar exactamente qué hay que corregir, sin corregir los permisos por su cuenta.
- **RF-6.3:** Si la ruta de los datos contiene un enlace simbólico, entonces el sistema deberá cancelar la operación con código de salida 3.
- **RF-6.4:** El sistema deberá considerar corruptos los datos que no se puedan interpretar, que tengan un formato o una versión que no reconoce, o que contengan algún registro que incumpla las reglas de esta spec (código, nombre clave, amenaza, estado o fecha inválidos, o nombres clave duplicados para un mismo agente).
- **RF-6.5:** Si los datos están corruptos, entonces el sistema deberá cancelar la operación con código de salida 3 sin sobrescribirlos e indicar que Q-Branch debe revisarlos.
- **RF-6.6:** Cuando se registre la primera misión y no exista ningún dato previo, el sistema deberá crear los datos accesibles solo para el usuario actual del sistema.
- **RF-6.7:** Si existen restos de datos incompletos, entonces el sistema deberá tratarlos como corruptos (RF-6.5), no como un primer uso.
- **RF-6.8:** Si otra ejecución está modificando los datos, entonces el sistema deberá cancelar la operación al momento con el mensaje "operación en curso", terminar con código de salida 3 y no modificar nada.
- **RF-6.9:** Si no se puede determinar el directorio personal del usuario o la CLI se ejecuta como root, entonces el sistema deberá cancelar la operación con código de salida 3.

### RF-7 Interfaz de terminal

- **RF-7.1:** Si el comando no existe o faltan o sobran argumentos, entonces el sistema deberá mostrar la ayuda en español y terminar con código de salida 2.
- **RF-7.2:** Cuando el agente pida la ayuda de forma explícita, el sistema deberá mostrarla y terminar con código de salida 0.
- **RF-7.3:** Si el agente cancela con Ctrl+C en cualquier momento, entonces el sistema deberá cancelar la operación sin cambios en los datos, mostrar un mensaje y terminar con código de salida 130.
- **RF-7.4:** El sistema deberá usar estos códigos de salida:

  | Código | Significado |
  |---|---|
  | 0 | Éxito |
  | 1 | Rechazo por validación o por una regla de negocio |
  | 2 | Uso incorrecto de la CLI o falta de terminal interactiva |
  | 3 | Fallo de datos, de permisos o de entorno |
  | 130 | Cancelación con Ctrl+C |

- **RF-7.5:** Cuando el sistema rechace una operación, el mensaje deberá indicar qué regla se ha incumplido.
- **RF-7.6:** Si la salida no admite UTF-8, entonces el sistema deberá sustituir los caracteres que no pueda representar en lugar de fallar.

## 5. Requisitos no funcionales

- **RNF-1 Seguridad:** los informes nunca se guardan en claro. El cifrado es autenticado: una contraseña incorrecta o un contenido manipulado se detecta. Ningún secreto aparece en el código ni en el repositorio.
- **RNF-2 Integridad:** una operación interrumpida (error, Ctrl+C, cierre forzado) nunca deja los datos a medio escribir. O se completa entera o no cambia nada.
- **RNF-3 Sin red:** ninguna operación necesita conexión a la red.
- **RNF-4 Idioma:** todo lo que ve el agente (confirmaciones, errores, ayuda, listados) está en español con tono MI6.
- **RNF-5 Plataformas:** el MVP funciona en macOS y Linux.
- **RNF-6 Rendimiento:** con 1.000 misiones guardadas en total, en un equipo de desarrollo normal y medido desde que se lanza el comando, listar tarda menos de 1 segundo, y registrar y archivar menos de 2 segundos. Obtener el secreto a partir de la contraseña es lento a propósito.
- **RNF-7 Mantenibilidad:** cada requisito funcional se puede verificar con tests automáticos reproducibles en macOS y Linux que no usan los datos reales del agente, incluidos los casos de permisos y de enlaces simbólicos.

### 5.1 Riesgos aceptados

- **Datos en claro:** el código, el nombre clave, la amenaza, la fecha y el estado se guardan sin cifrar, para poder listar y calcular el riesgo sin contraseña y detectar duplicados. Cualquiera con acceso al usuario del sistema puede leerlos.
- **Contraseña perdida:** si un agente pierde su contraseña, sus informes no se pueden recuperar.
- **Código sin autenticar:** cualquiera con acceso al usuario del sistema puede listar las misiones de cualquier código, pero no registrar ni archivar sin la contraseña.

## 6. Casos límite

- Código `000`, `0007`, `07`, `00A`, `００７` o vacío: se rechaza (RF-1.2). ` 007 ` se acepta (RF-1.1).
- Amenaza `0`, `6`, `03`, `+3`, `3.0`, `-1`, `٣` o `tres`: se rechaza (RF-3.6).
- Nombre clave con `../`, `/`, espacios, tildes, letras cirílicas, caracteres invisibles, secuencias de escape o más de 30 caracteres: se rechaza (RF-3.9).
- `skyfall` y `SKYFALL`: son el mismo nombre clave (RF-3.7) y el segundo se rechaza como duplicado (RF-3.10).
- Nombre clave repetido por el mismo agente con la misión anterior archivada: se rechaza y el mensaje indica "archivada" (RF-3.10).
- Informe vacío, con solo espacios Unicode, con caracteres de control o de 501 caracteres: se rechaza (RF-3.9). Con saltos de línea, tildes, eñes o emojis: se acepta.
- Primera contraseña de 7 caracteres o con una confirmación distinta: se rechaza (RF-2.4).
- Contraseña incorrecta al registrar o archivar: se rechaza sin cambios (RF-2.6).
- Ejecución sin terminal interactiva: se rechaza con código 2 (RF-2.7).
- Archivar dos veces la misma misión o una que no existe: se rechaza (RF-5.4).
- Agente sin misiones activas, o sin ningún dato todavía: riesgo 0 `BAJO` y no se crea nada (RF-4.5 y RF-4.6).
- Riesgo exactamente en los límites: 5 → `BAJO`, 6 → `MEDIO`, 10 → `MEDIO`, 11 → `CRÍTICO`.
- Dos misiones registradas en el mismo minuto: se listan en el orden en que se registraron (RF-4.2).
- Reloj del sistema atrasado, adelantado o con cambio de zona horaria: no bloquea nada y no altera el orden (RF-4.2).
- Datos con permisos abiertos o detrás de un enlace simbólico: se cancela (RF-6.2 y RF-6.3).
- Datos corruptos, editados a mano, con un informe cifrado dañado o de una versión desconocida: se cancela (RF-6.5).
- Restos de datos incompletos: se tratan como corruptos (RF-6.7).
- Dos ejecuciones a la vez: la segunda se cancela (RF-6.8).
- Ejecución como root o sin directorio personal: se cancela (RF-6.9).
- Ctrl+C en mitad de una operación o al pedir la contraseña: se cancela sin cambios (RF-7.3).
- Salida redirigida a un archivo o terminal sin UTF-8: no falla (RF-7.6).

## 7. Fuera de alcance

- Consultar el nivel de autorización (Clearance Level). Irá en una spec posterior.
- Descifrar o leer el informe de una misión, activa o archivada.
- Listar las misiones archivadas.
- Editar o borrar misiones, activas o archivadas.
- Cambiar o recuperar la contraseña de un código.
- Windows.
- Red, sincronización y exportación de datos.

## 8. Criterios de finalización

- Esta spec está en estado **aprobada**, sin ningún [NECESITA ACLARACIÓN].
- Todos los criterios de aceptación de RF-1 a RF-7 están cubiertos por tests automáticos que pasan en macOS y Linux.
- Todos los casos límite de la sección 6 tienen al menos un test.
- Un test demuestra que ningún informe aparece en claro en los datos guardados.
- Un test demuestra que un informe se puede descifrar con la contraseña correcta y que falla con una incorrecta o con el contenido manipulado.
- Todos los mensajes al agente están en español.
- La implementación cumple los seis principios de `docs/constitution.md`.

## 9. Dudas abiertas

Ninguna. La última, sobre editar o borrar misiones activas, se resolvió el 2026-10-26: queda fuera de alcance (sección 7).
