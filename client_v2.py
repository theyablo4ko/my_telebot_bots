# =============================================================
# КЛИЕНТ БЛЕКДЖЕКА  (консоль, цветной)
# =============================================================
# Запуск:  python client.py
#
# Зависимости (один раз):
#   pip install websockets colorama
# =============================================================

import asyncio
import json
import sys
import websockets
import os
import time

from colorama import Fore, Back, Style, init

# Инициализация colorama (нужно для корректной работы цветов в Windows)
init(autoreset=True)

SERVER = "wss://my-telebot-bots-oitl.onrender.com/ws"

# Сохраняем последнее состояние, чтобы перерисовывать экран
last_state = None
my_id      = None

# Очередь команд: пользователь вводит текст → кладём сюда → отправляем серверу
input_queue: asyncio.Queue = None


# =============================================================
# ЦВЕТОВАЯ ПАЛИТРА
# =============================================================

# Общие элементы
C_BORDER   = Fore.CYAN + Style.BRIGHT
C_TITLE    = Fore.CYAN + Style.BRIGHT
C_RESET    = Style.RESET_ALL

# Игроки
C_ME       = Fore.GREEN + Style.BRIGHT     # "ты"
C_HOST     = Fore.MAGENTA + Style.BRIGHT   # хост
C_NAME     = Fore.WHITE                    # обычный игрок
C_CREDITS  = Fore.YELLOW                   # кредиты
C_BET      = Fore.CYAN                     # ставка

# Карты
C_RED_SUIT   = Fore.RED + Style.BRIGHT     # ♥ ♦
C_BLACK_SUIT = Fore.WHITE + Style.BRIGHT   # ♠ ♣
C_HIDDEN     = Fore.LIGHTBLACK_EX          # ??

# Статусы игрока
C_WAITING  = Fore.LIGHTBLACK_EX
C_ACTING   = Fore.YELLOW + Style.BRIGHT    # ">>> ХОД <<<"
C_STAND    = Fore.BLUE
C_BUST     = Fore.RED + Style.BRIGHT
C_WIN      = Fore.GREEN + Style.BRIGHT
C_LOSE     = Fore.RED
C_PUSH     = Fore.LIGHTBLUE_EX

# Фазы игры
C_PHASE_LOBBY   = Fore.LIGHTBLACK_EX
C_PHASE_BETTING = Fore.YELLOW
C_PHASE_PLAYING = Fore.GREEN + Style.BRIGHT
C_PHASE_RESULTS = Fore.MAGENTA + Style.BRIGHT

# Дилер
C_DEALER   = Fore.YELLOW + Style.BRIGHT

# Подсказки
C_HINT     = Fore.LIGHTBLACK_EX
C_HINT_CMD = Fore.LIGHTCYAN_EX             # команды в подсказках

# Итоги раунда
C_RES_WIN  = Fore.GREEN + Style.BRIGHT
C_RES_LOSE = Fore.RED
C_RES_BUST = Fore.RED + Style.BRIGHT
C_RES_PUSH = Fore.CYAN


# =============================================================
# ОТРИСОВКА СОСТОЯНИЯ
# =============================================================

SUIT_MAP = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}

def pretty_card(card: str) -> str:
    """Превращает 'AH' → 'A♥', '10S' → '10♠', '??' → '??' с цветом."""
    if card == "??":
        return f"{C_HIDDEN}[??]{C_RESET}"
    suit_char = SUIT_MAP.get(card[-1], card[-1])
    val  = card[:-1]
    # Красные масти — красным, чёрные — белым
    if card[-1] in ("H", "D"):
        color = C_RED_SUIT
    else:
        color = C_BLACK_SUIT
    return f"{color}[{val}{suit_char}]{C_RESET}"

def pretty_hand(hand: list) -> str:
    return "  ".join(pretty_card(c) for c in hand)

STATUS_LABELS = {
    "waiting": ("ожидает",    C_WAITING),
    "acting":  (">>> ХОД <<<", C_ACTING),
    "stand":   ("стоп",       C_STAND),
    "bust":    ("ПЕРЕБОР",    C_BUST),
    "win":     ("ПОБЕДА  +",  C_WIN),
    "lose":    ("проигрыш -", C_LOSE),
    "push":    ("ничья",      C_PUSH),
}

def render(s: dict):
    """Очищает экран и рисует текущее состояние игры."""
    print("\033[2J\033[H", end="")   # очистить терминал
    clear()

    phase_labels = {
        "lobby":   ("Лобби — ждём игроков",  C_PHASE_LOBBY),
        "betting": ("Фаза ставок",           C_PHASE_BETTING),
        "playing": ("Идёт игра",             C_PHASE_PLAYING),
        "results": ("Итоги раунда",          C_PHASE_RESULTS),
    }
    phase_text, phase_color = phase_labels.get(s['phase'], (s['phase'], C_RESET))

    print(f"{C_BORDER}{'=' * 55}{C_RESET}")
    print(f"{C_TITLE}  БЛЕКДЖЕК{C_RESET}  |  {phase_color}{phase_text}{C_RESET}")
    print(f"{C_BORDER}{'=' * 55}{C_RESET}")

    # ── Рука дилера ─────────────────────────────────────────
    print(f"\n  {C_DEALER}ДИЛЕР:{C_RESET}  {pretty_hand(s['dealer_hand'])}   ({C_DEALER}{s['dealer_total']}{C_RESET})")
    print()

    # ── Игроки ──────────────────────────────────────────────
    for pid in s["order"]:
        p    = s["players"][pid]
        is_me = (pid == s["my_id"])
        is_host = (pid == s["host"])

        me_str   = f" {C_ME}(ты){C_RESET}" if is_me else ""
        host_str = f" {C_HOST}[ХОСТ]{C_RESET}" if is_host else ""

        name_color = C_ME if is_me else C_NAME
        lbl_text, lbl_color = STATUS_LABELS.get(p["status"], (p["status"], C_RESET))

        print(f"  {name_color}{p['name']}{C_RESET}{me_str}{host_str}")
        print(f"    {C_CREDITS}Кредиты: {p['credits']}{C_RESET}  |  {C_BET}Ставка: {p['bet']}{C_RESET}  |  {lbl_color}{lbl_text}{C_RESET}")
        if p["hand"]:
            print(f"    Карты:  {pretty_hand(p['hand'])}   ({C_CREDITS}{p['total']}{C_RESET})")
        print()

    # ── Итоги раунда (показываем только когда фаза results) ─
    if s["phase"] == "results":
        _print_results(s)

    # ── Подсказка по доступным командам ─────────────────────
    print(f"{C_BORDER}{'-' * 55}{C_RESET}")
    _print_hint(s)
    print()


def _print_results(s: dict):
    """
    Рисует красивую таблицу итогов раунда.
    Вызывается только когда phase == 'results'.
    """
    RESULT_STYLE = {
        "win":  ("🏆", "ПОБЕДА",   "+", C_RES_WIN),
        "lose": ("💸", "ПРОИГРЫШ", "-", C_RES_LOSE),
        "bust": ("💥", "ПЕРЕБОР",  "-", C_RES_BUST),
        "push": ("🤝", "НИЧЬЯ",    " ", C_RES_PUSH),
    }

    print(f"\n{C_BORDER}{'=' * 55}{C_RESET}")
    print(f"{C_TITLE}  ИТОГИ РАУНДА{C_RESET}")
    print(f"{C_BORDER}{'=' * 55}{C_RESET}")

    for pid in s["order"]:
        p = s["players"][pid]
        icon, word, sign, color = RESULT_STYLE.get(p["status"], ("?", p["status"], "", C_RESET))

        if p["status"] in ("lose", "bust"):
            delta = p["bet"]
        elif p["status"] == "win":
            delta = p["bet"]
        else:
            delta = 0

        me = f" {C_ME}(ты){C_RESET}" if pid == s["my_id"] else ""

        print(f"  {icon}  {color}{word:<10}{C_RESET}  {C_NAME}{p['name']}{C_RESET}{me}")
        if delta > 0:
            print(f"             {C_BET}Ставка: {p['bet']}{C_RESET}  →  {color}{sign}{delta} кр.{C_RESET}  |  {C_CREDITS}Кредиты: {p['credits']}{C_RESET}")
        else:
            print(f"             {C_BET}Ставка: {p['bet']}{C_RESET}  →  {C_HINT}без изменений{C_RESET}  |  {C_CREDITS}Кредиты: {p['credits']}{C_RESET}")
        print()

    print(f"{C_BORDER}{'=' * 55}{C_RESET}")
    print()


def _print_hint(s: dict):
    """Печатает подсказку о том, что можно сделать прямо сейчас."""
    pid   = s["my_id"]
    phase = s["phase"]

    if phase == "lobby":
        if pid == s["host"]:
            print(f"  {C_HINT}Введите{C_RESET}  {C_HINT_CMD}start{C_RESET}  {C_HINT}— чтобы начать игру{C_RESET}")
        else:
            print(f"  {C_HINT}Ждём, пока хост начнёт игру...{C_RESET}")

    elif phase == "betting":
        p = s["players"].get(pid, {})
        if p.get("bet", 0) == 0:
            print(f"  {C_HINT}Введите{C_RESET}  {C_HINT_CMD}bet <сумма>{C_RESET}  {C_HINT}— сделать ставку{C_RESET}")
            print(f"  {C_HINT}Пример:{C_RESET}  {C_HINT_CMD}bet 100{C_RESET}")
        else:
            print(f"  {C_HINT}Ставка сделана:{C_RESET} {C_BET}{p['bet']}{C_RESET}. {C_HINT}Ждём остальных...{C_RESET}")

    elif phase == "playing":
        if s["current"] == pid:
            print(f"  {C_ACTING}Твой ход!{C_RESET}")
            print(f"  {C_HINT_CMD}hit{C_RESET}   {C_HINT}— взять ещё карту{C_RESET}")
            print(f"  {C_HINT_CMD}stand{C_RESET} {C_HINT}— остановиться{C_RESET}")
        else:
            cur = s["players"].get(s["current"], {})
            print(f"  {C_HINT}Ход игрока:{C_RESET} {C_NAME}{cur.get('name','?')}{C_RESET}. {C_HINT}Ждём...{C_RESET}")

    elif phase == "results":
        if pid == s["host"]:
            print(f"  {C_HINT}Введите{C_RESET}  {C_HINT_CMD}start{C_RESET}  {C_HINT}— сыграть ещё раунд{C_RESET}")
        else:
            print(f"  {C_HINT}Ждём, пока хост начнёт новый раунд...{C_RESET}")


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
            print(f"  {C_LOSE}Ошибка: сумма должна быть числом, например:{C_RESET}  {C_HINT_CMD}bet 100{C_RESET}")
            return None

    print(f"  {C_LOSE}Неизвестная команда:{C_RESET} {text.strip()}")
    return None


# =============================================================
# ПРОВЕРКА БАЛАНСА (автовыход при нуле кредитов)
# =============================================================

def check_balance_and_exit(msg: dict):
    """
    Проверяет баланс текущего игрока.
    Если кредиты закончились (или игрока удалили из списка),
    выводит сообщение и принудительно закрывает процесс.
    """
    global my_id
    if my_id is None:
        return

    my_player = msg["players"].get(my_id)

    if my_player is None or my_player.get("credits", 1) <= 0:
        print(f"\n{C_BORDER}{'=' * 55}{C_RESET}")
        print(f"  {C_RES_BUST}У вас закончились кредиты! Вы вылетели из игры.{C_RESET}")
        print(f"P.S. можешь пойти в наш банк - tochno-ne-naebalovo.com и взять микрозайм со ставкой 200%")
        print(f"{C_BORDER}{'=' * 55}{C_RESET}")
        sys.stdout.flush()
        time.sleep(3)
        os._exit(0)


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
            name = input(f"  {C_HINT}Введите ваше имя:{C_RESET} ").strip() or f"Player{my_id}"
            await ws.send(json.dumps({"cmd": "join", "name": name}))

        elif msg["type"] == "state":
            last_state = msg
            render(msg)
            check_balance_and_exit(msg)


async def input_loop():
    """
    Читает строки из терминала и кладёт их в очередь.
    Работает в отдельном потоке, чтобы не блокировать asyncio.
    """
    loop = asyncio.get_event_loop()
    while True:
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
    os.system('cls' if os.name == 'nt' else 'clear')


# =============================================================
# ТОЧКА ВХОДА
# =============================================================

async def main():
    clear()
    global input_queue
    input_queue = asyncio.Queue()

    print(f"{C_HINT}Подключаемся к{C_RESET} {C_CREDITS}{SERVER}{C_RESET} {C_HINT}...{C_RESET}")

    try:
        async with websockets.connect(SERVER) as ws:
            print(f"{C_WIN}Подключено!{C_RESET}\n")
            # Запускаем все три задачи параллельно
            await asyncio.gather(
                receive_loop(ws),
                input_loop(),
                send_loop(ws),
            )
    except ConnectionRefusedError:
        print(f"\n{C_LOSE}Ошибка: не удалось подключиться к серверу.{C_RESET}")
        print(f"{C_HINT}Убедитесь, что сервер запущен:{C_RESET}  {C_HINT_CMD}python server.py{C_RESET}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{C_HINT}Выход...{C_RESET}")
        sys.exit(0)
