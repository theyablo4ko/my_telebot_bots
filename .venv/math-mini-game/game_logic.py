from random import *
import re
import os


# ==================== ФУНКЦИИ ДЛЯ КОНФИГА ====================

def parse_config(text):
	"""Парсит текст конфигурации и возвращает словарь"""
	config = {}

	# Извлекаем operations_num
	match = re.search(r'operations_num:\s*(\d+)', text)
	if match:
		config['operations_num'] = int(match.group(1))

	# Извлекаем spread [x, y]
	match = re.search(r'spread:\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]', text)
	if match:
		config['spread'] = [int(match.group(1)), int(match.group(2))]

	return config


def load_config(filepath):
	"""Читает конфигурацию из файла"""
	try:
		with open(filepath, 'r', encoding='utf-8') as f:
			content = f.read()
		return parse_config(content), None
	except FileNotFoundError:
		return None, f"Файл '{filepath}' не найден"
	except Exception as e:
		return None, f"Ошибка чтения: {e}"


# ==================== ФУНКЦИИ ДЛЯ СЛОЖНОСТИ ====================

def load_difficulty(filepath='difficulty.txt'):
	"""Загружает последний уровень сложности из файла"""
	default_diff = {
		'operations_num': 1,
		'spread_min': 1,
		'spread_max': 10
	}

	# Если файла нет - создаём с дефолтными значениями
	if not os.path.exists(filepath):
		save_difficulty(default_diff, filepath)
		return default_diff

	try:
		with open(filepath, 'r', encoding='utf-8') as f:
			content = f.read()

		diff = {}
		lines = content.strip().split('\n')

		for line in lines:
			line = line.strip()
			if ':' in line:
				key, value = line.split(':', 1)
				key = key.strip()
				value = value.strip()
				diff[key] = int(value)

		# Проверяем что все поля есть
		if 'operations_num' in diff and 'spread_min' in diff and 'spread_max' in diff:
			return diff
		else:
			return default_diff

	except:
		return default_diff


def save_difficulty(diff, filepath='difficulty.txt'):
	"""Сохраняет текущий уровень сложности в файл"""
	try:
		with open(filepath, 'w', encoding='utf-8') as f:
			f.write(f"operations_num: {diff['operations_num']}\n")
			f.write(f"spread_min: {diff['spread_min']}\n")
			f.write(f"spread_max: {diff['spread_max']}\n")
		return True
	except:
		return False


def increase_difficulty(diff):
	"""Увеличивает сложность после успешной игры"""
	# Сначала увеличиваем диапазон чисел
	if diff['spread_max'] < 20:
		diff['spread_max'] += 5
		diff['spread_min'] += 2

	# Потом добавляем операции
	elif diff['operations_num'] < 5:
		diff['operations_num'] += 1
		diff['spread_min'] = 1
		diff['spread_max'] = 10

	return diff



# ==================== ФУНКЦИЯ ДЛЯ ПРИМЕРА ====================

def choice_a_exmaple(operations_num=1, spread_between_numbers=[1, 10], number_round=1):
	operations = ['+', '-', '*', '/']

	is_incorrect_example = True

	while is_incorrect_example:
		example = ''

		example += str(randint(spread_between_numbers[0], spread_between_numbers[1]))

		for i in range(operations_num):
			second_number = randint(spread_between_numbers[0], spread_between_numbers[1])
			math_operation = choice(operations)
			example += str(math_operation)
			example += str(second_number)

		# Проверяем что пример корректный (целое число и нет деления на 0)
		try:
			print(example)
			if '/' in example:
				print('/')
				matches = re.findall(r'(\d+)/(\d+)', example)
				correct_division = 0
				for numbers in matches:
					print(int(numbers[0]), int(numbers[1]), (int(numbers[0])) % (int(numbers[1])))
					if ((int(numbers[0]) % int(numbers[1]))) == 0:
						correct_division += 1
				print(correct_division, len(matches))
				if correct_division == (len(matches)):
					print('верное деление')
					is_incorrect_example = False
					return [example, int(result)]
			else:
				result = eval(example)
				if isinstance(result, int) or result == int(result):
					return [example, int(result)]
		except:
			pass
	return [example, 0]


# ==================== ОСНОВНОЙ КОД ====================

# variable
# variable
# variable

classic_game = True
personal_game = False

correct_answer = 0
wrong_answer = 0
round_num = 1
row_correct = 0

game = True

# Загружаем сложность из файла
difficulty = load_difficulty('difficulty.txt')

# variable end
# variable end
# variable end


print(
	"This is a simple math game where you have to quickly write the answer to a math problem after seeing two numbers and a math operation. The faster you write it, the better.")
print("Answer must be only 1 number without dot")
print("Default difficulty may be changed in difficulty.txt")
print(
	f"Current difficulty: operations={difficulty['operations_num']}, spread=[{difficulty['spread_min']}, {difficulty['spread_max']}]")

# Загружаем конфиг (если нужен)
config, error = load_config('config.txt')
# print(config, error)  # Можно закомментировать если не используется


while game:
	print(f'Round {round_num}/∞')

	# Формируем spread из текущей сложности
	spread = [difficulty['spread_min'], difficulty['spread_max']]

	example = choice_a_exmaple(
		operations_num=difficulty['operations_num'],
		spread_between_numbers=spread
	)

	print(f"Example for you: {example[0]}")
	answer = input("please enter your answer: ")

	if answer == 'exit':
		game = False
		print(f"\n=== GAME OVER ===")
		print(f"Your stats(correct | all): {correct_answer} | {round_num}")
		save_difficulty(difficulty, 'difficulty.txt')


	elif answer.isdigit() or (answer.startswith('-') and answer[1:].isdigit()):
		if int(answer) == example[1]:
			correct_answer += 1
			row_correct += 1
			print('well... well... well...')
		else:
			wrong_answer += 1
			row_correct = 0
			print('bad..bad...bad....(breaking)')
			print(f"correct answer: {example[1]}")
	else:
		print("Invalid input! Please enter a number.")
		round_num -= 1  # Не считаем этот раунд

	if row_correct == 5:
		row_correct = 0
		difficulty = increase_difficulty(difficulty)
		print(f'you answered 5 examples correctly in a row. difficulty increased!!! ({difficulty['operations_num']}, [{difficulty['spread_min']}, {difficulty['spread_max']}])')

	round_num += 1



# print(f"Your stats(correct | all): {correct_answer} | {num_of_rounds}")