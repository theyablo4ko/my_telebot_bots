# =============================================================
# КЛИЕНТ БЛЕКДЖЕКА  (консоль)
# =============================================================
# Запуск:  python client.py
#
# Что делает этот файл:
#   - Подключается к серверу по WebSocket
#   - Получает обновления состояния и отображает их в консоли
#   - Читает команды пользователя из терминала
#
# Установка зависимости (один раз):
#   pip install websockets
# =============================================================

import asyncio
import json
import sys
import websockets
import os

SERVER = "ws://localhost:8765"

# Сохраняем последнее состояние, чтобы перерисовывать экран
last_state = None
my_id      = None

# Очередь команд: пользователь вводит текст → кладём сюда → отправляем серверу
input_queue: asyncio.Queue = None


# =============================================================
# ОТРИСОВКА СОСТОЯНИЯ
# =============================================================

SUIT_MAP = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}

def pretty_card(card: str) -> str:
    """Превращает 'AH' → 'A♥', '10S' → '10♠', '??' → '??'"""
    if card == "??":
        return "[??]"
    suit = SUIT_MAP.get(card[-1], card[-1])
    val  = card[:-1]
    return f"[{val}{suit}]"

def pretty_hand(hand: list) -> str:
    return "  ".join(pretty_card(c) for c in hand)

STATUS_LABELS = {
    "waiting": "ожидает",
    "acting":  ">>> ХОД <<<",
    "stand":   "стоп",
    "bust":    "ПЕРЕБОР",
    "win":     "ПОБЕДА  +",
    "lose":    "проигрыш -",
    "push":    "ничья",
}

def render(s: dict):
    """Очищает экран и рисует текущее состояние игры."""
    print("\033[2J\033[H", end="")   # очистить терминал

    clear()

    phase_labels = {
        "lobby":   "Лобби — ждём игроков",
        "betting": "Фаза ставок",
        "playing": "Идёт игра",
        "results": "Итоги раунда",
    }
    print("=" * 55)
    print(f"  БЛЕКДЖЕК  |  {phase_labels.get(s['phase'], s['phase'])}")
    print("=" * 55)

    # ── Рука дилера ─────────────────────────────────────────
    print(f"\n  ДИЛЕР:  {pretty_hand(s['dealer_hand'])}   ({s['dealer_total']})")
    print()

    # ── Игроки ──────────────────────────────────────────────
    for pid in s["order"]:
        p    = s["players"][pid]
        me   = " (ты)" if pid == s["my_id"] else ""
        host = " [ХОСТ]" if pid == s["host"] else ""
        lbl  = STATUS_LABELS.get(p["status"], p["status"])

        print(f"  {p['name']}{me}{host}")
        print(f"    Кредиты: {p['credits']}  |  Ставка: {p['bet']}  |  {lbl}")
        if p["hand"]:
            print(f"    Карты:  {pretty_hand(p['hand'])}   ({p['total']})")
        print()

    # ── Итоги раунда (показываем только когда фаза results) ─
    if s["phase"] == "results":
        _print_results(s)

    # ── Подсказка по доступным командам ─────────────────────
    print("-" * 55)
    _print_hint(s)
    print()


def _print_results(s: dict):
    """
    Рисует красивую таблицу итогов раунда.
    Вызывается только когда phase == 'results'.
    """

    # Иконки и текст для каждого исхода
    # Ключ — статус игрока который пришёл с сервера
    RESULT_STYLE = {
        "win":  ("🏆", "ПОБЕДА",   "+"),   # (иконка, слово, знак перед суммой)
        "lose": ("💸", "ПРОИГРЫШ", "-"),
        "bust": ("💥", "ПЕРЕБОР",  "-"),
        "push": ("🤝", "НИЧЬЯ",    " "),
    }

    print("=" * 55)
    print("  ИТОГИ РАУНДА")
    print("=" * 55)

    # Проходим по каждому игроку в порядке очереди
    for pid in s["order"]:
        p = s["players"][pid]

        # Берём иконку/слово/знак для этого игрока
        # Если статус незнакомый — показываем заглушку
        icon, word, sign = RESULT_STYLE.get(p["status"], ("?", p["status"], ""))

        # Считаем на сколько изменились кредиты за этот раунд
        # bust и lose — игрок теряет ставку, win — получает, push — ничего
        if p["status"] in ("lose", "bust"):
            delta = p["bet"]          # потерял столько
        elif p["status"] == "win":
            delta = p["bet"]          # выиграл столько
        else:
            delta = 0                 # ничья — ничего не изменилось

        # Пометка "(ты)" только для нашего игрока
        me = " (ты)" if pid == s["my_id"] else ""

        # Строка итога, например:  🏆 ПОБЕДА   Вася (ты)  +100 кр.  → итого: 1100
        print(f"  {icon}  {word:<10}  {p['name']}{me}")
        if delta > 0:
            print(f"             Ставка: {p['bet']}  →  {sign}{delta} кр.  |  Кредиты: {p['credits']}")
        else:
            print(f"             Ставка: {p['bet']}  →  без изменений  |  Кредиты: {p['credits']}")
        print()

    print("=" * 55)
    print()


def _print_hint(s: dict):
    """Печатает подсказку о том, что можно сделать прямо сейчас."""
    pid   = s["my_id"]
    phase = s["phase"]

    if phase == "lobby":
        if pid == s["host"]:
            print("  Введите  start  — чтобы начать игру")
        else:
            print("  Ждём, пока хост начнёт игру...")

    elif phase == "betting":
        p = s["players"].get(pid, {})
        if p.get("bet", 0) == 0:
            print(f"  Введите  bet <сумма>  — сделать ставку")
            print(f"  Пример:  bet 100")
        else:
            print(f"  Ставка сделана: {p['bet']}. Ждём остальных...")

    elif phase == "playing":
        if s["current"] == pid:
            print("  Твой ход!")
            print("  hit   — взять ещё карту")
            print("  stand — остановиться")
        else:
            cur = s["players"].get(s["current"], {})
            print(f"  Ход игрока: {cur.get('name','?')}. Ждём...")

    elif phase == "results":
        if pid == s["host"]:
            print("  Введите  start  — сыграть ещё раунд")
        else:
            print("  Ждём, пока хост начнёт новый раунд...")


# =============================================================
# РАЗБОР ВВОДА ПОЛЬЗОВАТЕЛЯ → КОМАНДА ДЛЯ СЕРВЕРА
# =============================================================

def parse_input(text: str, s: dict) -> dict | None:
    """
    Преобразует строку пользователя в словарь-команду для сервера.
    Возвращает None, если команда неизвестна.
    """
    parts = text.strip().lower().split()
    if not parts:
        return None

    cmd = parts[0]

    if cmd == "start":
        return {"cmd": "start"}

    if cmd == "hit":
        return {"cmd": "hit"}

    if cmd == "stand":
        return {"cmd": "stand"}

    if cmd == "bet" and len(parts) == 2:
        try:
            return {"cmd": "bet", "amount": int(parts[1])}
        except ValueError:
            print("  Ошибка: сумма должна быть числом, например:  bet 100")
            return None

    print(f"  Неизвестная команда: {text.strip()}")
    return None


# =============================================================
# АСИНХРОННЫЕ ЗАДАЧИ
# =============================================================

async def receive_loop(ws):
    """
    Постоянно слушает сообщения от сервера.
    При получении — перерисовывает экран.
    """
    global last_state, my_id

    async for raw in ws:
        msg = json.loads(raw)

        if msg["type"] == "welcome":
            my_id = msg["your_id"]
            # Сразу отправляем команду «войти» с именем
            name = input("  Введите ваше имя: ").strip() or f"Player{my_id}"
            await ws.send(json.dumps({"cmd": "join", "name": name}))

        elif msg["type"] == "state":
            last_state = msg
            render(msg)


async def input_loop():
    """
    Читает строки из терминала и кладёт их в очередь.
    Работает в отдельном потоке, чтобы не блокировать asyncio.
    """
    loop = asyncio.get_event_loop()
    while True:
        # run_in_executor позволяет вызвать блокирующий input() не блокируя всю программу
        line = await loop.run_in_executor(None, sys.stdin.readline)
        await input_queue.put(line)


async def send_loop(ws):
    """
    Достаёт команды из очереди и отправляет на сервер.
    """
    while True:
        line = await input_queue.get()
        if last_state is None:
            continue
        cmd = parse_input(line, last_state)
        if cmd:
            await ws.send(json.dumps(cmd))

def clear():
    os.system('cls')

# =============================================================
# ТОЧКА ВХОДА
# =============================================================

async def main():
    clear()
    global input_queue
    input_queue = asyncio.Queue()

    print(f"Подключаемся к {SERVER} ...")

    try:
        async with websockets.connect(SERVER) as ws:
            print("Подключено!\n")
            # Запускаем все три задачи параллельно
            await asyncio.gather(
                receive_loop(ws),
                input_loop(),
                send_loop(ws),
            )
    except ConnectionRefusedError:
        print("\nОшибка: не удалось подключиться к серверу.")
        print("Убедитесь, что сервер запущен:  python server.py")


if __name__ == "__main__":
    asyncio.run(main())