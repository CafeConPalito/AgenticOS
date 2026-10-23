# Phase 16 spike: reproducible Spanish test audio, made with the Windows voice (no licences).
# Writes 16 kHz mono 16-bit WAVs and the reference text next to them.
param([string]$Out = "$PSScriptRoot\samples")

Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force $Out | Out-Null
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.SelectVoice('Microsoft Helena Desktop')
$voice.Rate = 0
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)

function Save($name, $text) {
    $voice.SetOutputToWaveFile("$Out\$name.wav", $format)
    $voice.Speak($text)
    $voice.SetOutputToNull()
    Set-Content -Encoding utf8 "$Out\$name.txt" $text
}

# 1. About a minute of dictation: speed.
$long = @(
    'Necesito que el agente de revisión compruebe la migración de la base de datos antes de fusionar la rama.',
    'La tarea consiste en añadir un botón de micrófono a todos los campos de texto largo de la aplicación.',
    'Cuando el usuario pulse el botón, la aplicación empezará a grabar y mostrará el nivel de audio y el tiempo transcurrido.',
    'Al terminar, el texto se insertará en la posición del cursor sin perder lo que ya estaba escrito.',
    'Hay que tener en cuenta que la transcripción se hace en el propio ordenador, sin enviar el audio a ningún servidor.',
    'Además, el modelo debe cargarse mientras se habla, para que el resultado aparezca en pocos segundos.',
    'Por último, conviene escribir pruebas que cubran los errores más habituales, como la falta de micrófono o de modelo.',
    'Si algo falla, el campo no debe perder el contenido y el mensaje de error tiene que explicar cómo solucionarlo.',
    'También quiero que se pueda cancelar la grabación con la tecla de escape, sin transcribir nada.',
    'Cuando termines, deja un resumen de los cambios en la descripción de la tarea y avísame en la bandeja de entrada.'
) -join ' '
Save 'dictado' $long

# 2. Proper names the model cannot know: vocabulary hint.
Save 'nombres' ('Asigna la tarea al agente Kestrel del proyecto Zafiro, y que Mirlo revise la etapa de Triaje ' +
    'antes de pasar a Cobalto. El equipo Lince usa Celery con Redis para las colas.')

# 3. Silence: hallucination check (10 s of nothing is made in make_noise.py).
$voice.Dispose()
