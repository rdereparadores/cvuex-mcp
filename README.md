# cvuex-mcp

Servidor MCP para el Campus Virtual de la Universidad de Extremadura, centrado en el alumnado: trabaja con **AVUEx** (aulas regladas). Usa la sesión del propio alumno mediante el mismo inicio de sesión SSO que la app oficial de Moodle: la contraseña nunca pasa por este programa.

Estado: F0 completada (login + comprobación de sesión); F1 en curso. Ver [PLAN.md](PLAN.md) y [FASE1.md](FASE1.md).

## Instalación

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run playwright install chromium   # navegador para el login (una sola vez)
```

## Uso

```bash
uv run cvuex-mcp login     # abre el navegador: inicia sesión con tu cuenta UEx
uv run cvuex-mcp whoami    # comprueba la sesión (--functions lista la API disponible)
uv run cvuex-mcp logout    # borra la sesión de este equipo
```

Las credenciales se guardan en `credentials.json` dentro de la carpeta de configuración del usuario (`~/.config/cvuex-mcp` en Linux, `~/Library/Application Support/cvuex-mcp` en macOS, `%LOCALAPPDATA%\cvuex-mcp` en Windows). Se puede cambiar con `CVUEX_MCP_HOME`. **El token da acceso a tu cuenta: no compartas ese fichero.**

## Conectarlo a un cliente MCP

Claude Code:

```bash
claude mcp add cvuex -- uv --directory /ruta/a/cvuex-mcp run cvuex-mcp serve
```

Otros clientes (Claude Desktop, etc.): comando `uv`, argumentos `["--directory", "/ruta/a/cvuex-mcp", "run", "cvuex-mcp", "serve"]`.

## Desarrollo

```bash
uv run pytest            # tests (los marcados "browser" usan Chromium)
uv run ruff check . && uv run ruff format .
```
