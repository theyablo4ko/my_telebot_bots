import asyncio
import json
import os
import random
from aiohttp import web, WSMsgType

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

class BlackjackGame:
    def __init__(self):
        self.players = {}          # ws -> player_data
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
            await asyncio.wait([ws.send_str(message) for ws in self.players])

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        try:
            init_msg = await ws.receive_str()
            data = json.loads(init_msg)
            name = data['name']
            if len(self.players) >= 2:
                await ws.send_str(json.dumps({'error': 'Стол полон'}))
                await ws.close()
                return ws
            self.players[ws] = {'name': name, 'hand': [], 'balance': 100, 'status': 'waiting'}
            await ws.send_str(json.dumps({'status': 'connected', 'message': f'Добро пожаловать, {name}'}))
            print(f"Игрок {name} подключился")

            if len(self.players) == 2:
                self.phase = 'betting'
                self.current_turn = list(self.players.values())[0]['name']
                await self.broadcast_state()

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    action = data.get('action')

                    if self.phase == 'betting' and action == 'bet':
                        bet = data['amount']
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
                    print(f'WebSocket error: {ws.exception()}')
        except Exception as e:
            print(f"Exception: {e}")
        finally:
            if ws in self.players:
                name = self.players[ws]['name']
                del self.players[ws]
                print(f"Игрок {name} отключился")
                if len(self.players) < 2:
                    self.phase = 'waiting'
                    await self.broadcast_state()
        return ws

game = BlackjackGame()

async def health_check(request):
    return web.Response(text="OK")

app = web.Application()
# aiohttp автоматически поддерживает HEAD для GET-маршрутов!
app.router.add_get('/healthz', health_check)
app.router.add_get('/ws', game.handle_ws)   # WebSocket endpoint

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    web.run_app(app, host='0.0.0.0', port=port)
