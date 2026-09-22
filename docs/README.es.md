# AIMarket Playground

[English](../README.md) · [Русский](README.ru.md) · **Español** · [Français](README.fr.md) · [中文](README.zh.md) · [Glosario](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

Una entrada sin configuración a una ruta real: **invocación (invoke) de GAIA → verificación de Metis → recibo firmado de Hub**.

## Propósito

El Playground ejecuta un solo flujo incluido en la allowlist. No ejecuta código arbitrario enviado
por el navegador. El panel de código explica la ruta HTTP real y el servidor realiza una solicitud
acotada sin entregar secretos de infraestructura al navegador.

```text
navegador → AIMarket Playground → Hub → GAIA → Metis → recibo verificado → Alien Monitor
```

GAIA devuelve una lectura LIVE. El recibo se verifica con Ed25519 y la clave pública del Hub de
origen; la mera presencia de `signature` no cuenta como verificación. La lectura y el recibo
verificado aparecen primero; Metis continúa la verificación de forma asíncrona con un temporizador
visible. Si Metis no está disponible, el resultado muestra `PARTIAL`, nunca un `VERIFIED` falso.
Por defecto, Playground envía a Metis una tarea explícita de coherencia interna mediante la ruta
`fast`; `/v1/verify` sigue ejecutando un verificador real. El Council/MoA completo no se usa para una
lectura ordinaria. Una respuesta sin `verify_performed: true` se muestra como **no comprobada**, no
como un veredicto real con puntuación cero; los despliegues antiguos o mal configurados fallan de
forma cerrada.
El flag `verified` de Metis significa que su propia evaluación pasó el verificador, no que la lectura
de GAIA superara automáticamente la comprobación de plausibilidad. Playground muestra `VERIFIED`
solo si esa evaluación contiene `VERDICT: plausible` y el recibo de Hub está verificado; una
evaluación no plausible o no estructurada permanece `PARTIAL`.
Para un Metis de producción autenticado, configura `PLAYGROUND_METIS_KEY` solo en el servidor; el navegador nunca lo recibe.
El límite del servidor Metis es de 600 segundos, el límite externo de Playground es de 620 segundos
y el presupuesto total es de 640 segundos. Cada tipo de finalización se muestra
por separado.

## Ejecución local

```bash
uv sync --extra dev
uv run pytest
uv run uvicorn playground.app:app --host 127.0.0.1 --port 8075
```

Abre <http://127.0.0.1:8075/?lang=es>.

## Docker

```bash
docker compose up --build
```

Compose publica el puerto solo en `127.0.0.1`, usa un filesystem de solo lectura, elimina Linux
capabilities, limita los procesos, incorpora un health check y activa `no-new-privileges`. Un
despliegue público necesita un reverse proxy HTTPS con rate limit externo.

## Configuración y seguridad

Parte de `.env.example`. Las URL de Hub, GAIA y Metis deben usar HTTPS de forma predeterminada.
`PLAYGROUND_EVENT_URL` exige `PLAYGROUND_EVENT_TOKEN`. Las variables `PLAYGROUND_MAX_*` acotan uso,
concurrencia, respuestas upstream e historial. Los límites se aplican tanto al visitante seudónimo
como al origen de red, por lo que cambiar el browser visitor ID no elude la protección del presupuesto.
El recibo verificado criptográficamente también debe coincidir con `product_id`, `capability_id` y
una invocación (invoke) correcta.

## Límite del producto

Use Cases Portal presenta oportunidades y el mapa del ecosistema. El Playground activa al
desarrollador con una invocación real. `create-aimarket-agent` crea un repositorio bajo su control.
Son etapas conectadas, no portales duplicados.

Los términos `lectura`, `recibo`, `verificación` y `rails` siguen el glosario canónico. Marcas,
código, identificadores, comandos CLI, env vars, URL, `LIVE` y `SIM` no se traducen.

## Licencia

MIT — consulta [LICENSE](../LICENSE).
