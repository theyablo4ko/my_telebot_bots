"""
🤖 Party Bot — демотиваторы, шакал-качество и стикеры
Создано с любовью для партии 🎉
"""

import os
import regex
from io import BytesIO
from html import escape

from PIL import Image, ImageDraw, ImageFont
import telebot

# =============================================================================
# ⚙️ КОНФИГУРАЦИЯ
# =============================================================================

# Загрузка токена
with open('info/token', 'r', encoding='utf-8') as f:
	BOT_TOKEN = f.readline().strip()

bot = telebot.TeleBot(BOT_TOKEN)

# Списки команд
COMMANDS = {
	'demotivator': ['/make_demotivator', '/demotivator', '/dm'],
	'poor_quality': ['/do_a_poor_quality', '/poor', '/pq'],
	'sticker': ['/make_sticker', '/sticker', '/st'],
}

# Списки доступа
ACCESS = {
	'admins': {'6555912810', '5081309603', '8204500319'},
	'blacklist': {'7167194461', '8581093935', '-1003754441670'},
	'selected': {'777000'},
}

# ID для отправки в супергруппу
SUPERGROUP_ID = '-1003637655262'

# Пути к файлам
PATHS = {
	'font': './font/minecraft.ttf',
	'start_image': './images/templates/start_image.png',
	'info_image': 'images/templates/info_image.jpg',
	'users_file': 'info/users.txt',
	'output_dir': 'images',
	'poor_quality_dir': 'images/poor_quality',
	'tmp_dir': 'tmp',
}

# Параметры обработки изображений
IMAGE_CONFIG = {
	'canvas_size': (1080, 1080),
	'image_max_size': (800, 600),
	'min_good_size': 500,
	'sticker_size': (512, 512),
	'sticker_max_kb': 512,
	'demotivator': {
		'title_font_size': 50,
		'subtitle_font_size': 40,
		'title_max_len': 30,
		'subtitle_max_len': 50,
	},
}


# =============================================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================


def get_user_info(message: telebot.types.Message) -> tuple[int, str, str]:
	"""
	Безопасно извлекает данные пользователя из сообщения.

	Returns:
		tuple: (user_id, username, first_name)
	"""
	if message.from_user:
		uid = message.from_user.id
		uname = message.from_user.username or f"user_{uid}"
		fname = message.from_user.first_name or "User"
	else:
		uid = message.chat.id
		uname = message.chat.username or "channel"
		fname = message.chat.title or "Channel"
	return uid, uname, fname


def check_access(message: telebot.types.Message) -> bool:
	"""Проверяет, есть ли у пользователя доступ к боту."""
	uid, _, _ = get_user_info(message)
	if str(uid) in ACCESS['blacklist'] and str(uid) not in ACCESS['selected']:
		return False
	return True


def is_private_chat(message: telebot.types.Message) -> bool:
	"""Проверяет, является ли чат личным сообщением."""
	return message.chat.type == 'private'


def has_command(message: telebot.types.Message, cmd_list: list[str]) -> bool:
	"""Проверяет наличие команды в тексте или подписи к сообщению."""
	caption = message.caption or ""
	text = message.text or ""
	return any(cmd in caption or cmd in text for cmd in cmd_list)


def cleanup_chat(message: telebot.types.Message, bot_msg_ids: list[int] | None = None) -> None:
	"""
	Удаляет исходное сообщение пользователя и служебные сообщения бота.
	Бот должен быть администратором с правом удаления сообщений.
	"""
	try:
		bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
		if bot_msg_ids:
			for msg_id in bot_msg_ids:
				try:
					bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
				except Exception as e:
					print(f"⚠️ Не удалось удалить сообщение бота {msg_id}: {e}")
	except Exception as e:
		print(f"⚠️ Не удалось очистить чат (бот должен быть админом): {e}")


def send_to_supergroup(message: telebot.types.Message, output_path: str | None = None, photo: any = None) -> None:
	"""Отправляет результат обработки в супергруппу для логирования."""
	try:
		uid, uname, fname = get_user_info(message)
		caption = (
			f"User ID: <code>{escape(str(uid))}</code>\n"
			f"User Name: <a href='t.me/{uname or ''}'>{escape(fname)}</a>"
		)

		def send_photo_file(photo_src):
			bot.send_photo(chat_id=SUPERGROUP_ID, photo=photo_src, caption=caption, parse_mode='HTML')

		if output_path:
			with open(output_path, 'rb') as f:
				send_photo_file(f)
		if photo:
			if isinstance(photo, str):
				with open(photo, 'rb') as f:
					send_photo_file(f)
			else:
				send_photo_file(photo)
	except Exception as e:
		print(f"❌ Ошибка отправки в супергруппу: {e}")


def extract_emojis(message: telebot.types.Message, default: str = "👍", max_count: int = 20) -> str:
	"""Извлекает эмодзи из подписи к сообщению."""
	try:
		caption = message.caption or ""
		pattern = regex.compile(r"\p{Emoji}")
		matches = pattern.findall(caption)
		return "".join(matches[:max_count]) if matches else default
	except Exception:
		return default


def format_emojis_for_api(emojis: str, max_count: int = 20) -> list[str]:
	"""Конвертирует строку эмодзи в список для Telegram API."""
	if not emojis:
		return ["👍"]
	pattern = regex.compile(r"\p{Emoji}")
	emoji_list = pattern.findall(emojis)
	return emoji_list[:max_count] or ["👍"]


def prepare_sticker_image(in_path: str, out_path: str) -> None:
	"""Конвертирует изображение в формат стикера Telegram (512x512 PNG, ≤512KB)."""
	with Image.open(in_path) as img:
		img = img.convert("RGBA")
		img.thumbnail(IMAGE_CONFIG['sticker_size'], Image.LANCZOS)

		bg = Image.new("RGBA", IMAGE_CONFIG['sticker_size'], (0, 0, 0, 0))
		offset = ((512 - img.width) // 2, (512 - img.height) // 2)
		bg.paste(img, offset, img)
		bg.save(out_path, "PNG", optimize=True)

		# Сжатие если файл > 512 KB
		max_size = IMAGE_CONFIG['sticker_max_kb'] * 1024
		if os.path.getsize(out_path) > max_size:
			for level in [95, 85, 75, 65]:
				bg.save(out_path, "PNG", optimize=True, compress_level=level)
				if os.path.getsize(out_path) <= max_size:
					break


def parse_demotivator_text(message: telebot.types.Message) -> list[str]:
	"""
	Извлекает и валидирует текст для демотиватора из подписи.
	Возвращает [заголовок, подзаголовок].
	"""
	caption = message.caption or ""
	all_commands = COMMANDS['demotivator'] + COMMANDS['poor_quality'] + COMMANDS['sticker']

	# Удаляем команды из текста
	clean_caption = caption
	for cmd in all_commands:
		clean_caption = clean_caption.replace(cmd, '').strip()

	lines = [line.strip() for line in clean_caption.split('\n') if line.strip()]
	cfg = IMAGE_CONFIG['demotivator']

	def validate(text: str, max_len: int, line_num: int) -> str:
		if len(text) > max_len:
			if is_private_chat(message):
				bot.send_message(
					message.chat.id,
					f'brooo, too many letters in {"first" if line_num == 1 else "second"} line...... (((('
				)
			return 'too many letters'
		return text

	if len(lines) >= 2:
		return [validate(lines[0], cfg['title_max_len'], 1), validate(lines[1], cfg['subtitle_max_len'], 2)]
	elif len(lines) == 1:
		return [validate(lines[0], cfg['title_max_len'], 1), '  ']
	return ['', '']


def parse_shakal_params(caption: str, cmd_list: list[str]) -> tuple[bool, int]:
	"""
	Извлекает процент деградации из подписи.
	Returns: (найдена_ли_команда, процент_0_100)
	"""
	if not caption:
		return False, None

	found_cmd = None
	for cmd in cmd_list:
		if cmd in caption:
			found_cmd = cmd
			parts = caption.replace(cmd, '', 1).strip().split()
			break

	if not found_cmd:
		return False, None

	if parts:
		num = parts[0].rstrip('%')
		if num.lstrip('-').isdigit():
			return True, max(0, min(100, int(num)))
	return True, 100  # Команда есть, но числа нет — дефолт 100%


def get_degradation_params(percent: int) -> tuple[int, int]:
	"""Конвертирует процент в параметры JPEG-деградации (quality, iterations)."""
	percent = max(0, min(100, percent))
	quality = max(1, 95 - int(percent * 0.94))
	iterations = max(1, int(percent))
	return quality, iterations


def load_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
	"""Загружает шрифты для демотиватора с fallback на дефолтные."""
	try:
		title = ImageFont.truetype(PATHS['font'], IMAGE_CONFIG['demotivator']['title_font_size'])
		subtitle = ImageFont.truetype(PATHS['font'], IMAGE_CONFIG['demotivator']['subtitle_font_size'])
		return title, subtitle
	except Exception as e:
		print(f"⚠️ Ошибка загрузки шрифта: {e}. Используется дефолтный.")
		return ImageFont.load_default(), ImageFont.load_default()


def save_user_id(user_id: int, user_name: str) -> None:
	"""Сохраняет ID нового пользователя в файл."""
	try:
		with open(PATHS['users_file'], 'r') as f:
			if str(user_id) in f.read():
				return
		with open(PATHS['users_file'], 'a') as f:
			f.write(f"{user_id}:{user_name}\n")
		print(f"✅ User {user_id} saved to users.txt")
	except Exception as e:
		print(f"⚠️ Error saving user {user_id} {e}")


def ensure_dirs() -> None:
	"""Создаёт необходимые директории."""
	for path in [PATHS['output_dir'], PATHS['poor_quality_dir'], PATHS['tmp_dir']]:
		os.makedirs(path, exist_ok=True)


# =============================================================================
# 🎮 ОБРАБОТЧИКИ КОМАНД
# =============================================================================


@bot.message_handler(commands=['start'])
def cmd_start(message: telebot.types.Message) -> None:
	"""Обработчик команды /start"""
	if not check_access(message):
		if str(message.from_user.id) not in ACCESS['selected']:
			bot.send_message(message.chat.id,
							 f'Великий партия выгнать ты {message.from_user.id}, плохой тайвань шпиен.')
		return

	save_user_id(message.from_user.id, message.from_user.username)
	uid, uname, fname = get_user_info(message)

	mention = f"@{uname}" if uname and uname != 'None' else "незнакомец"
	caption = (
		f"Партия приветсвовать тебя, {mention}! 🎉\n"
		f"Данный бот может много чего предложить. Напиши /help для подробностей.\n"
		f"(партия будет доволен, если ты подаришь звезда и зайдешь в канал↓↓↓)\n"
		f"https://t.me/+r2p3l1QPGMM0Nzcy"
	)

	try:
		with open(PATHS['start_image'], 'rb') as f:
			bot.send_photo(message.chat.id, f, caption=caption)
	except Exception as e:
		bot.send_message(message.chat.id, "❌ Ошибка загрузки стартового изображения")
		print(f"❌ Start error: {e}")


@bot.message_handler(commands=['help', 'h', '?'])
def cmd_help(message: telebot.types.Message) -> None:
	"""Обработчик команды /help"""
	if not check_access(message):
		if str(message.from_user.id) not in ACCESS['selected']:
			bot.send_message(message.chat.id, 'Партия запретить тебе смотреть /help.')
		return

	help_text = (
		"📜 **Команды партии:**\n\n"
		"🖼️ **Демотиватор:**\n"
		"`/demotivator`, `/dm`, `/make_demotivator` — создать демотиватор\n"
		"Текст в подписи к фото (2 строки)\n\n"
		"🗑️ **Шакал-качество:**\n"
		"`/poor`, `/pq`, `/do_a_poor_quality` [0-100%] — зашакалить изображение\n"
		"Пример: `/poor 50` или `/poor 10%`\n\n"
		"🎨 **Стикеры:**\n"
		"`/sticker`, `/st`, `/make_sticker` — создать стикер\n"
		"Эмодзи в подписи будут привязаны к стикеру\n\n"
		"🧹 **Авто-очистка:**\n"
		"Бот удаляет исходное сообщение и оставляет только результат!\n\n"
		"💬 **Режимы работы:**\n"
		"• В ЛС — бот отвечает на все сообщения\n"
		"• В группах — бот реагирует только на команды"
	)
	bot.send_message(message.chat.id, help_text, parse_mode='Markdown')


@bot.message_handler(commands=['info'])
def cmd_info(message: telebot.types.Message) -> None:
	"""Обработчик команды /info"""
	caption = (
		'этот бот был создан давным-давно для того, чтобы радовать людей и создателя '
		'(задоньте пж, разраб тоже есть хочет)↓↓↓\n'
		'https://t.me/+r2p3l1QPGMM0Nzcy'
	)
	try:
		with open(PATHS['info_image'], 'rb') as img:
			bot.send_photo(message.chat.id, photo=img, caption=caption)
	except Exception as e:
		print(f'❌ Error with info message: {e}')


@bot.message_handler(content_types=['text'])
def handle_text(message: telebot.types.Message) -> None:
	"""Обработчик текстовых сообщений (только в ЛС)"""
	# Игнорируем команды — они обрабатываются отдельно
	if message.text and message.text.startswith('/'):
		return

	if not is_private_chat(message):
		return  # В группах игнорируем обычный текст

	if check_access(message):
		print(f'[ЛС] {message.text} \n@{message.from_user.username} {message.from_user.id}')
		bot.send_message(message.chat.id, 'Партия учтет твой мысль.')
	elif str(message.from_user.id) not in ACCESS['selected']:
		bot.send_message(message.chat.id, f'Великий партия выгнать ты {message.from_user.id}, эхо не работать.')
	else:
		print('🌟 Сообщение от избранного.')


# =============================================================================
# 🖼️ ОБРАБОТЧИКИ ФОТО
# =============================================================================


@bot.message_handler(content_types=['photo'], func=lambda m: has_command(m, COMMANDS['demotivator']))
def make_demotivator(message: telebot.types.Message) -> None:
	"""Создаёт демотиватор из фото с текстом в подписи."""
	if not check_access(message):
		if str(message.from_user.id) not in ACCESS['selected']:
			bot.send_message(message.chat.id, 'Великий партия выгнать ты, плохой тайвань шпиен.')
		return

	bot_msg_ids = []
	uid, uname, fname = get_user_info(message)

	try:
		# Уведомление только в ЛС
		if is_private_chat(message):
			temp = bot.send_message(message.chat.id, "🎨 Партия делает демотиватор...")
			bot_msg_ids.append(temp.message_id)

		# Загрузка и подготовка изображения
		file_info = bot.get_file(message.photo[-1].file_id)
		downloaded = bot.download_file(file_info.file_path)

		user_img_path = f"{PATHS['output_dir']}/dm_{uid}_{message.message_id}.jpg"
		with open(user_img_path, 'wb') as f:
			f.write(downloaded)

		original = Image.open(user_img_path).convert("RGB")
		canvas = Image.new('RGB', IMAGE_CONFIG['canvas_size'], color=(0, 0, 0))
		draw = ImageDraw.Draw(canvas)

		title_font, subtitle_font = load_fonts()

		# Обработка изображения
		if original.width < IMAGE_CONFIG['min_good_size'] or original.height < IMAGE_CONFIG['min_good_size']:
			user_img = original.resize(IMAGE_CONFIG['image_max_size'], Image.NEAREST)
		else:
			user_img = original.convert("RGBA")
			user_img.thumbnail(IMAGE_CONFIG['image_max_size'], Image.LANCZOS)

		text = parse_demotivator_text(message)

		if user_img.mode != "RGBA":
			user_img = user_img.convert("RGBA")

		# Центрирование изображения на холсте
		img_w, img_h = user_img.size
		x = (1080 - img_w) // 2
		y = (1080 - img_h) // 2 - 50
		gap = 10

		# Белая рамка
		draw.rectangle(
			((x - gap, y - gap), (x + img_w + gap, y + img_h + gap)),
			outline='white', width=4
		)
		canvas.paste(user_img, (x, y), user_img)

		# Текст — заголовок
		bbox = draw.textbbox((0, 0), text[0], font=title_font)
		tx = (1080 - (bbox[2] - bbox[0])) // 2
		draw.text((tx, y + img_h + 30), text[0], fill=(255, 255, 255), font=title_font)

		# Текст — подзаголовок
		bbox1 = draw.textbbox((0, 0), text[1], font=subtitle_font)
		tx1 = (1080 - (bbox1[2] - bbox1[0])) // 2
		draw.text((tx1, y + img_h + 90), text[1], fill=(255, 255, 255), font=subtitle_font)

		# Сохранение результата
		output_path = f"{PATHS['output_dir']}/res_dm_{uid}_{message.message_id}.jpg"
		canvas.save(output_path, "JPEG", quality=95)

		# 🧹 Очистка чата (только в группах)
		if not is_private_chat(message):
			cleanup_chat(message, bot_msg_ids)

		# Отправка результата
		with open(output_path, 'rb') as photo:
			bot.send_photo(chat_id=message.chat.id, photo=photo)

		# Логирование в супергруппу
		send_to_supergroup(message, output_path=output_path)

		# Удаление временных файлов
		os.remove(output_path)
		os.remove(user_img_path)

	except Exception as e:
		print(f"❌ Demotivator Error: {e}")
		if not is_private_chat(message):
			cleanup_chat(message, bot_msg_ids)
		bot.send_message(message.chat.id, "❌ Партия сломалась при создании демотиватора.")


@bot.message_handler(content_types=['photo'], func=lambda m: has_command(m, COMMANDS['poor_quality']))
def make_poor_quality(message: telebot.types.Message) -> None:
	"""Применяет эффект «шакал-качество» к изображению."""
	if not check_access(message):
		if str(message.from_user.id) not in ACCESS['selected']:
			bot.send_message(message.chat.id, 'Партия запретить тебе делать шакалы.')
		return

	bot_msg_ids = []
	uid, uname, fname = get_user_info(message)
	caption = message.caption or ""

	is_cmd, percent = parse_shakal_params(caption, COMMANDS['poor_quality'])
	if not is_cmd:
		return

	quality, iterations = get_degradation_params(percent)

	# Уведомление только в ЛС
	if percent != 100 and is_private_chat(message):
		temp = bot.send_message(
			message.chat.id,
			f"🔧 Партия шакалит на {percent}%\nJPEG quality: {quality}, итераций: {iterations}"
		)
		bot_msg_ids.append(temp.message_id)

	try:
		file_info = bot.get_file(message.photo[-1].file_id)
		downloaded = bot.download_file(file_info.file_path)

		user_img_path = f"{PATHS['poor_quality_dir']}/pq_{uid}_{message.message_id}.jpg"
		with open(user_img_path, 'wb') as f:
			f.write(downloaded)

		# Обработка изображения
		img = Image.open(user_img_path).convert("RGB")
		img = img.resize(IMAGE_CONFIG['image_max_size'], Image.NEAREST)
		img = img.convert("P", palette=Image.ADAPTIVE, colors=32).convert("RGB")

		for _ in range(iterations):
			buf = BytesIO()
			img.save(buf, "JPEG", quality=quality)
			buf.seek(0)
			img = Image.open(buf).convert("RGB")

		img = img.resize(IMAGE_CONFIG['image_max_size'], Image.NEAREST)

		# 🧹 Очистка чата (только в группах)
		if not is_private_chat(message):
			cleanup_chat(message, bot_msg_ids)

		# Отправка результата
		bot.send_photo(chat_id=message.chat.id, photo=img)
		send_to_supergroup(message, photo=img)

		os.remove(user_img_path)

	except Exception as e:
		print(f"❌ Poor Quality Error: {e}")
		if not is_private_chat(message):
			cleanup_chat(message, bot_msg_ids)
		bot.send_message(message.chat.id, "❌ Партия не смогла зашакалить фото.")


@bot.message_handler(content_types=['photo'], func=lambda m: has_command(m, COMMANDS['sticker']))
def make_sticker(message: telebot.types.Message) -> None:
	"""Создаёт стикер Telegram из изображения."""
	if not check_access(message):
		if str(message.from_user.id) not in ACCESS['selected']:
			bot.send_message(message.chat.id, 'Партия запретить тебе делать стикеры.')
		return

	bot_msg_ids = []
	uid, uname, fname = get_user_info(message)

	emojis_raw = extract_emojis(message)
	emojis_api = format_emojis_for_api(emojis_raw)
	emojis_display = "".join(emojis_api)

	# Уведомление только в ЛС
	if is_private_chat(message):
		temp = bot.send_message(message.chat.id, f"🎨 Партия делает стикер с эмодзи: {emojis_display}")
		bot_msg_ids.append(temp.message_id)

	try:
		file_info = bot.get_file(message.photo[-1].file_id)
		downloaded = bot.download_file(file_info.file_path)

		raw_path = f"{PATHS['tmp_dir']}/raw_{uid}_{message.message_id}.jpg"
		png_path = f"{PATHS['tmp_dir']}/sticker_{uid}_{message.message_id}.png"

		with open(raw_path, "wb") as f:
			f.write(downloaded)

		prepare_sticker_image(raw_path, png_path)

		bot_username = bot.get_me().username
		pack_name = f"u{uid}_stickers_by_{bot_username}"
		pack_title = f"{fname}'s stickers"

		result = ""
		try:
			with open(png_path, "rb") as st:
				bot.add_sticker_to_set(
					user_id=uid, name=pack_name, emojis=emojis_api, png_sticker=st
				)
			result = f"✅ Стикёр добавлен!\n📦 https://t.me/addstickers/{pack_name}\n🎨 {emojis_display}"
		except telebot.apihelper.ApiException as e:
			err = str(e)
			if "STICKERSET_INVALID" in err or "not found" in err.lower():
				with open(png_path, "rb") as st:
					bot.create_new_sticker_set(
						user_id=uid, name=pack_name, title=pack_title,
						emojis=emojis_api, png_sticker=st, sticker_format="static"
					)
				result = f"✨ Пак создан!\n📦 https://t.me/addstickers/{pack_name}\n🎨 {emojis_display}"
			elif "STICKERS_TOO_MUCH" in err:
				result = "📦 В паке максимум 120 стикеров! Удали старые или создай новый пак."
			else:
				result = f"❌ Ошибка: {e}"

		# 🧹 Очистка чата (только в группах)
		if not is_private_chat(message):
			cleanup_chat(message, bot_msg_ids)

		bot.send_message(message.chat.id, result)
		os.remove(raw_path)
		os.remove(png_path)

	except Exception as e:
		print(f"❌ Sticker Error: {e}")
		if not is_private_chat(message):
			cleanup_chat(message, bot_msg_ids)
		bot.send_message(message.chat.id, "❌ Ошибка стикера.")


@bot.message_handler(
	content_types=['photo'],
	func=lambda m: not any(has_command(m, cmds) for cmds in COMMANDS.values())
)
def handle_photo_no_command(message: telebot.types.Message) -> None:
	"""Обрабатывает фото без команд — показывает подсказку (только в ЛС)."""
	if is_private_chat(message) and check_access(message):
		bot.send_message(
			message.chat.id,
			"📸 Партия получить изображение!\n\n"
			"Чтобы партия что-то сделал, добавь команду в подпись:\n"
			"/demotivator — сделает демотиватор\n"
			"/poor [0-100%] — сделает шакал-качество\n"
			"/sticker — сделает стикер"
		)
	# В группах игнорируем фото без команд


# =============================================================================
# 🚀 ЗАПУСК
# =============================================================================

if __name__ == '__main__':
	print('🤖 @editor_theyablo4ko_bot запущен (ЛС: все, канал: ограниченные)')
	ensure_dirs()
	bot.infinity_polling()
