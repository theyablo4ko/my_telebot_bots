import asyncio
import json
import os
import sys
import websockets
from colorama import init, Fore, Back, Style

init(autoreset=True)

SERVER_URL = "wss://my-telebot-bots.onrender.com/ws"

# ---------- Статистика ----------
class GameStats:
    def __init__(self, initial_balance=100):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.wins = 0
        self.losses = 0
        self.pushes = 0
        self.history = []
        self.round_number = 0

    def add_round(self, player_hand, dealer_hand, result_str, new_balance):
        self.round_number += 1
        outcome = self._parse_outcome(result_str)
        if outcome == 'win':
            self.wins += 1
        elif outcome == 'loss':
            self.losses += 1
        elif outcome == 'push':
            self.pushes += 1
        self.history.append({
            'round': self.round_number,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'outcome': outcome,
            'result_text': result_str,
            'balance_change': new_balance - self.balance,
            'balance_after': new_balance
        })
        self.balance = new_balance

    def _parse_outcome(self, text):
        if 'победа' in text or 'выиграл' in text or 'выигрыш' in text:
            return 'win'
        elif 'проиграл' in text or 'проигрыш' in text:
            return 'loss'
        elif 'ничья' in text:
            return 'push'
        return 'unknown'

    def get_summary(self):
        total = self.wins + self.losses + self.pushes
        winrate = (self.wins / total * 100) if total > 0 else 0.0
        return (
            f"Всего раундов: {total}\n"
            f"Побед: {self.wins} | Поражений: {self.losses} | Ничьих: {self.pushes}\n"
            f"Винрейт: {winrate:.1f}%\n"
            f"Текущий баланс: {self.balance} (изменение: {self.balance - self.initial_balance:+d})"
        )

    def get_history(self, last_n=10):
        lines = []
        for rec in self.history[-last_n:]:
            lines.append(
                f"Раунд {rec['round']}: Рука: {', '.join(rec['player_hand'])} | "
                f"Дилер: {', '.join(rec['dealer_hand'])} | "
                f"Исход: {rec['outcome']} | Баланс: {rec['balance_after']} ({rec['balance_change']:+d})"
            )
        return "\n".join(lines) if lines else "История пуста."

# ---------- Подсказки ----------
def get_hint(player_hand, dealer_upcard):
    if not player_hand or not dealer_upcard:
        return None
    values = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':10,'Q':10,'K':10,'A':11}
    def card_val(card):
        rank = card[:-1]
        return values.get(rank, 0)
    total = sum(card_val(c) for c in player_hand)
    aces = sum(1 for c in player_hand if c[:-1] == 'A')
    soft = (aces > 0 and total <= 21)
    dealer_val = card_val(dealer_upcard)
    if soft:
        if total >= 20: return 'stop'
        elif total == 19: return 'stop'
        elif total == 18: return 'stop' if dealer_val in (2,3,4,5,6,7,8) else 'put'
        else: return 'put'
    else:
        if total >= 17: return 'stop'
        elif total <= 11: return 'put'
        else: return 'stop' if dealer_val < 7 else 'put'

# ---------- Отображение ----------
def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_state(state, my_name, stats):
    clear()
    print(Style.BRIGHT + Fore.CYAN + "=" * 50)
    print(Fore.YELLOW + f"🃏 Блекджек — {my_name}")
    print(Fore.CYAN + "=" * 50)

    phase = state.get('phase', '')
    if phase == 'waiting':
        print(Fore.MAGENTA + "\n⏳ Ожидание подключения второго игрока...")
        return

    print(Fore.WHITE + f"Фаза: {phase}")
    if state.get('current_turn'):
        is_my_turn = (state['current_turn'] == my_name)
        turn_color = Fore.GREEN if is_my_turn else Fore.YELLOW
        print(turn_color + f"Ход: {state['current_turn']} {'← ВЫ' if is_my_turn else '— думает'}")

    dhand = state.get('dealer_hand', [])
    dscore = state.get('dealer_score')
    print(Fore.RED + "\n--- Дилер ---")
    if dhand:
        if phase in ('dealer', 'finished') and dscore is not None:
            print(Fore.RED + f"Карты: {', '.join(dhand)} (очки: {dscore})")
        else:
            print(Fore.RED + f"Карты: [{dhand[0]}, ??]")
    else:
        print(Fore.RED + "Карт нет")

    print(Fore.BLUE + "\n--- Игроки ---")
    for pname, pinfo in state.get('players', {}).items():
        is_me = (pname == my_name)
        name_color = Fore.GREEN if is_me else Fore.WHITE
        name_suffix = " (ВЫ)" if is_me else ""
        if is_me or phase == 'finished':
            hand_str = ', '.join(pinfo['hand']) if pinfo['hand'] else "—"
            score = pinfo.get('score', '?')
            status = pinfo.get('status', '')
            status_str = f" | {_status_color(status)}{status}{Fore.RESET}" if status else ""
            print(name_color + f"{pname}{name_suffix}: {hand_str} (очки: {score}) | Баланс: {pinfo['balance']} | Ставка: {pinfo['bet']}{status_str}")
        else:
            hidden = ['??'] * len(pinfo['hand']) if pinfo['hand'] else ["—"]
            print(name_color + f"{pname}: {', '.join(hidden)} | Баланс: {pinfo['balance']} | Ставка: {pinfo['bet']}")

    result = state.get('result')
    if result:
        print("\n" + Back.BLUE + Fore.WHITE + " Результат раунда " + Back.RESET)
        for line in result.split('\n'):
            if 'победа' in line or 'выиграл' in line or 'выигрыш' in line:
                print(Fore.GREEN + "  " + line)
            elif 'проиграл' in line or 'проигрыш' in line:
                print(Fore.RED + "  " + line)
            elif 'ничья' in line:
                print(Fore.YELLOW + "  " + line)
            else:
                print(Fore.CYAN + "  " + line)

    if phase == 'playing' and state['current_turn'] == my_name and dhand:
        my_hand = state['players'][my_name]['hand']
        dealer_upcard = dhand[0]
        hint = get_hint(my_hand, dealer_upcard)
        if hint:
            hint_text = "💡 Рекомендация: " + ("Взять (put)" if hint == 'put' else "Остановиться (stop)")
            print("\n" + Fore.MAGENTA + hint_text)

    # Статистика всегда внизу
    print("\n" + Fore.CYAN + "─" * 50)
    print(Fore.WHITE + f"Баланс: {stats.balance} | Побед: {stats.wins} | Поражений: {stats.losses} | Ничьих: {stats.pushes}")

def _status_color(status):
    if status == 'bust': return Fore.RED
    elif status == 'stand': return Fore.GREEN
    return Fore.WHITE

# ---------- Главный игровой цикл ----------
async def game_loop(ws, my_name):
    """Основной цикл: получает состояние, показывает, ждёт действия."""
    stats = None
    state = None

    while True:
        try:
            # Ждём сообщение от сервера
            msg = await ws.recv()
            state = json.loads(msg)
        except websockets.ConnectionClosed:
            print(Fore.RED + "\n🔌 Соединение с сервером закрыто.")
            break

        # Инициализируем статистику при первой возможности
        if stats is None and my_name in state.get('players', {}):
            stats = GameStats(state['players'][my_name]['balance'])

        # Сохраняем результат раунда
        if state['phase'] == 'finished' and state.get('result') and stats:
            my_result_line = ""
            for line in state['result'].split('\n'):
                if line.startswith(my_name + ':'):
                    my_result_line = line
                    break
            if my_result_line:
                my_hand = state['players'][my_name]['hand']
                dealer_hand = state.get('dealer_hand', [])
                new_balance = state['players'][my_name]['balance']
                stats.add_round(my_hand, dealer_hand, my_result_line, new_balance)

        # Показываем состояние
        if state:
            show_state(state, my_name, stats)

        # Если ждём второго игрока — просто ждём следующее сообщение
        if state['phase'] == 'waiting':
            continue

        # Проверяем, нужно ли действие от нас
        phase = state['phase']
        is_my_turn = (state.get('current_turn') == my_name)
        my_info = state['players'].get(my_name)

        if not my_info:
            continue

        # Автовыход при нулевом балансе
        if my_info['balance'] <= 0:
            print(Fore.RED + "\n💸 Ваш баланс равен 0. Вы покидаете игру.")
            await ws.close()
            break

        # ---------- Требуется ввод от игрока ----------
        need_input = False

        # Фаза ставок и мы ещё не поставили
        if phase == 'betting' and my_info['bet'] == 0:
            need_input = True
            action = await get_betting_action(my_info['balance'], stats)
            if action == 'quit':
                break
            await ws.send(json.dumps(action))

        # Наш ход в игре
        elif phase == 'playing' and is_my_turn:
            need_input = True
            action = await get_playing_action(stats)
            if action == 'quit':
                break
            await ws.send(json.dumps(action))

        # Конец раунда — ждём решения о продолжении
        elif phase == 'finished':
            need_input = True
            action = await get_finished_action(stats)
            if action == 'quit':
                await ws.send(json.dumps({"action": "new_round"}))  # последний раунд перед выходом?
                break
            if action == 'leave':
                print(Fore.YELLOW + "\n👋 Спасибо за игру!")
                await ws.close()
                break
            await ws.send(json.dumps(action))

        # Если ввода не требовалось — просто ждём следующее сообщение
        # (цикл автоматически продолжит)

async def get_betting_action(balance, stats):
    """Запрашивает ставку у игрока."""
    while True:
        cmd = input(Fore.CYAN + f"\n💰 Ваша ставка (баланс: {balance}) или stats/history: ").strip().lower()
        if cmd == 'stats':
            print(Fore.YELLOW + stats.get_summary())
            continue
        elif cmd == 'history':
            print(Fore.YELLOW + stats.get_history())
            continue
        try:
            bet = int(cmd)
            if 0 < bet <= balance:
                print(Fore.GREEN + f"✅ Ставка {bet} принята, ждём соперника...")
                return {"action": "bet", "amount": bet}
            print(Fore.RED + "Некорректная сумма.")
        except ValueError:
            print(Fore.RED + "Введите целое число или stats/history.")

async def get_playing_action(stats):
    """Запрашивает ход игрока."""
    while True:
        cmd = input(Fore.CYAN + "\n🎮 Ваш ход (put/stop/stats/history): ").strip().lower()
        if cmd == 'stats':
            print(Fore.YELLOW + stats.get_summary())
            continue
        elif cmd == 'history':
            print(Fore.YELLOW + stats.get_history())
            continue
        if cmd in ('put', 'stop'):
            print(Fore.GREEN + f"✅ Выбрано: {cmd}")
            return {"action": cmd}
        print(Fore.RED + "Введите put, stop, stats или history.")

async def get_finished_action(stats):
    """Запрашивает действие после раунда."""
    while True:
        cmd = input(Fore.CYAN + "\n🔄 Сыграть ещё? (y/n/stats/history): ").strip().lower()
        if cmd == 'stats':
            print(Fore.YELLOW + stats.get_summary())
            continue
        elif cmd == 'history':
            print(Fore.YELLOW + stats.get_history())
            continue
        if cmd == 'y':
            return {"action": "new_round"}
        elif cmd == 'n':
            return "leave"
        print(Fore.RED + "Введите y, n, stats или history.")

# ---------- Точка входа ----------
async def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = SERVER_URL

    my_name = input(Fore.CYAN + "Введи свой ник: ").strip()
    print(Fore.CYAN + f"Подключаюсь к {url} ...")

    try:
        # Долгие пинги, чтобы Render не разрывал соединение
        async with websockets.connect(url, ping_interval=30, ping_timeout=20) as ws:
            # Регистрация
            await ws.send(json.dumps({"name": my_name}))

            # Запускаем игровой цикл
            await game_loop(ws, my_name)

    except websockets.ConnectionClosed:
        print(Fore.RED + "\nСоединение закрыто сервером.")
    except Exception as e:
        print(Fore.RED + f"\nНе удалось подключиться: {e}")

if __name__ == "__main__":
    asyncio.run(main())
