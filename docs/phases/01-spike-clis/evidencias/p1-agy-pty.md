# Antigravity CLI en ConPTY (P1–P3)

argv: `agy --model gemini-3.8-flash-low -i Responde solo con la palabra UNO` · cwd: sandbox · ventana 120×40

## Diálogo de confianza en la carpeta (t=6.1s)

```text
Accessing workspace:

C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\agy-pty-20261009-201032

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit

  ↑/↓ Navigate · enter Confirm
                                                                                                  Gemini 3.8 Flash · low
```

## a) Respuesta al prompt inicial ✅ (t=21.2s)

```text
Accessing workspace:

C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\agy-pty-20261009-201032

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit

  ↑/↓ Navigate · enter Confirm
                                                                                                  Gemini 3.8 Flash · low
1u

      ▄▀▀▄        Antigravity CLI 1.3.2
     ▀▀▀▀▀▀       usuario@example.com (Google AI Pro)
    ▀▀▀▀▀▀▀▀      Gemini 3.8 Flash (Low)
   ▄▀▀    ▀▀▄     ~/AppData/Local/AgenticOS-spike/sandbox/agy-pty-20261009-201032
  ▄▀▀      ▀▀▄

────────────────────────────────────────────────────────────
> Responde solo con la palabra UNO

  UNO

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## b) Segundo prompt escrito desde fuera ✅ (t=27.0s)

```text
Accessing workspace:

C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\agy-pty-20261009-201032

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit

  ↑/↓ Navigate · enter Confirm
                                                                                                  Gemini 3.8 Flash · low
1u

      ▄▀▀▄        Antigravity CLI 1.3.2
     ▀▀▀▀▀▀       usuario@example.com (Google AI Pro)
    ▀▀▀▀▀▀▀▀      Gemini 3.8 Flash (Low)
   ▄▀▀    ▀▀▄     ~/AppData/Local/AgenticOS-spike/sandbox/agy-pty-20261009-201032
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

## c1) Turno largo en curso (antes de Esc) (t=30.8s)

```text
  56
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
⡿  Working...
└ Tip: Press ? to see keyboard shortcuts.
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────
```

## c2) Tras pulsar Esc (t=33.8s)

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

  ⎿  Interrupted · What should Antigravity CLI do instead?
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## c3) ¿La sesión sigue viva y responde tras Esc? ✅ (t=39.4s)

```text
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

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                                                   Gemini 3.8 Flash · low
```

## e) Tras redimensionar a 90×30 (t=41.4s)

```text
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

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

──────────────────────────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                                     Gemini 3.8 Flash · low
```

## d1) Tras un Ctrl+C (sin turno en curso) ✅ (t=42.9s)

```text
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

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

──────────────────────────────────────────────────────────────────────────────────────────
>
──────────────────────────────────────────────────────────────────────────────────────────
press ctrl+c again to exit                                          Gemini 3.8 Flash · low
```

## d2) Tras un segundo Ctrl+C ✅ (t=44.1s)

```text
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

────────────────────────────────────────────────────────────
> Responde solo con la palabra TRES

  TRES

──────────────────────────────────────────────────────────────────────────────────────────
> 1u
──────────────────────────────────────────────────────────────────────────────────────────

Resume with -c (or command below):
agy --conversation=d47e4962-f9c6-4660-a075-a3e323b35d83
```

Proceso vivo al final: False

Configuración global: changed: C:\Users\usuario\.gemini\antigravity-cli\history.jsonl
+{"display":"Responde solo con la palabra DOS","timestamp":1791569454126,"workspace":"C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\agy-pty-20261009-201032","conversationId":"d47e4962-f9c6-4660-a075-a3e323b35d83"}
+{"display":"Escribe los números del 1 al 300, uno por línea, sin ningún otro texto","timestamp":1791569459955,"workspace":"C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\agy-pty-20261009-201032","conversationId":"d47e4962-f9c6-4660-a075-a3e323b35d83"}
+{"display":"Responde solo con la palabra TRES","timestamp":1791569466798,"workspace":"C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\agy-pty-20261009-201032","conversationId":"d47e4962-f9c6-4660-a075-a3e323b35d83"}
changed: C:\Users\usuario\.gemini\antigravity-cli\settings.json
-    "C:\\Users\\usuario"
+    "C:\\Users\\usuario",
+    "C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\agy-pty-20261009-201032"
