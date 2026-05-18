import asyncio
import json
import os
import sys
import websockets

# Замени на свой URL после деплоя (например, wss://my-blackjack.koyeb.app)
SERVER_URL = "wss://my-blackjack.koyeb.app"

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

async def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = SERVER_URL

    name = input("Введи свой ник: ").strip()
    print(f"Подключаюсь к {url} ...")
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"name": name}))
            resp = json.loads(await ws.recv())
            if 'error' in resp:
                print(resp['error'])
                return
            print(resp['message'])

            async def listen():
                while True:
                    try:
                        msg = await ws.recv()
                        state = json.loads(msg)
                        show_state(state, name)
                        await handle_action(ws, state, name)
                    except websockets.ConnectionClosed:
                        print("\nСоединение закрыто сервером.")
                        sys.exit(0)

            await listen()
    except Exception as e:
        print(f"Не удалось подключиться: {e}")

def show_state(state, my_name):
    clear()
    print("=" * 40)
    print(f"🃏 Блекджек — {my_name}")
    print(f"Фаза: {state['phase']}")
    if state['current_turn']:
        print(f"Сейчас ход: {state['current_turn']} {'(ваш)' if state['current_turn'] == my_name else ''}")
    # Дилер
    dhand = state.get('dealer_hand', [])
    dscore = state.get('dealer_score')
    if state['phase'] in ('dealer', 'finished') and dscore is not None:
        print(f"Дилер: {', '.join(dhand)} (очки: {dscore})")
    else:
        if dhand:
            print(f"Дилер: [{dhand[0]}, ??]")
        else:
            print("Дилер: карт нет")
    print("-" * 40)
    for pname, pinfo in state['players'].items():
        if pname == my_name or state['phase'] == 'finished':
            print(f"{pname}: {', '.join(pinfo['hand'])} (очки: {pinfo['score']}) | Баланс: {pinfo['balance']} | Ставка: {pinfo['bet']} | Статус: {pinfo['status']}")
        else:
            hidden = ['??' for _ in pinfo['hand']]
            print(f"{pname}: {', '.join(hidden)} | Баланс: {pinfo['balance']} | Ставка: {pinfo['bet']}")
    if state['result']:
        print("\n" + state['result'])

async def handle_action(ws, state, my_name):
    if state['phase'] == 'betting':
        my_info = state['players'][my_name]
        if my_info['bet'] == 0:
            while True:
                try:
                    bet = int(input(f"Ваш баланс: {my_info['balance']}. Введите ставку: "))
                    if 0 < bet <= my_info['balance']:
                        break
                    print("Некорректная сумма")
                except ValueError:
                    print("Введите целое число")
            await ws.send(json.dumps({"action": "bet", "amount": bet}))
        else:
            print("Ожидание ставок других игроков...")
            await asyncio.sleep(2)
    elif state['phase'] == 'playing' and state['current_turn'] == my_name:
        action = input("Ваш ход (put - взять карту, stop - остановиться): ").strip().lower()
        if action in ('put', 'stop'):
            await ws.send(json.dumps({"action": action}))
    elif state['phase'] == 'finished':
        if input("Сыграть ещё? (y/n): ").strip().lower() == 'y':
            await ws.send(json.dumps({"action": "new_round"}))
        else:
            print("Выход из игры. До встречи!")
            sys.exit(0)
    else:
        await asyncio.sleep(1)  # ждём свою очередь

if __name__ == "__main__":
    asyncio.run(main())