import asyncio
import json
import logging
import os
import random
from aiohttp import web, WSMsgType

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

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
        if rank in ('J', 'Q', 'K'):
            return 10
        if rank == 'A':
            return 11
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
        # Безопасно формируем отображаемую руку дилера
        if self.dealer_hand:
            if self.phase in ('dealer', 'finished'):
                dealer_display = self.dealer_hand
            else:
                dealer_display = [self.dealer_hand[0]]
        else:
            dealer_display = []

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
            'dealer_hand': dealer_display,
            'dealer_score': self.hand_score(self.dealer_hand) if self.phase == 'finished' else None,
            'result': self.result
        }
        if self.players:
            message = json.dumps(state)
            logger.info(f"Broadcasting state to {len(self.players)} player(s)")
            await asyncio.wait([ws.send_str(message) for ws in self.players])

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        logger.info(f"WebSocket connection attempt from {request.remote}")

        try:
            init_msg = await ws.receive()
            if init_msg.type != WSMsgType.TEXT:
                logger.warning("First message is not text, closing")
                await ws.close()
                return ws

            try:
                data = json.loads(init_msg.data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {init_msg.data}")
                await ws.send_str(json.dumps({'error': 'Неверный формат'}))
                await ws.close()
                return ws

            name = data.get('name', '').strip()
            if not name:
                await ws.send_str(json.dumps({'error': 'Имя не указано'}))
                await ws.close()
                return ws

            if len(self.players) >= 2:
                await ws.send_str(json.dumps({'error': 'Стол полон, максимум 2 игрока'}))
                await ws.close()
                return ws

            self.players[ws] = {'name': name, 'hand': [], 'balance': 100, 'status': 'waiting'}
            logger.info(f"Игрок {name} подключился")

            await self.broadcast_state()

            if len(self.players) == 2:
                self.phase = 'betting'
                self.current_turn = list(self.players.values())[0]['name']
                await self.broadcast_state()

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    logger.info(f"Message from {name}: {msg.data}")
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await ws.send_str(json.dumps({'error': 'Неверный JSON'}))
                        continue

                    action = data.get('action')

                    if self.phase == 'betting' and action == 'bet':
                        bet = data.get('amount', 0)
                        me = self.players[ws]
                        if bet <= 0 or bet > me['balance']:
                            await ws.send_str(json.dumps({'error': 'Некорректная ставка'}))
                            continue
                        self.bets[me['name']] = bet
                        me['balance'] -= bet
                        if len(self.bets) == len(self.players):
                            self.reset_round()
                        await self.broadcast_state()

                    elif self.phase == 'playing' and action in ('put', 'stop'):
                        if self.current_turn != self.players[ws]['name']:
                            await ws.send_str(json.dumps({'error': 'Не ваш ход'}))
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

                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
                else:
                    logger.info(f"Non-text message type {msg.type} ignored")

        except Exception as e:
            logger.error(f"Exception in handle_ws: {e}")
        finally:
            if ws in self.players:
                name = self.players[ws]['name']
                del self.players[ws]
                logger.info(f"Игрок {name} отключился")
                if len(self.players) < 2:
                    self.phase = 'waiting'
                await self.broadcast_state()
        return ws

# ---------- Создаём игру ----------
game = BlackjackGame()

async def health_check(request):
    logger.info(f"Health check from {request.remote}")
    return web.Response(text="OK")

@web.middleware
async def log_middleware(request, handler):
    logger.info(f"HTTP {request.method} {request.path} from {request.remote}")
    return await handler(request)

app = web.Application(middlewares=[log_middleware])
app.router.add_get('/healthz', health_check)
app.router.add_get('/ws', game.handle_ws)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    logger.info(f"Starting server on port {port}")
    web.run_app(app, host='0.0.0.0', port=port)
