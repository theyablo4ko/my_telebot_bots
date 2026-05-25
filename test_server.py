import asyncio
import json
import logging
import os
from aiohttp import web, WSMsgType

# Логирование всех запросов
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Хранилище активных WebSocket-соединений (для опциональной мульти-игры)
connected_clients = set()

async def echo_websocket_handler(request):
    """Принимает WebSocket-соединение и отправляет обратно все полученные сообщения."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    logger.info(f"WebSocket connection established from {request.remote}")
    connected_clients.add(ws)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                logger.info(f"Received: {msg.data}")
                # Отправляем обратно то же сообщение
                await ws.send_str(msg.data)
                logger.info(f"Echo sent: {msg.data}")
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"Exception in echo handler: {e}")
    finally:
        connected_clients.discard(ws)
        logger.info("WebSocket connection closed")

    return ws

async def health_check(request):
    """Health check endpoint для Render."""
    logger.info(f"Health check from {request.remote}")
    return web.Response(text="OK")

# Middleware для логирования всех HTTP-запросов
@web.middleware
async def log_middleware(request, handler):
    logger.info(f"HTTP {request.method} {request.path} from {request.remote}")
    return await handler(request)

# Создаём приложение
app = web.Application(middlewares=[log_middleware])
app.router.add_get('/healthz', health_check)
app.router.add_get('/ws', echo_websocket_handler)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    logger.info(f"Starting echo server on port {port}")
    web.run_app(app, host='0.0.0.0', port=port)
