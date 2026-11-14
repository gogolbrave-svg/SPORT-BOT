import asyncio
import datetime
import logging 
import os 
import random
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import ClientSession, web
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")

if not BOT_TOKEN:
  raise ValueError("❌ BOT_TOKEN не найден!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

admin_env = os.getenv("ADMIN_ID")
ADMIN_ID = int(admin_env) if admin_env and admin_env.isdigit() else None

class OrderForm(StatesGroup):
  service = State()
  country = State()
  target_location = State()
  target_data = State()
  photos = State()
  urgency = State()
  receipt = State()

class VacancyForm(StatesGroup):
  country = State()
  city_name_age = State()
  parameters = State()
  sports_exp = State()
  photo = State()
  receipt = State()

class SupportForm(StatesGroup):
  reason = State()
  photo = State()

# Базы данных в памяти
USER_ORDERS = {}
KNOWN_USERS = {}
ABANDONED_CHECKOUTS = {}
CARD_DETAILS = []      # Список реквизитов карт/телефонов
CARD_POINTERS = {}     # Индексы для циклического чередования реквизитов по странам
BANNED_USERS = set()   # Множество заблокированных пользователей

router = Router()

# === MIDDLEWARE ДЛЯ ПРОВЕРКИ БАНА ===
@router.message.middleware()
async def ban_middleware(handler, event, data):
  if event.from_user and event.from_user.id in BANNED_USERS:
    return
  return await handler(event, data)

@router.callback_query.middleware()
async def ban_callback_middleware(handler, event, data):
  if event.from_user and event.from_user.id in BANNED_USERS:
    await event.answer("Вы заблокированы в этом боте.", show_alert=True)
    return
  return await handler(event, data)

# === СЛОВАРЬ ВАЛЮТ ДЛЯ СТРАН ===
COUNTRY_CURRENCIES = {
    "Россия": {"code": "RUB", "symbol": "₽"},
    "Беларусь": {"code": "BYN", "symbol": "BYN"},
    "Украина": {"code": "UAH", "symbol": "грн."},
    "Казахстан": {"code": "KZT", "symbol": "₸"},
}

# === КРИПТОСЕТИ И РЕКВИЗИТЫ ===
CRYPTO_NETWORKS = {
    "trc20": {
        "name": "USDT (TRC-20)",
        "address": "TYd1ekJgTHnFfgAVYXsi7689GaG5oZN3Xe",
        "network": "TRC-20",
    },
    "bep20": {
        "name": "USDT (BEP-20)",
        "address": "0x0A6C6634f8FD920a5E9E0d241CD46d6C15377f39",
        "network": "BEP-20",
    },
    "ton": {
        "name": "TON",
        "address": "UQDwk7PZoWr0zHv-BItBEGxnq4uyj81z6BlIw74heDgF-Shd",
        "network": "TON",
    },
    "btc": {
        "name": "Bitcoin (BTC)",
        "address": "bc1qj7xy0645vcza7l3et5s8nuahllua9a439c0795",
        "network": "Bitcoin",
    },
}

# === ФУНКЦИЯ ЧЕРЕДОВАНИЯ РЕКВИЗИТОВ (ROUND-ROBIN) ПО КРУГУ ===
def get_next_card(country: str):
  now = datetime.datetime.now()
  active = []
  for card in CARD_DETAILS:
    if card["country"].lower() == country.lower():
      if card["frozen_until"] and card["frozen_until"] > now:
        continue
      elif card["frozen_until"] and card["frozen_until"] <= now:
        card["frozen_until"] = None
      active.append(card)

  if not active:
    return None

  if country not in CARD_POINTERS:
    CARD_POINTERS[country] = 0

  index = CARD_POINTERS[country] % len(active)
  chosen_card = active[index]
  CARD_POINTERS[country] = (index + 1) % len(active)

  return chosen_card

# === ФУНКЦИЯ ПОЛУЧЕНИЯ КУРСОВ ВАЛЮТ ===
async def get_exchange_rate(target_currency: str) -> float:
  url = "https://open.er-api.com/v6/latest/USD"
  try:
    async with ClientSession() as session:
      async with session.get(url, timeout=5) as response:
        if response.status == 200:
          data = await response.json()
          rates = data.get("rates", {})
          if target_currency in rates:
            return float(rates[target_currency])
  except Exception as e:
    logger.warning(f"Не удалось получить курс для {target_currency}: {e}")

  fallback_rates = {
      "RUB": 95.0, "BYN": 3.3, "KZT": 480.0, "UAH": 41.5,
  }
  return fallback_rates.get(target_currency, 1.0)

# === ЕДИНАЯ ФУНКЦИЯ ГЛАВНОГО МЕНЮ ===
async def show_main_menu(event: Message | CallbackQuery, state: FSMContext, edit: bool = False):
  await state.clear()
  user_id = event.from_user.id
  if user_id not in KNOWN_USERS:
    KNOWN_USERS[user_id] = datetime.datetime.now()

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🛒 Заказать", callback_data="start_order")],
          [
              InlineKeyboardButton(text="📦 В работе", callback_data="my_orders"),
              InlineKeyboardButton(text="📊 Репутация", callback_data="reputation"),
          ],
          [
              InlineKeyboardButton(text="💬 Поддержка", callback_data="contact_admin"),
          ],
      ]
  )
  text = (
      "🏆 <b>ARENA SHOP — СПОРТ УСЛУГИ</b>\n\n"
      "Здесь вы можете поквитаться с должниками, отомстить обидчикам и заказать правосудие. "
      "Все конфиденциально и главное — безопасно. Работаем 24/7.\n\n"
      "Да прибудет АРЕНА!"
  )
  
  if isinstance(event, CallbackQuery):
    if edit:
      try:
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
      except Exception:
        await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await event.answer()
  else:
    await event.answer(text, reply_markup=keyboard, parse_mode="HTML")

# === АДМИНСКИЕ КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ КАРТАМИ И БАНОМ ===
@router.message(Command("ban"))
async def cmd_ban_user(message: Message):
  if ADMIN_ID and message.from_user.id != ADMIN_ID:
    return
  args = message.text.split(maxsplit=1)
  if len(args) < 2:
    await message.reply("❌ Использование: `/ban <user_id>`", parse_mode="Markdown")
    return

  target = args[1].strip()
  if target.isdigit():
    user_id = int(target)
    BANNED_USERS.add(user_id)
    await message.reply(f"✅ Пользователь с ID <code>{user_id}</code> успешно заблокирован.", parse_mode="HTML")
  else:
    await message.reply("❌ Укажите корректный числовой ID пользователя.", parse_mode="Markdown")

@router.message(Command("add"))
async def cmd_add_card(message: Message):
  if ADMIN_ID and message.from_user.id != ADMIN_ID:
    return
  args = message.text.split(maxsplit=1)
  if len(args) < 2:
    await message.reply(
        "❌ Использование:\n"
        "• Для РФ/РК: `/add +783839293 ОзонБанк Россия`\n"
        "• Для УКР/РБ: `/add 6672 7778 1113 8888 ПриватБанк Украина`",
        parse_mode="Markdown"
    )
    return

  parts = args[1].split()
  if len(parts) < 3:
    await message.reply("❌ Неверный формат. Укажите реквизиты, банк и страну.")
    return

  country = parts[-1]
  bank = parts[-2]
  details = " ".join(parts[:-2])

  valid_countries = ["Россия", "Казахстан", "Украина", "Беларусь"]
  if country not in valid_countries:
    await message.reply(f"❌ Неверная страна. Доступные: {', '.join(valid_countries)}")
    return

  for card in CARD_DETAILS:
    if card["details"] == details and card["bank"] == bank and card["country"] == country:
      await message.reply("⚠️ Такие реквизиты уже существуют в базе.")
      return

  CARD_DETAILS.append({
      "details": details,
      "bank": bank,
      "country": country,
      "frozen_until": None
  })
  await message.reply(
      f"✅ <b>Реквизиты успешно добавлены!</b>\n\n"
      f"🌍 Страна: {country}\n"
      f"🏦 Банк: {bank}\n"
      f"💳 Данные: <code>{details}</code>",
      parse_mode="HTML"
  )

@router.message(Command("delete"))
async def cmd_delete_card(message: Message):
  if ADMIN_ID and message.from_user.id != ADMIN_ID:
    return
    
  global CARD_DETAILS  
  args = message.text.split(maxsplit=1)
  if len(args) < 2:
    await message.reply("❌ Использование: `/delete <реквизиты> <Банк> <Страна>`", parse_mode="Markdown")
    return

  parts = args[1].split()
  if len(parts) < 3:
    await message.reply("❌ Неверный формат.")
    return

  country = parts[-1]
  bank = parts[-2]
  details = " ".join(parts[:-2])

  initial_len = len(CARD_DETAILS)
  CARD_DETAILS = [
      c for c in CARD_DETAILS 
      if not (c["details"] == details and c["bank"] == bank and c["country"].lower() == country.lower())
  ]

  if len(CARD_DETAILS) < initial_len:
    await message.reply("✅ Реквизиты успешно удалены.")
  else:
    await message.reply("❌ Реквизиты не найдены в базе.")

@router.message(Command("freeze"))
async def cmd_freeze_card(message: Message):
  if ADMIN_ID and message.from_user.id != ADMIN_ID:
    return
  args = message.text.split(maxsplit=1)
  if len(args) < 2:
    await message.reply("❌ Использование: `/freeze <реквизиты> <Банк> <Страна>`", parse_mode="Markdown")
    return

  parts = args[1].split()
  if len(parts) < 3:
    await message.reply("❌ Неверный формат.")
    return

  country = parts[-1]
  bank = parts[-2]
  details = " ".join(parts[:-2])

  found = False
  now = datetime.datetime.now()
  for card in CARD_DETAILS:
    if card["details"] == details and card["bank"] == bank and card["country"].lower() == country.lower():
      card["frozen_until"] = now + datetime.timedelta(hours=24)
      found = True
      break

  if found:
    await message.reply("✅ Реквизиты зафрижены на 24 часа. По истечении времени они автоматически станут актуальными.")
  else:
    await message.reply("❌ Реквизиты не найдены.")

# === ФУНКЦИЯ СОЗДАНИЯ ИНВОЙСА CRYPTOBOT ===
async def create_cryptobot_invoice(amount_usd: float, description: str):
  if not CRYPTO_BOT_TOKEN:
    return "", None

  url = "https://pay.crypt.bot/api/createInvoice"
  headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
  payload = {
      "asset": "USDT",
      "amount": str(amount_usd),
      "description": description,
      "payload": "order_payment",
  }

  for attempt in range(2):
    try:
      async with ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
          if resp.status == 200:
            data = await resp.json()
            if data.get("ok"):
              res = data["result"]
              return res["pay_url"], res["invoice_id"]
    except Exception as e:
      logger.error(f"Попытка {attempt+1} - Ошибка создания CryptoBot инвойса: {e}")
      await asyncio.sleep(1)
  return "", None

# === ПРОВЕРКА СТАТУСА ПЛАТЕЖА CRYPTOBOT ===
async def check_cryptobot_invoice_status(invoice_id: int) -> bool:
  if not CRYPTO_BOT_TOKEN or not invoice_id:
    return True
  url = "https://pay.crypt.bot/api/getInvoices"
  headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
  params = {"invoice_ids": str(invoice_id)}
  try:
    async with ClientSession() as session:
      async with session.get(url, params=params, headers=headers, timeout=10) as resp:
        if resp.status == 200:
          data = await resp.json()
          if data.get("ok"):
            items = data.get("result", {}).get("items", [])
            if items:
              return items[0].get("status") == "paid"
  except Exception as e:
    logger.error(f"Ошибка проверки инвойса CryptoBot: {e}")
  return False

# === ФОНОВАЯ ЗАДАЧА АВТО-РАССЫЛКИ ===
async def scheduled_broadcast(bot: Bot):
  while True:
    await asyncio.sleep(3600)
    now = datetime.datetime.now()
    for user_id, last_time in list(KNOWN_USERS.items()):
      if last_time is None or (now - last_time).total_seconds() >= 24 * 3600:
        try:
          today = datetime.date.today()
          target_date = today + datetime.timedelta(days=3)
          months_ru = ["", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
          
          text = (
              "✨ <b>Специальное предложение</b>\n\n"
              f"Напоминаем, что в нашем сервисе действует персональная скидка <b>20%</b>, которая актуальна до <b>{target_date.day} {months_ru[target_date.month]}</b>.\n\n"
              "Будем рады помочь с решением вашей задачи на лучших условиях. Гарантируем аккуратность и конфиденциальность.\n\n"
              "Ждем вас в боте 👇"
          )
          keyboard = InlineKeyboardMarkup(inline_keyboard=[
              [InlineKeyboardButton(text="✨ Оформить со скидкой 20%", callback_data="start_order")],
              [InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]
          ])
          await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard, parse_mode="HTML")
          KNOWN_USERS[user_id] = now
        except Exception as e:
          logger.error(f"Не удалось отправить автосообщение пользователю {user_id}: {e}")

async def delayed_abandoned_cart_reminder(bot: Bot, user_id: int):
  try:
    await asyncio.sleep(1800)  # 30 минут
    if user_id in ABANDONED_CHECKOUTS:
      reminder_text = (
          "👋 <b>Завершить заказ со скидкой -20%?</b>\n\n"
          "Мы заметили, что вы остановились на этапе оплаты. Возвращайтесь к оформлению первого заказа со скидкой <b>-20%</b> или обратитесь в поддержку, если возникли вопросы 👇"
      )
      keyboard = InlineKeyboardMarkup(inline_keyboard=[
          [InlineKeyboardButton(text="🛒 Вернуться к заказу (-20%)", callback_data="start_order")],
          [InlineKeyboardButton(text="💬 Обратиться в поддержку", callback_data="contact_admin")]
      ])
      await bot.send_message(chat_id=user_id, text=reminder_text, reply_markup=keyboard, parse_mode="HTML")
      ABANDONED_CHECKOUTS.pop(user_id, None)
  except asyncio.CancelledError:
    pass

# === ОБРАБОТЧИКИ СОБЫТИЙ И КОМАНД ===
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
  await show_main_menu(message, state)

@router.message(Command("order"))
async def cmd_order(message: Message, state: FSMContext):
  user_id = message.from_user.id
  if user_id not in KNOWN_USERS:
    KNOWN_USERS[user_id] = datetime.datetime.now()
  await state.set_state(OrderForm.service)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🧤 Облить зеленкой — 20$", callback_data="srv_Облить_зеленкой_20")],
          [InlineKeyboardButton(text="🧯 Поджёг двери — 50$", callback_data="srv_Поджег_дверей_50")],
          [InlineKeyboardButton(text="🥊 Избить — 80$", callback_data="srv_Избить_80")],
          [InlineKeyboardButton(text="🖖 Сломать пальцы — 100$", callback_data="srv_Сломать_пальцы_100")],
          [InlineKeyboardButton(text="🦵 Сломать конечности — 200$", callback_data="srv_Сломать_конечности_200")],
          [InlineKeyboardButton(text="🪓 Отрубить конечности — 300$", callback_data="srv_Отрубить_конечности_300")],
          [InlineKeyboardButton(text="🧑‍🦽 Сделать инвалидом — 500$", callback_data="srv_Сделать_инвалидом_500")],
          [InlineKeyboardButton(text="🩸 Убийство — 3000$", callback_data="srv_Убийство_3000")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")],
      ]
  )
  await message.answer("🛒 <b>Каталог услуг</b>\n\nВыберите подходящий вариант из списка:", reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("my_orders"))
async def cmd_my_orders_msg(message: Message):
  user_id = message.from_user.id
  orders = USER_ORDERS.get(user_id, [])

  if not orders:
    text = "📦 <b>В работе</b>\n\nУ вас пока нет активных или завершенных заказов."
  else:
    text = "📦 <b>История ваших заказов:</b>\n\n"
    for idx, ord_data in enumerate(orders, 1):
      text += f"<b>Заказ #{idx}</b>\n• Услуга: {ord_data['service_name']}\n• Сумма: {ord_data['total_price']}$\n• Статус: {ord_data['status']}\n\n"

  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]])
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("reputation"))
async def cmd_reputation_msg(message: Message):
  current_date = datetime.date.today()
  base_date = datetime.date(2026, 1, 1)
  days_passed = max(0, (current_date - base_date).days)
  completed = min(3752 + days_passed * 25, 20000)
  
  rng = random.Random(current_date.toordinal())
  in_progress = rng.randint(170, 500)
  new_requests = rng.randint(30, 80)

  text = (
      "📊 <b>Статистика и достижения сервиса</b>\n\n"
      f"• Успешно выполнено задач: <b>{completed:,}</b>\n"
      f"• В активной работе: <b>{in_progress}</b>\n"
      f"• Новых заявок сегодня: <b>{new_requests}</b>\n\n"
      "<i>Мы дорожим конфиденциальностью каждого клиента и поддерживаем безупречный уровень сервиса.</i>"
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]])
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  task = ABANDONED_CHECKOUTS.pop(user_id, None)
  if task:
    task.cancel()
  await show_main_menu(callback, state, edit=True)

@router.callback_query(F.data == "reputation")
async def show_reputation(callback: CallbackQuery):
  current_date = datetime.date.today()
  base_date = datetime.date(2026, 1, 1)
  days_passed = max(0, (current_date - base_date).days)
  completed = min(3752 + days_passed * 25, 20000)
  
  rng = random.Random(current_date.toordinal())
  in_progress = rng.randint(170, 500)
  new_requests = rng.randint(30, 80)

  text = (
      "📊 <b>Статистика и достижения сервиса</b>\n\n"
      f"• Успешно выполнено задач: <b>{completed:,}</b>\n"
      f"• В активной работе: <b>{in_progress}</b>\n"
      f"• Новых заявок сегодня: <b>{new_requests}</b>\n\n"
      "<i>Мы дорожим конфиденциальностью каждого клиента и поддерживаем безупречный уровень сервиса.</i>"
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]])
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "my_orders")
async def show_my_orders(callback: CallbackQuery):
  user_id = callback.from_user.id
  orders = USER_ORDERS.get(user_id, [])

  if not orders:
    text = "📦 <b>В работе</b>\n\nУ вас пока нет активных или завершенных заказов."
  else:
    text = "📦 <b>История ваших заказов:</b>\n\n"
    for idx, ord_data in enumerate(orders, 1):
      text += f"<b>Заказ #{idx}</b>\n• Услуга: {ord_data['service_name']}\n• Сумма: {ord_data['total_price']}$\n• Статус: {ord_data['status']}\n\n"

  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]])
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "contact_admin")
async def contact_admin_info(callback: CallbackQuery, state: FSMContext):
  await state.set_state(SupportForm.reason)
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_home")]])
  text = (
      "💬 <b>Служба поддержки</b>\n\n"
      "Опишите вашу ситуацию или задайте вопрос "
      "(например: <i>проблема с оплатой, статус заказа, другой вопрос</i>):"
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.message(SupportForm.reason, F.text)
async def process_support_reason(message: Message, state: FSMContext):
  await state.update_data(reason=message.text.strip())
  await state.set_state(SupportForm.photo)
  keyboard = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="⏩ Пропустить", callback_data="skip_support_photo")],
      [InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_home")]
  ])
  await message.answer("📸 Отправьте фото или нажмите кнопку пропуска:", reply_markup=keyboard)

@router.message(SupportForm.photo, F.photo)
async def process_support_photo(message: Message, state: FSMContext):
  photo_id = message.photo[-1].file_id
  data = await state.get_data()
  user = message.from_user
  user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
  
  admin_text = f"📩 <b>Новое обращение в поддержку</b>\n\n• От кого: {user_info} (<code>{user.id}</code>)\n• Вопрос: {data.get('reason')}"
  if ADMIN_ID:
    try:
      await message.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=admin_text, parse_mode="HTML")
    except Exception as e:
      logger.error(f"Ошибка отправки админу: {e}")

  await message.answer("✅ Обращение отправлено! Специалист свяжется с вами в ближайшее время.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]]))
  await state.clear()

@router.callback_query(SupportForm.photo, F.data == "skip_support_photo")
async def skip_support_photo(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  user = callback.from_user
  user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
  
  admin_text = f"📩 <b>Новое обращение в поддержку</b>\n\n• От кого: {user_info} (<code>{user.id}</code>)\n• Вопрос: {data.get('reason')}"
  if ADMIN_ID:
    try:
      await callback.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="HTML")
    except Exception as e:
      logger.error(f"Ошибка отправки админу: {e}")

  await callback.message.edit_text("✅ Обращение отправлено! Специалист свяжется с вами в ближайшее время.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]]))
  await state.clear()
  await callback.answer()

# === КАТАЛОГ И ОФОРМЛЕНИЕ ЗАКАЗА ===
@router.callback_query(F.data == "start_order")
async def process_start_order(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  task = ABANDONED_CHECKOUTS.pop(user_id, None)
  if task:
    task.cancel()

  await state.set_state(OrderForm.service)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🧤 Облить зеленкой — 20$", callback_data="srv_Облить_зеленкой_20")],
          [InlineKeyboardButton(text="🧯 Поджёг двери — 50$", callback_data="srv_Поджег_дверей_50")],
          [InlineKeyboardButton(text="🥊 Избить — 80$", callback_data="srv_Избить_80")],
          [InlineKeyboardButton(text="🖖 Сломать пальцы — 100$", callback_data="srv_Сломать_пальцы_100")],
          [InlineKeyboardButton(text="🦵 Сломать конечности — 200$", callback_data="srv_Сломать_конечности_200")],
          [InlineKeyboardButton(text="🪓 Отрубить конечности — 300$", callback_data="srv_Отрубить_конечности_300")],
          [InlineKeyboardButton(text="🧑‍🦽 Сделать инвалидом — 500$", callback_data="srv_Сделать_инвалидом_500")],
          [InlineKeyboardButton(text="🩸 Убийство — 3000$", callback_data="srv_Убийство_3000")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text("🛒 <b>Каталог услуг</b>\n\nВыберите подходящий вариант из списка:", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(OrderForm.service, F.data.startswith("srv_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  price = int(parts[-1])
  service_name = " ".join(parts[1:-1]).replace("_", " ")

  await state.update_data(service_name=service_name, service_price=price)
  await state.set_state(OrderForm.country)

  countries = [
      ("🇷🇺 Россия", "country_Russia"),
      ("🇧🇾 Беларусь", "country_Belarus"),
      ("🇺🇦 Украина", "country_Ukraine"),
      ("🇰🇿 Казахстан", "country_Kazakhstan"),
  ]
  
  kb_rows = []
  for i in range(0, len(countries), 2):
    row = [InlineKeyboardButton(text=countries[i][0], callback_data=countries[i][1])]
    if i + 1 < len(countries):
      row.append(InlineKeyboardButton(text=countries[i+1][0], callback_data=countries[i+1][1]))
    kb_rows.append(row)
  kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="start_order")])

  await callback.message.edit_text(f"🎯 Выбрано: <b>{service_name}</b> ({price}$)\n\n🌍 <b>Страна вашей цели</b>\n\nВыберите страну:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
  await callback.answer()

@router.callback_query(OrderForm.country, F.data.startswith("country_"))
async def process_country(callback: CallbackQuery, state: FSMContext):
  c_code = callback.data.split("_")[1]
  names = {
      "Russia": "Россия", "Belarus": "Беларусь",
      "Ukraine": "Украина", "Kazakhstan": "Казахстан"
  }
  selected = names.get(c_code, c_code)
  curr_info = COUNTRY_CURRENCIES.get(selected, {"code": "USD", "symbol": "USD"})
  await state.update_data(country=selected, curr_code=curr_info["code"], curr_symbol=curr_info["symbol"])

  await state.set_state(OrderForm.target_location)
  await callback.message.edit_text(
      f"📍 Страна: <b>{selected}</b>\n\n"
      f"🏢 <b>Локация</b>\n"
      f"Укажите адрес цели.\n"
      f"<i>Пример: город, адрес, дом, квартира</i>",
      parse_mode="HTML"
  )
  await callback.answer()

@router.message(OrderForm.target_location, F.text)
async def process_target_location(message: Message, state: FSMContext):
  await state.update_data(target_location=message.text.strip())
  await state.set_state(OrderForm.target_data)
  await message.answer(
      "🪪 <b>Данные цели</b>\n"
      "Укажите информацию о цели.\n"
      "<i>Пример: ФИО, паспортные данные, просто имя, если неизвестно — можно написать «неизвестно»</i>",
      parse_mode="HTML"
  )

@router.message(OrderForm.target_data, F.text)
async def process_target_data(message: Message, state: FSMContext):
  await state.update_data(target_data=message.text.strip(), photos=[])
  await state.set_state(OrderForm.photos)
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏩ Пропустить", callback_data="finish_photos")]])
  await message.answer("📸 Прикрепите фото цели (до 3 шт.) или нажмите пропустить:", reply_markup=keyboard)

@router.message(OrderForm.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
  data = await state.get_data()
  photos = data.get("photos", [])
  if len(photos) >= 3:
    await message.answer("⚠️ Добавлено максимальное количество фото (3 шт.).")
    return

  photos.append(message.photo[-1].file_id)
  await state.update_data(photos=photos)
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ Готово ({len(photos)}/3)", callback_data="finish_photos")]])
  await message.answer(f"📸 Фото #{len(photos)} добавлено.", reply_markup=keyboard)

@router.callback_query(OrderForm.photos, F.data == "finish_photos")
async def finish_photos(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.urgency)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="⚡ За 2-3 часа (+50$)", callback_data="urg_fast_50")],
          [InlineKeyboardButton(text="🕐 Завтра (+20$)", callback_data="urg_tomorrow_20")],
          [InlineKeyboardButton(text="📅 Стандартно (2-5 дней)", callback_data="urg_standard_0")],
      ]
  )
  await callback.message.edit_text("⏱ Выберите срочность выполнения:", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(OrderForm.urgency, F.data.startswith("urg_"))
async def process_urgency(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  urg_price = int(parts[2])
  urg_map = {"fast": "⚡ За 2-3 часа", "tomorrow": "🕐 Завтра", "standard": "📅 2-5 дней"}
  urgency = urg_map.get(parts[1], "📅 2-5 дней")

  await state.update_data(urgency=urgency, urgency_price=urg_price)
  data = await state.get_data()
  
  total_price = data.get("service_price", 0) + urg_price
  await state.update_data(total_price=total_price)

  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(total_price * rate)

  summary_text = (
      "✨ <b>Готово! Детали заказа:</b>\n\n"
      f"• Услуга: <b>{data.get('service_name')}</b>\n"
      f"• Срочность: {urgency}\n"
      f"• Страна: {data.get('country')}\n\n"
      f"💵 <b>Сумма к оплате: {total_price}$</b> <i>(≈ {local_amount:,} {data.get('curr_symbol')})</i>"
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Перейти к оплате", callback_data="go_to_payment")]])
  await callback.message.edit_text(summary_text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "go_to_payment")
async def process_go_to_payment(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  
  if user_id in ABANDONED_CHECKOUTS:
    task = ABANDONED_CHECKOUTS.pop(user_id, None)
    if task:
      task.cancel()
  ABANDONED_CHECKOUTS[user_id] = asyncio.create_task(delayed_abandoned_cart_reminder(callback.bot, user_id))

  data = await state.get_data()
  total_price = data.get("total_price", 250)
  service_name = data.get("service_name", "")
  country = data.get("country", "Россия")
  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(total_price * rate)

  is_murder = "убийство" in service_name.lower()

  if is_murder:
    payment_text = (
        "⏳ <b>Бронирование зафиксировано</b>\n"
        "Время на завершение оплаты: <b><u>20:00</u></b>\n\n"
        "⚠️ <b>Внимание:</b> Для выбранной услуги («Убийство») оплата банковскими картами недоступна по соображениям безопасности. Доступна только криптовалюта и CryptoBot.\n\n"
        f"💳 <b>Способ оплаты</b>\n\n"
        f"Сумма: <b>{total_price}$</b> <i>(≈ {local_amount:,} {data.get('curr_symbol')})</i>\n\n"
        "Выберите вариант:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 CryptoBot (без комиссий)", callback_data="pay_cryptobot")],
            [InlineKeyboardButton(text="🪙 Криптовалюта (выбор сети)", callback_data="crypto_expert")],
            [InlineKeyboardButton(text="💬 Нужна помощь", callback_data="payment_help_manager")]
        ]
    )
  else:
    card_btn_text_map = {
        "Россия": "💳 Оплатить на СБП",
        "Казахстан": "💳 Оплатить на Kaspi",
        "Украина": "💳 Оплатить картой",
        "Беларусь": "💳 Оплатить картой"
    }
    card_btn_text = card_btn_text_map.get(country, "💳 Оплатить картой")

    payment_text = (
        "⏳ <b>Бронирование зафиксировано</b>\n"
        "Время на завершение оплаты: <b><u>20:00</u></b>\n\n"
        f"💳 <b>Способ оплаты ({country})</b>\n\n"
        f"Сумма: <b>{total_price}$</b> <i>(≈ {local_amount:,} {data.get('curr_symbol')})</i>\n\n"
        "Выберите вариант:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=card_btn_text, callback_data="pay_card_option")],
            [InlineKeyboardButton(text="🤖 CryptoBot (без комиссий)", callback_data="pay_cryptobot")],
            [InlineKeyboardButton(text="🪙 Криптовалюта (выбор сети)", callback_data="crypto_expert")],
            [InlineKeyboardButton(text="💬 Нужна помощь", callback_data="payment_help_manager")]
        ]
    )

  await callback.message.edit_text(payment_text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

# === ОБРАБОТКА ОПЛАТЫ КАРТОЙ / СБП / КАСПИ (С ЧЕРЕДОВАНИЕМ ПО КРУГУ) ===
@router.callback_query(F.data == "pay_card_option")
async def process_pay_card_option(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  country = data.get("country", "Россия")
  total_price = data.get("total_price", 250)
  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(total_price * rate)

  card = get_next_card(country)

  if not card:
    if country == "Россия":
      payment_type_desc = "картой/СБП"
    elif country == "Казахстан":
      payment_type_desc = "Kaspi / по номеру"
    else:
      payment_type_desc = "картой"

    text = (
        f"❌ <b>Реквизиты временно недоступны</b>\n\n"
        f"К сожалению, в данный момент реквизиты для оплаты ({payment_type_desc}) для страны <b>{country}</b> недоступны.\n\n"
        "Мы уже решаем эту проблему. Пожалуйста, оплатите через <b>CryptoBot</b> или реквизиты криптовалюты 👇"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 CryptoBot", callback_data="pay_cryptobot")],
            [InlineKeyboardButton(text="🪙 Криптовалюта", callback_data="crypto_expert")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="go_to_payment")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
    return

  header_map = {
      "Россия": "Оплата по СБП",
      "Казахстан": "Оплата на Kaspi",
      "Украина": "Оплата по реквизитам карты",
      "Беларусь": "Оплата по реквизитам карты"
  }
  header_title = header_map.get(country, "Оплата по реквизитам")

  text = (
      f"💳 <b>{header_title} ({country})</b>\n\n"
      f"• Сумма в долларах: <b>{total_price}$</b>\n"
      f"• Актуальный курс: <b>1 USD = {rate:.2f} {data.get('curr_symbol')}</b>\n"
      f"• <b>Итого к оплате: {local_amount:,} {data.get('curr_symbol')}</b>\n\n"
      f"⚠️ <b>Внимание!</b> Переводите средства <b>строго</b> на указанные реквизиты ниже:\n\n"
      f"<b>Банк:</b> {card['bank']}\n"
      f"<b>Реквизиты:</b> <code>{card['details']}</code>\n\n"
      "💡 <i>После успешного перевода нажмите кнопку ниже, чтобы прикрепить чек.</i>"
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="✅ Прикрепить чек", callback_data="ask_for_receipt")],
      [InlineKeyboardButton(text="⬅️ Назад", callback_data="go_to_payment")]
  ])
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "cryptobot_guide")
async def process_cryptobot_guide(callback: CallbackQuery):
  guide_text = "📖 <b>Минигайд: как оплатить через @CryptoBot</b>\n\n1. Откройте @CryptoBot.\n2. Перейдите в Кошелек ➔ P2P.\n3. Купите USDT с карты.\n4. Вернитесь и оплатите без комиссии."
  keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="go_to_payment")]])
  await callback.message.edit_text(guide_text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "payment_help_manager")
async def process_payment_help_manager(callback: CallbackQuery):
  if ADMIN_ID:
    try:
      user = callback.from_user
      await callback.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 Запрос помощи с оплатой от @{user.username} (<code>{user.id}</code>)", parse_mode="HTML")
    except Exception:
      pass
  await callback.answer("✅ Менеджер уведомлен, скоро свяжется с вами.", show_alert=True)

@router.callback_query(F.data == "pay_cryptobot")
async def process_pay_cryptobot(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)

  pay_url, inv_id = await create_cryptobot_invoice(total_price, "Оплата услуг")
  if not pay_url:
    await callback.answer("❌ Сервис недоступен.", show_alert=True)
    return

  await state.update_data(invoice_id=inv_id)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🔗 Оплатить счет", url=pay_url)],
          [InlineKeyboardButton(text="✅ Проверить оплату", callback_data="cryptobot_check_success")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="go_to_payment")],
      ]
  )
  await callback.message.edit_text(f"🤖 <b>CryptoBot</b>\n\nСумма: <b>{total_price} USDT</b>\n\nПосле оплаты нажмите кнопку проверки:", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "cryptobot_check_success")
async def process_cryptobot_check(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  inv_id = data.get("invoice_id")
  
  is_paid = await check_cryptobot_invoice_status(inv_id)
  if not is_paid:
    await callback.answer("⏳ Платеж еще не поступил. Попробуйте через минуту.", show_alert=True)
    return

  user = callback.from_user
  task = ABANDONED_CHECKOUTS.pop(user.id, None)
  if task:
    task.cancel()

  if user.id not in USER_ORDERS:
    USER_ORDERS[user.id] = []
  USER_ORDERS[user.id].append({"service_name": data.get("service_name"), "total_price": data.get("total_price"), "status": "✅ Оплачено через CryptoBot"})

  if ADMIN_ID:
    try:
      await callback.bot.send_message(chat_id=ADMIN_ID, text=f"🤖 Успешная оплата CryptoBot от @{user.username} (<code>{user.id}</code>)", parse_mode="HTML")
    except Exception:
      pass

  await callback.message.edit_text("✅ <b>Оплата подтверждена!</b>\n\nЗаявка принята в работу.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]]), parse_mode="HTML")
  await state.clear()

@router.callback_query(F.data == "crypto_expert")
async def process_crypto_expert(callback: CallbackQuery, state: FSMContext):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="💎 USDT (TRC-20)", callback_data="pay_crypto_trc20")],
          [InlineKeyboardButton(text="💵 USDT (BEP-20)", callback_data="pay_crypto_bep20")],
          [InlineKeyboardButton(text="🪙 TON", callback_data="pay_crypto_ton")],
          [InlineKeyboardButton(text="🪙 Bitcoin (BTC)", callback_data="pay_crypto_btc")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="go_to_payment")],
      ]
  )
  await callback.message.edit_text("🪙 Выберите криптовалютную сеть:", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data.startswith("pay_crypto_"))
async def process_pay_crypto(callback: CallbackQuery, state: FSMContext):
  net_key = callback.data.split("_")[2]
  net_info = CRYPTO_NETWORKS.get(net_key)
  if not net_info:
    await callback.answer("Сеть не найдена", show_alert=True)
    return

  data = await state.get_data()
  total_price = data.get("total_price", 250)
  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(total_price * rate)

  text = (
      f"💳 <b>Оплата {net_info['name']}</b>\n\n"
      f"• Сумма: <b>{total_price}$</b> <i>(≈ {local_amount:,} {data.get('curr_symbol')})</i>\n"
      f"• Сеть: <b>{net_info['network']}</b>\n"
      f"• Реквизиты:\n<code>{net_info['address']}</code>\n\n"
      "💡 <i>После перевода прикрепите чек.</i>"
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="✅ Прикрепить чек", callback_data="ask_for_receipt")],
      [InlineKeyboardButton(text="⬅️ Назад", callback_data="crypto_expert")]
  ])
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "ask_for_receipt")
async def ask_for_receipt(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.receipt)
  await callback.message.edit_text("🧾 Отправьте скриншот или фото чека:", parse_mode="HTML")
  await callback.answer()

@router.message(OrderForm.receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext):
  user = message.from_user
  task = ABANDONED_CHECKOUTS.pop(user.id, None)
  if task:
    task.cancel()
  data = await state.get_data()

  if user.id not in USER_ORDERS:
    USER_ORDERS[user.id] = []
  USER_ORDERS[user.id].append({"service_name": data.get("service_name"), "total_price": data.get("total_price"), "status": "⏳ Ожидает проверки чека"})

  if ADMIN_ID:
    try:
      await message.bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=f"🛒 Новый чек от @{user.username} (<code>{user.id}</code>)\nСумма: {data.get('total_price')}$", parse_mode="HTML")
    except Exception:
      pass

  await message.answer("✅ Чек получен! Менеджер проверит платеж в течение 25 минут.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]]))
  await state.clear()

# === АНКЕТА КАНДИДАТА (ВАКАНСИИ) ===
@router.callback_query(F.data == "start_vacancy")
async def process_start_vacancy(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  await state.set_state(VacancyForm.country)
  countries = [
      ("🇷🇺 Россия", "vcountry_Russia"),
      ("🇧🇾 Беларусь", "vcountry_Belarus"),
      ("🇺🇦 Украина", "vcountry_Ukraine"),
      ("🇰🇿 Казахстан", "vcountry_Kazakhstan"),
  ]
  
  kb_rows = []
  for i in range(0, len(countries), 2):
    row = [InlineKeyboardButton(text=countries[i][0], callback_data=countries[i][1])]
    if i + 1 < len(countries):
      row.append(InlineKeyboardButton(text=countries[i+1][0], callback_data=countries[i+1][1]))
    kb_rows.append(row)
  kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")])

  await callback.message.edit_text("💼 <b>Анкета кандидата</b>\n\nВыберите вашу страну:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
  await callback.answer()

@router.callback_query(VacancyForm.country, F.data.startswith("vcountry_"))
async def process_vacancy_country(callback: CallbackQuery, state: FSMContext):
  c_code = callback.data.split("_")[1]
  names = {
      "Russia": "Россия", "Belarus": "Беларусь",
      "Ukraine": "Украина", "Kazakhstan": "Казахстан"
  }
  selected = names.get(c_code, c_code)
  curr_info = COUNTRY_CURRENCIES.get(selected, {"code": "USD", "symbol": "USD"})
  await state.update_data(country=selected, curr_code=curr_info["code"], curr_symbol=curr_info["symbol"])

  await state.set_state(VacancyForm.city_name_age)
  await callback.message.edit_text(f"🌍 Страна: <b>{selected}</b>\n\nУкажите город, имя и возраст (одним сообщением):", parse_mode="HTML")
  await callback.answer()

@router.message(VacancyForm.city_name_age, F.text)
async def process_vacancy_city_name_age(message: Message, state: FSMContext):
  await state.update_data(city_name_age=message.text.strip())
  await state.set_state(VacancyForm.parameters)
  await message.answer("📏 Укажите ваши физические параметры:", parse_mode="HTML")

@router.message(VacancyForm.parameters, F.text)
async def process_vacancy_parameters(message: Message, state: FSMContext):
  await state.update_data(parameters=message.text.strip())
  await state.set_state(VacancyForm.sports_exp)
  await message.answer("🏅 Расскажите о вашем спортивном опыте:", parse_mode="HTML")

@router.message(VacancyForm.sports_exp, F.text)
async def process_vacancy_sports_exp(message: Message, state: FSMContext):
  await state.update_data(sports_exp=message.text.strip())
  await state.set_state(VacancyForm.photo)
  await message.answer("📸 Прикрепите фото физической формы:", parse_mode="HTML")

@router.message(VacancyForm.photo, F.photo)
async def process_vacancy_photo(message: Message, state: FSMContext):
  await state.update_data(photo=message.photo[-1].file_id)
  data = await state.get_data()
  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(100 * rate)

  text = (
      "✅ <b>Анкета заполнена!</b>\n\n"
      f"Для трудоустройства требуется гарантийный залог <b>100$</b> <i>(≈ {local_amount:,} {data.get('curr_symbol')})</i>.\n\n"
      "Выберите способ оплаты:"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🤖 CryptoBot", callback_data="vpay_cryptobot")],
          [InlineKeyboardButton(text="🪙 Криптовалюта", callback_data="vpay_crypto_expert")],
          [InlineKeyboardButton(text="📖 Минигайд", callback_data="vpay_cryptobot_guide")]
      ]
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "vpay_cryptobot_guide")
async def process_vpay_cryptobot_guide(callback: CallbackQuery):
  await callback.message.edit_text("📖 Минигайд по @CryptoBot...", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]]))
  await callback.answer()

@router.callback_query(F.data == "vpay_cryptobot")
async def process_vpay_cryptobot(callback: CallbackQuery, state: FSMContext):
  pay_url, inv_id = await create_cryptobot_invoice(100.0, "Залог за вакансию")
  if not pay_url:
    await callback.answer("❌ Сервис недоступен.", show_alert=True)
    return

  await state.update_data(v_invoice_id=inv_id)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🔗 Оплатить счет", url=pay_url)],
          [InlineKeyboardButton(text="✅ Проверить оплату", callback_data="vpay_check_success")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text("🤖 <b>CryptoBot</b>\n\nСумма: <b>100 USDT</b>", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "vpay_check_success")
async def process_vpay_check(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  if not await check_cryptobot_invoice_status(data.get("v_invoice_id")):
    await callback.answer("⏳ Платеж еще не поступил.", show_alert=True)
    return

  if ADMIN_ID:
    try:
      await callback.bot.send_message(chat_id=ADMIN_ID, text=f"💼 Успешный залог за вакансию от @{callback.from_user.username}", parse_mode="HTML")
    except Exception:
      pass

  await callback.message.edit_text("✅ Залог подтвержден! Анкета передана руководству.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]]), parse_mode="HTML")
  await state.clear()

@router.callback_query(F.data == "vpay_crypto_expert")
async def process_vpay_crypto_expert(callback: CallbackQuery):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="💎 USDT (TRC-20)", callback_data="vpay_crypto_trc20")],
          [InlineKeyboardButton(text="💵 USDT (BEP-20)", callback_data="vpay_crypto_bep20")],
          [InlineKeyboardButton(text="🪙 TON", callback_data="vpay_crypto_ton")],
          [InlineKeyboardButton(text="🪙 Bitcoin (BTC)", callback_data="vpay_crypto_btc")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text("🪙 Выберите сеть для залога:", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data.startswith("vpay_crypto_"))
async def process_vpay_crypto(callback: CallbackQuery):
  net_key = callback.data.split("_")[2]
  net_info = CRYPTO_NETWORKS.get(net_key)
  if not net_info:
    await callback.answer("Сеть не найдена", show_alert=True)
    return

  text = (
      f"💳 <b>Оплата залога ({net_info['name']})</b>\n\n"
      "• Сумма: <b>100$</b>\n"
      f"• Сеть: <b>{net_info['network']}</b>\n"
      f"• Реквизиты:\n<code>{net_info['address']}</code>\n\n"
      "💡 <i>Прикрепите чек после перевода.</i>"
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="✅ Прикрепить чек", callback_data="vacancy_ask_receipt")],
      [InlineKeyboardButton(text="⬅️ Назад", callback_data="vpay_crypto_expert")]
  ])
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(F.data == "vacancy_ask_receipt")
async def vacancy_ask_receipt(callback: CallbackQuery, state: FSMContext):
  await state.set_state(VacancyForm.receipt)
  await callback.message.edit_text("🧾 Отправьте чек о переводе гарантийного залога:", parse_mode="HTML")
  await callback.answer()

@router.message(VacancyForm.receipt, F.photo)
async def process_vacancy_receipt(message: Message, state: FSMContext):
  user = message.from_user
  if ADMIN_ID:
    try:
      await message.bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=f"💼 Чек залога за вакансию от @{user.username} (<code>{user.id}</code>)", parse_mode="HTML")
    except Exception:
      pass

  await message.answer("✅ Чек принят! Руководство свяжется с вами.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]]))
  await state.clear()

# === WEB SERVER FOR RENDER ===
async def handle_ping(request):
  return web.Response(text="Bot is running!")

async def start_web_server():
  app = web.Application()
  app.router.add_get("/", handle_ping)
  runner = web.AppRunner(app)
  await runner.setup()
  port = int(os.getenv("PORT", 10000))
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()

async def main():
  bot = Bot(token=BOT_TOKEN)
  dp = Dispatcher()
  dp.include_router(router)
  
  # Защита от временных сбоев Telegram API (502 Bad Gateway) при старте
  try:
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="order", description="Заказать"),
        BotCommand(command="my_orders", description="В работе"),
        BotCommand(command="reputation", description="Репутация"),
    ])
  except Exception as e:
    logger.warning(f"Не удалось установить команды бота при старте: {e}")
  
  asyncio.create_task(start_web_server())
  asyncio.create_task(scheduled_broadcast(bot))
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)

if __name__ == "__main__":
  asyncio.run(main())
