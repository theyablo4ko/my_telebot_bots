import asyncio
import json
import logging
import os
import random
import traceback
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
        self.bets = {p['name']: 0 for p in self.players.values()}

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
        for ws, p in list(self.players.items()):
            if ws not in self.players:
                continue
            p_score = self.hand_score(p['hand'])
            bet = self.bets.get(p['name'], 0)
            if p['status'] == 'bust':
                msgs.append(f"{p['name']}: перебор, проиграл")
            elif d_score > 21:
                p['balance'] += bet * 2
                msgs.append(f"{p['name']}: дилер перебрал, выиграл {bet*2}")
            elif p_score > d_score:
                p['balance'] += bet * 2
                msgs.append(f"{p['name']}: победа, выигрыш {bet*2}")
            elif p_score < d_score:
                msgs.append(f"{p['name']}: проиграл дилеру")
            else:
                p['balance'] += bet
                msgs.append(f"{p['name']}: ничья, ставка возвращена")
        self.result = "\n".join(msgs)

    async def broadcast_state(self):
        # Очищаем неактивные соединения перед отправкой
        inactive = [ws for ws in self.players if ws.closed]
        for ws in inactive:
            name = self.players[ws]['name']
            del self.players[ws]
            logger.info(f"Удалён неактивный игрок {name} перед broadcast")
        if inactive and len(self.players) < 2:
            self.phase = 'waiting'
            self.current_turn = None
            self.bets = {}
            self.dealer_hand = []
            self.result = ""

        player_names = [p['name'] for p in self.players.values()]
        logger.info(f"broadcast: phase={self.phase}, players={player_names}")

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

        if not self.players:
            logger.info("broadcast: нет игроков, пропускаем")
            return

        message = json.dumps(state)
        logger.info(f"broadcast: отправка {len(message)} байт")

        # Исправленная отправка через asyncio.create_task
        tasks = [asyncio.create_task(ws.send_str(message)) for ws in self.players]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ws, res in zip(self.players, results):
            if isinstance(res, Exception):
                name = self.players[ws]['name']
                logger.error(f"Ошибка отправки игроку {name}: {res}")
                # Попытка удалить проблемное соединение
                try:
                    del self.players[ws]
                    logger.info(f"Удалён игрок {name} из-за ошибки отправки")
                except:
                    pass
        # После возможного удаления обновим фазу, если надо
        if len(self.players) < 2 and self.phase != 'waiting':
            self.phase = 'waiting'
            self.current_turn = None
            self.bets = {}
            self.dealer_hand = []
            self.result = ""

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        logger.info(f"WS соединение от {request.remote}")

        try:
            init_msg = await ws.receive()
            if init_msg.type != WSMsgType.TEXT:
                await ws.close()
                return ws
            try:
                data = json.loads(init_msg.data)
            except:
                await ws.send_str(json.dumps({'error': 'Неверный JSON'}))
                await ws.close()
                return ws

            name = data.get('name', '').strip()
            if not name:
                await ws.send_str(json.dumps({'error': 'Имя не указано'}))
                await ws.close()
                return ws

            # Очищаем мёртвые соединения
            inactive = [w for w in self.players if w.closed]
            for w in inactive:
                logger.info(f"Удалён неактивный игрок {self.players[w]['name']}")
                del self.players[w]
            if inactive and len(self.players) < 2:
                self.phase = 'waiting'
                await self.broadcast_state()

            if len(self.players) >= 2:
                await ws.send_str(json.dumps({'error': 'Стол полон'}))
                await ws.close()
                return ws

            self.players[ws] = {'name': name, 'hand': [], 'balance': 100, 'status': 'waiting'}
            logger.info(f"Игрок {name} подключился, всего игроков: {len(self.players)}")

            if len(self.players) == 2:
                self.phase = 'betting'
                self.current_turn = list(self.players.values())[0]['name']
            await self.broadcast_state()

            # Основной цикл приёма сообщений
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except:
                        await ws.send_str(json.dumps({'error': 'Неверный JSON'}))
                        continue
                    action = data.get('action')
                    logger.info(f"Действие от {name}: {action}")

                    # Обработка действий
                    if action == 'bet' and self.phase == 'betting':
                        amount = data.get('amount', 0)
                        me = self.players.get(ws)
                        if not me:
                            break
                        if amount <= 0 or amount > me['balance']:
                            await ws.send_str(json.dumps({'error': 'Неверная ставка'}))
                            continue
                        self.bets[me['name']] = amount
                        me['balance'] -= amount
                        logger.info(f"Игрок {name} поставил {amount}, ставки: {self.bets}")
                        if len(self.bets) == 2:
                            self.reset_round()
                        await self.broadcast_state()

                    elif action in ('put', 'stop') and self.phase == 'playing':
                        if self.current_turn != name:
                            await ws.send_str(json.dumps({'error': 'Не ваш ход'}))
                            continue
                        if action == 'put':
                            self.player_hit(name)
                        else:
                            self.player_stand(name)
                        # Переход хода
                        players_list = [p for p in self.players.values() if p['status'] == 'playing']
                        if players_list:
                            # Найти следующего после текущего
                            try:
                                cur_idx = next(i for i, p in enumerate(players_list) if p['name'] == self.current_turn)
                                next_idx = (cur_idx + 1) % len(players_list)
                                self.current_turn = players_list[next_idx]['name']
                            except StopIteration:
                                self.current_turn = players_list[0]['name']
                        else:
                            # Все закончили
                            self.phase = 'dealer'
                            await self.broadcast_state()
                            self.dealer_play()
                        await self.broadcast_state()

                    elif action == 'new_round' and self.phase == 'finished':
                        if len(self.players) == 2:
                            for p in self.players.values():
                                p['hand'] = []
                                p['status'] = 'waiting'
                            self.dealer_hand = []
                            self.phase = 'betting'
                            self.current_turn = list(self.players.values())[0]['name']
                            self.result = ""
                            self.bets = {}
                            await self.broadcast_state()
                        else:
                            await ws.send_str(json.dumps({'error': 'Недостаточно игроков'}))

                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
        except Exception as e:
            logger.error(f"Ошибка в handle_ws: {e}\n{traceback.format_exc()}")
        finally:
            if ws in self.players:
                name = self.players[ws]['name']
                del self.players[ws]
                logger.info(f"Игрок {name} отключился, осталось {len(self.players)}")
                if len(self.players) == 1:
                    self.phase = 'waiting'
                    self.current_turn = None
                    self.bets = {}
                    self.dealer_hand = []
                    self.result = ""
                    await self.broadcast_state()
                elif len(self.players) == 0:
                    self.phase = 'waiting'
                    self.current_turn = None
                    self.bets = {}
                    self.dealer_hand = []
                    self.result = ""
        return ws

# ---------- Приложение ----------
game = BlackjackGame()

async def health_check(request):
    return web.Response(text="OK")

@web.middleware
async def log_middleware(request, handler):
    logger.info(f"HTTP {request.method} {request.path} от {request.remote}")
    return await handler(request)

app = web.Application(middlewares=[log_middleware])
app.router.add_get('/healthz', health_check)
app.router.add_get('/ws', game.handle_ws)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    logger.info(f"Старт сервера на порту {port}")
    web.run_app(app, host='0.0.0.0', port=port)
