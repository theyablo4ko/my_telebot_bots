# =============================================================
# СЕРВЕР БЛЕКДЖЕКА
# =============================================================
# Запуск:  python server.py
# Порт:    берётся из переменной окружения PORT (Render задаёт сам)
#          если PORT не задан — используем 8765 (для локального запуска)
# =============================================================

import asyncio
import json
import random
import websockets
import datetime
import os


# =============================================================
# КОЛОДА
# =============================================================

def new_deck():
    suits  = ["S", "H", "D", "C"]
    values = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    deck = [v + s for s in suits for v in values]
    random.shuffle(deck)
    return deck


def card_value(card: str) -> int:
    v = card[:-1]
    if v in ("J", "Q", "K"):
        return 10
    if v == "A":
        return 11
    return int(v)


def hand_total(cards: list) -> int:
    total = sum(card_value(c) for c in cards)
    aces  = sum(1 for c in cards if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


# =============================================================
# СОСТОЯНИЕ ИГРЫ
# =============================================================

state = {
    "phase": "lobby",
    "host": None,
    "order": [],
    "players": {},
    "dealer_hand": [],
    "current": None,
    "deck": [],
}

connections: dict = {}
_next_id = 0

def make_id() -> str:
    global _next_id
    _next_id += 1
    return str(_next_id)


# =============================================================
# ОТПРАВКА ДАННЫХ
# =============================================================

def build_snapshot(viewer_id: str) -> dict:
    hide_dealer = state["phase"] == "playing"

    dealer_visible = (
        [state["dealer_hand"][0], "??"] if hide_dealer and len(state["dealer_hand"]) >= 2
        else state["dealer_hand"]
    )

    players_out = {}
    for pid, p in state["players"].items():
        players_out[pid] = {
            "name":    p["name"],
            "credits": p["credits"],
            "bet":     p["bet"],
            "hand":    p["hand"],
            "total":   hand_total(p["hand"]),
            "status":  p["status"],
        }

    return {
        "type":          "state",
        "my_id":         viewer_id,
        "phase":         state["phase"],
        "host":          state["host"],
        "order":         state["order"],
        "current":       state["current"],
        "players":       players_out,
        "dealer_hand":   dealer_visible,
        "dealer_total":  hand_total(state["dealer_hand"]) if not hide_dealer else "?",
    }


async def broadcast():
    for pid, ws in list(connections.items()):
        try:
            await ws.send(json.dumps(build_snapshot(pid)))
        except Exception:
            pass


# =============================================================
# ЛОГИКА РАУНДОВ
# =============================================================

def draw() -> str:
    if len(state["deck"]) < 15:
        state["deck"] = new_deck()
    return state["deck"].pop()


async def start_betting():
    state["phase"]       = "betting"
    state["dealer_hand"] = []
    state["current"]     = None
    state["deck"]        = new_deck()
    for p in state["players"].values():
        p["hand"]   = []
        p["bet"]    = 0
        p["status"] = "waiting"
    await broadcast()


async def try_start_playing():
    all_bet = all(state["players"][pid]["bet"] > 0 for pid in state["order"])
    if not all_bet:
        return

    for pid in state["order"]:
        state["players"][pid]["hand"] = [draw(), draw()]

    state["dealer_hand"] = [draw(), draw()]
    state["phase"]       = "playing"

    await give_turn(state["order"][0])
    await broadcast()


async def give_turn(pid: str):
    state["current"] = pid
    state["players"][pid]["status"] = "acting"


async def next_turn():
    order   = state["order"]
    current = state["current"]

    if current not in order:
        await dealer_turn()
        return

    idx = order.index(current)
    nxt = None
    for i in range(idx + 1, len(order)):
        if state["players"][order[i]]["status"] == "waiting":
            nxt = order[i]
            break

    if nxt:
        await give_turn(nxt)
        await broadcast()
    else:
        await dealer_turn()


async def dealer_turn():
    state["current"] = None
    while hand_total(state["dealer_hand"]) < 17:
        state["dealer_hand"].append(draw())
    await resolve()


async def resolve():
    state["phase"] = "results"
    d_total = hand_total(state["dealer_hand"])
    d_bust  = d_total > 21

    for p in state["players"].values():
        if p["status"] == "bust":
            p["credits"] -= p["bet"]
            continue

        p_total = hand_total(p["hand"])

        if d_bust or p_total > d_total:
            p["status"]  = "win"
            p["credits"] += p["bet"]
        elif p_total < d_total:
            p["status"]  = "lose"
            p["credits"] -= p["bet"]
        else:
            p["status"]  = "push"

    await broadcast()


# =============================================================
# ОБРАБОТКА КОМАНД
# =============================================================

async def handle(pid: str, msg: dict):
    cmd = msg.get("cmd")

    if cmd == "join":
        name = msg.get("name", f"Player{pid}")
        state["players"][pid] = {
            "name":    name,
            "credits": 1000,
            "bet":     0,
            "hand":    [],
            "status":  "waiting",
        }
        state["order"].append(pid)
        if state["host"] is None:
            state["host"] = pid
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [join]  {name}  (id={pid})  host={state['host']}")
        await broadcast()

    elif cmd == "start":
        if pid != state["host"]:
            return
        if state["phase"] not in ("lobby", "results"):
            return
        await start_betting()

    elif cmd == "bet":
        if state["phase"] != "betting":
            return
        amount = int(msg.get("amount", 0))
        p = state["players"][pid]
        if amount <= 0 or amount > p["credits"]:
            return
        p["bet"] = amount
        await broadcast()
        await try_start_playing()

    elif cmd == "hit":
        if state["phase"] != "playing" or state["current"] != pid:
            return
        p = state["players"][pid]
        p["hand"].append(draw())
        if hand_total(p["hand"]) > 21:
            p["status"] = "bust"
            await next_turn()
        else:
            await broadcast()

    elif cmd == "stand":
        if state["phase"] != "playing" or state["current"] != pid:
            return
        state["players"][pid]["status"] = "stand"
        await next_turn()


# =============================================================
# ПОДКЛЮЧЕНИЕ / ОТКЛЮЧЕНИЕ
# =============================================================

async def on_connect(ws):
    pid = make_id()
    connections[pid] = ws
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [conn]  новое соединение  id={pid}")

    await ws.send(json.dumps({"type": "welcome", "your_id": pid}))

    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
                await handle(pid, data)
            except json.JSONDecodeError:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [warn]  некорректный JSON от {pid}")
    finally:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [leave]  отключился id={pid}")
        connections.pop(pid, None)

        if pid in state["players"]:
            print(f"        ({state['players'][pid]['name']} покинул игру)")
            del state["players"][pid]

        if pid in state["order"]:
            state["order"].remove(pid)

        if state["host"] == pid:
            state["host"] = state["order"][0] if state["order"] else None

        if state["current"] == pid and state["phase"] == "playing":
            await next_turn()
        else:
            await broadcast()


# =============================================================
# ТОЧКА ВХОДА
# =============================================================

async def main():
    # Render передаёт порт через переменную окружения PORT.
    # int(...) преобразует строку "10000" в число 10000.
    # or 8765 — если переменной нет (локальный запуск), используем 8765.
    port = int(os.environ.get("PORT", 8765))

    # "0.0.0.0" означает "принимай подключения с любого адреса".
    # На локальной машине это тоже работает нормально.
    host = "0.0.0.0"

    print("=" * 45)
    print("  Блекджек-сервер запущен")
    print(f"  Слушаем: {host}:{port}")
    print("=" * 45)

    async with websockets.serve(on_connect, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
