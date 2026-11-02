# Seguridad

## Avisar de una vulnerabilidad
Si encuentras una vulnerabilidad en Agentic OS, **no abras un issue público**. Escribe a [contacto@cafeconpalito.com](mailto:contacto@cafeconpalito.com) con:
- qué versión usas (Ajustes › Acerca de);
- qué has encontrado y cómo reproducirlo;
- qué impacto crees que tiene.

Responderemos en cuanto podamos. Cuando la corrección esté publicada, el problema se puede contar en público, con tu nombre si quieres.

*To report a vulnerability, please e-mail the address above instead of opening a public issue.*

## Versiones con soporte
Solo la última versión publicada en [Releases](https://github.com/CafeConPalito/AgenticOS/releases) recibe correcciones.

## Qué hace la app con tus datos
- Todo corre en tu equipo. No hay telemetría ni se envía nada sin que tú lo hagas.
- Los secretos de las conexiones MCP van al almacén de credenciales de Windows.
- Los agentes son los CLIs que tú instalas (Claude Code, Antigravity CLI…), con tus cuentas y sus propias políticas de datos.
