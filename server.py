import asyncio
import json
import os
import random
import websockets
from http import HTTPStatus

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

# ---------- Игра (вся логика без изменений) ----------
class BlackjackGame:
    def __init__(self):
        self.players = {}
        self.phase = "waiting"
        self.deck = []
        self.dealer_hand = []
        self.current_turn = None
        self.bets = {}
        self.result = ""

    def new_deck(self):
        d = [r + s for s in SUITS for r in RANKS]
        random.shuffle(d)
        return d

    def reset_round(self):
        self.deck = self.new_deck()
        for p in self.players.values():
            p['hand'] = [self.deck.pop(), self.deck.pop()]
            p['status'] = 'playing'
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.current_turn = list(self.players.values())[0]['name']
        self.phase = 'playing'
        self.bets = {}

    @staticmethod
    def card_value(card):
        rank = card[:-1]
        if rank in ('J', 'Q', 'K'): return 10
        if rank == 'A': return 11
        return int(rank)

    def hand_score(self, hand):
        score = sum(self.card_value(c) for c in hand)
        aces = sum(1 for c in hand if c[:-1] == 'A')
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score

    def player_hit(self, name):
        for p in self.players.values():
            if p['name'] == name:
                p['hand'].append(self.deck.pop())
                if self.hand_score(p['hand']) > 21:
                    p['status'] = 'bust'
                return True
        return False

    def player_stand(self, name):
        for p in self.players.values():
            if p['name'] == name:
                p['status'] = 'stand'
                return True
        return False

    def dealer_play(self):
        while self.hand_score(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        self.phase = 'finished'
        self.resolve()

    def resolve(self):
        d_score = self.hand_score(self.dealer_hand)
        msgs = []
        for ws, p in self.players.items():
            p_score = self.hand_score(p['hand'])
            if p['status'] == 'bust':
                msgs.append(f"{p['name']}: перебор, проиграл")
            elif d_score > 21:
                p['balance'] += self.bets[p['name']] * 2
                msgs.append(f"{p['name']}: дилер перебрал, выиграл {self.bets[p['name']]*2}")
            elif p_score > d_score:
                p['balance'] += self.bets[p['name']] * 2
                msgs.append(f"{p['name']}: победа, выигрыш {self.bets[p['name']]*2}")
            elif p_score < d_score:
                msgs.append(f"{p['name']}: проиграл дилеру")
            else:
                p['balance'] += self.bets[p['name']]
                msgs.append(f"{p['name']}: ничья, ставка возвращена")
        self.result = "\n".join(msgs)

    async def broadcast_state(self):
        state = {
            'phase': self.phase,
            'current_turn': self.current_turn,
            'players': {p['name']: {
                'hand': p['hand'],
                'score': self.hand_score(p['hand']),
                'balance': p['balance'],
                'bet': self.bets.get(p['name'], 0),
                'status': p['status']
            } for p in self.players.values()},
            'dealer_hand': self.dealer_hand if self.phase in ('dealer', 'finished') else [self.dealer_hand[0]],
            'dealer_score': self.hand_score(self.dealer_hand) if self.phase == 'finished' else None,
            'result': self.result
        }
        if self.players:
            message = json.dumps(state)
            await asyncio.wait([ws.send(message) for ws in self.players])

    async def ws_handler(self, ws):
        try:
            init_msg = await ws.recv()
            data = json.loads(init_msg)
            name = data['name']
            if len(self.players) >= 2:
                await ws.send(json.dumps({'error': 'Стол полон'}))
                await ws.close()
                return
            self.players[ws] = {'name': name, 'hand': [], 'balance': 100, 'status': 'waiting'}
            await ws.send(json.dumps({'status': 'connected', 'message': f'Добро пожаловать, {name}'}))
            print(f"Игрок {name} подключился")

            if len(self.players) == 2:
                self.phase = 'betting'
                self.current_turn = list(self.players.values())[0]['name']
                await self.broadcast_state()

            async for message in ws:
                data = json.loads(message)
                action = data.get('action')
                # ... (вся логика обработки ходов, скопируй её из предыдущей полной версии)
                # Ниже вставлена сокращённая версия, но лучше возьми полную из ответа с aiohttp
                if self.phase == 'betting' and action == 'bet':
                    bet = data['amount']
                    me = self.players[ws]
                    if bet <= 0 or bet > me['balance']:
                        await ws.send(json.dumps({'error': 'Некорректная ставка'}))
                        continue
                    self.bets[me['name']] = bet
                    me['balance'] -= bet
                    if len(self.bets) == len(self.players):
                        self.reset_round()
                    await self.broadcast_state()

                elif self.phase == 'playing' and action in ('put', 'stop'):
                    if self.current_turn != self.players[ws]['name']:
                        await ws.send(json.dumps({'error': 'Не ваш ход'}))
                        continue
                    if action == 'put':
                        self.player_hit(self.players[ws]['name'])
                    else:
                        self.player_stand(self.players[ws]['name'])

                    players_list = list(self.players.values())
                    idx = next(i for i, p in enumerate(players_list) if p['name'] == self.current_turn)
                    next_idx = (idx + 1) % len(players_list)
                    all_done = True
                    for _ in range(len(players_list)):
                        if players_list[next_idx]['status'] == 'playing':
                            self.current_turn = players_list[next_idx]['name']
                            all_done = False
                            break
                        next_idx = (next_idx + 1) % len(players_list)
                    if all_done:
                        self.phase = 'dealer'
                        await self.broadcast_state()
                        self.dealer_play()
                    await self.broadcast_state()

                elif self.phase == 'finished' and action == 'new_round':
                    for p in self.players.values():
                        p['hand'] = []
                        p['status'] = 'waiting'
                    self.dealer_hand = []
                    self.phase = 'betting'
                    self.current_turn = list(self.players.values())[0]['name']
                    self.result = ""
                    self.bets = {}
                    await self.broadcast_state()

        except websockets.exceptions.ConnectionClosed:
            print(f"Игрок отключился")
            if ws in self.players:
                del self.players[ws]
            if len(self.players) < 2:
                self.phase = 'waiting'
                await self.broadcast_state()

game = BlackjackGame()

# ---------- HTTP-обработчик для health check ----------
async def handle_http(reader, writer):
    try:
        data = await asyncio.wait_for(reader.read(4096), timeout=5)
        if not data:
            writer.close()
            return
        request_line = data.split(b'\r\n')[0].decode()
        parts = request_line.split()
        if len(parts) < 2:
            writer.close()
            return
        method, path = parts[0], parts[1]

        if path == '/healthz':
            body = "OK"
            if method.upper() == 'HEAD':
                response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n"
            else:
                response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
            writer.write(response)
        else:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        await writer.wait_closed()

# ---------- Главный сервер ----------
async def main():
    port = int(os.environ.get('PORT', 8765))
    # Запускаем websockets сервер на отдельном сокете, но мы можем повесить оба на один порт?
    # Нет, asyncio.start_server можно запустить только один раз на порту.
    # Поэтому используем подход: создаём общий сервер, который разбирает запросы.
    # Если запрос HTTP (особенно HEAD) – отвечаем сами.
    # Если WebSocket (GET + Upgrade) – передаём управление websockets.

    server = await asyncio.start_server(handle_connection, '0.0.0.0', port)
    print(f"Сервер запущен на порту {port}")
    await server.serve_forever()

async def handle_connection(reader, writer):
    # Читаем первые 4 байта, чтобы понять, HTTP или нет
    try:
        peek = await asyncio.wait_for(reader.read(4), timeout=5)
    except asyncio.TimeoutError:
        writer.close()
        return

    if not peek:
        writer.close()
        return

    # Если запрос начинается с HTTP-метода (GET, HEAD...)
    if peek.startswith(b'GET ') or peek.startswith(b'HEAD ') or peek.startswith(b'POST ') or peek.startswith(b'PUT '):
        # Читаем остаток запроса
        data = peek + await asyncio.wait_for(reader.read(4092), timeout=5)
        request_text = data.split(b'\r\n\r\n')[0].decode()
        headers = request_text.split('\r\n')
        request_line = headers[0]
        parts = request_line.split()
        if len(parts) < 2:
            writer.close()
            return
        method, path = parts[0], parts[1]

        # Проверяем, не WebSocket ли это (GET + Upgrade: websocket)
        if method.upper() == 'GET' and any('Upgrade: websocket' in h for h in headers):
            # Это WebSocket handshake. Нужно передать управление websockets.
            # Помещаем уже прочитанные данные обратно в reader.
            # Создадим новый StreamReader, который сначала отдаст data, затем продолжит чтение из оригинального reader.
            # Передадим его в websockets.server.serve или вручную обработаем.
            # Воспользуемся внутренним механизмом websockets.
            await handle_ws_upgrade(reader, writer, data)
            return

        # Обычный HTTP запрос
        if path == '/healthz':
            body = "OK"
            if method.upper() == 'HEAD':
                response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n"
            else:
                response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
            writer.write(response)
        else:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return

    # Если не HTTP – просто закрываем
    writer.close()

async def handle_ws_upgrade(reader, writer, initial_data):
    # Создаём буферизованный reader, который сначала отдаст initial_data
    class BufferedReader:
        def __init__(self, prefix, reader):
            self._prefix = prefix
            self._reader = reader
            self._offset = 0

        async def read(self, n=-1):
            if self._offset < len(self._prefix):
                chunk = self._prefix[self._offset:self._offset+n] if n > 0 else self._prefix[self._offset:]
                self._offset += len(chunk)
                if n > 0 and len(chunk) < n:
                    rest = await self._reader.read(n - len(chunk))
                    return chunk + rest
                return chunk
            return await self._reader.read(n)

        async def readexactly(self, n):
            data = b''
            while len(data) < n:
                chunk = await self.read(n - len(data))
                if not chunk:
                    raise asyncio.IncompleteReadError(data, n)
                data += chunk
            return data

        def at_eof(self):
            return self._offset >= len(self._prefix) and self._reader.at_eof()

    # Создаём объект websocket соединения через websockets.server.WebSocketServerProtocol
    # Но проще использовать функцию websockets.server.serve с уже готовым сокетом.
    # Документация websockets показывает, как создать сервер из существующего reader/writer.
    # Вот работающий способ (для версии websockets 11+):
    from websockets.asyncio.server import ServerConnection

    class MyServerProtocol(websockets.ServerProtocol):
        pass

    protocol = MyServerProtocol()
    connection = ServerConnection(protocol, reader=BufferedReader(initial_data, reader), writer=writer)
    # Запускаем обработчик игры
    await game.ws_handler(connection)

if __name__ == '__main__':
    asyncio.run(main())
