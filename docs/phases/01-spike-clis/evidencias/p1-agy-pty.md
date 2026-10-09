# Antigravity CLI en ConPTY (P1–P3)

argv: `agy --model gemini-3.8-flash-low -i Responde solo con la palabra UNO` · cwd: sandbox · ventana 120×40

## Diálogo de confianza en la carpeta (t=3.5s)

```text
Accessing workspace:

C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\agy-pty-20261009-192831

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit

  ↑/↓ Navigate · enter Confirm
```

## a) Respuesta al prompt inicial ✅ (t=18.5s)

```text
Accessing workspace:

C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\agy-pty-20261009-192831

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit


      ▄▀▀▄        Antigravity CLI 1.3.2
     ▀▀▀▀▀▀       usuario@example.com (Google AI Pro)
    ▀▀▀▀▀▀▀▀      Gemini 3.8 Flash (Low)
   ▄▀▀    ▀▀▄     ~/AppData/Local/AgenticOS-spike/sandbox/agy-pty-20261009-192831
  ▄▀▀      ▀▀▄

────────────────────────────────────────────────────────────
> Responde solo con la palabra UNO

  UNO

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## b) Segundo prompt escrito desde fuera ✅ (t=24.1s)

```text
Accessing workspace:

C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\agy-pty-20261009-192831

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit


      ▄▀▀▄        Antigravity CLI 1.3.2
     ▀▀▀▀▀▀       usuario@example.com (Google AI Pro)
    ▀▀▀▀▀▀▀▀      Gemini 3.8 Flash (Low)
   ▄▀▀    ▀▀▄     ~/AppData/Local/AgenticOS-spike/sandbox/agy-pty-20261009-192831
  ▄▀▀      ▀▀▄

────────────────────────────────────────────────────────────
> Responde solo con la palabra UNO

  UNO

────────────────────────────────────────────────────────────
> Responde solo con la palabra DOS

  DOS

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## c1) Turno largo en curso (antes de Esc) (t=27.7s)

```text
  57
  58
  59
  60
  61
  62
  63
  64
  65
  66
  67
  68
  69
  70
  71
  72
  73
  74
  75
  76
  77
  78
  79
  80
  81
  82
  83
  84
  85
  86
  87
  88
  89
  9
⡿  Generating...
└ Tip: View and review artifacts with /artifact.
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
esc to cancel                                                                                     Gemini 3.8 Flash · low
```

## c2) Tras pulsar Esc (t=30.7s)

```text
  65
  66
  67
  68
  69
  70
  71
  72
  73
  74
  75
  76
  77
  78
  79
  80
  81
  82
  83
  84
  85
  86
  87
  88
  89
  90
  91
  92
  93
  94
  95
  96
  97
  9

  ⎿  Interrupted · What should Antigravity CLI do instead?
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## c3) ¿La sesión sigue viva y responde tras Esc? ✅ (t=36.0s)

```text
  69
  70
  71
  72
  73
  74
  75
  76
  77
  78
  79
  80
  81
  82
  83
  84
  85
  86
  87
  88
  89
  90
  91
  92
  93
  94
  95
  96
  97
  9

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## e) Tras redimensionar a 90×30 (t=38.0s)

```text
  79
  80
  81
  82
  83
  84
  85
  86
  87
  88
  89
  90
  91
  92
  93
  94
  95
  96
  97
  9

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

──────────────────────────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                     Gemini 3.8 Flash · low
```

## d1) Tras un Ctrl+C (sin turno en curso) ✅ (t=39.5s)

```text
  79
  80
  81
  82
  83
  84
  85
  86
  87
  88
  89
  90
  91
  92
  93
  94
  95
  96
  97
  9

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

──────────────────────────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────────────────────────
press ctrl+c again to exit                                          Gemini 3.8 Flash · low
```

## d2) Tras un segundo Ctrl+C ✅ (t=39.9s)

```text
  82
  83
  84
  85
  86
  87
  88
  89
  90
  91
  92
  93
  94
  95
  96
  97
  9

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

──────────────────────────────────────────────────────────────────────────────────────────
> 1u
──────────────────────────────────────────────────────────────────────────────────────────

Resume with -c (or command below):
agy --conversation=6e56e344-26fc-4cbc-9c66-e8f3ffb44dbc
```

Proceso vivo al final: False

Configuración global: added: C:\Users\usuario\.gemini\antigravity-cli\history.jsonl
changed: C:\Users\usuario\.gemini\antigravity-cli\settings.json
-    "C:\\Users\\usuario"
+    "C:\\Users\\usuario",
+    "C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\agy-pty-20261009-192831"
