import asyncio
import websockets

async def echo(websocket, path):
  async for message in websocket:
    print(f"Получено сообщение: {message}")
    await websocket.send(f"Эхо: {message}")

async def main():
  server = await websockets.serve(echo, "", 8765)
  print("Сервер запущен на ws://localhost:8765", server)
  await server.wait_closed()

if name == "main":
  asyncio.run(main())
