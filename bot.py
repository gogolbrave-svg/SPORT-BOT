import asyncio
import datetime
import logging
import os
import random
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
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
  targets_count = State()
  country = State()
  location_and_target = State()
  photos = State()
  task_and_urgency = State()
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
PAYMENT_TIMERS = {}
ABANDONED_CHECKOUTS = {}

router = Router()

# === СЛОВАРЬ ВАЛЮТ ДЛЯ СТРАН ===
COUNTRY_CURRENCIES = {
    "Россия": {"code": "RUB", "symbol": "₽"},
    "Беларусь": {"code": "BYN", "symbol": "BYN"},
    "Казахстан": {"code": "KZT", "symbol": "₸"},
    "Молдова": {"code": "MDL", "symbol": "лей"},
    "Узбекистан": {"code": "UZS", "symbol": "сум"},
    "Кыргызстан": {"code": "KGS", "symbol": "сом"},
    "Таджикистан": {"code": "TJS", "symbol": "сом."},
    "Армения": {"code": "AMD", "symbol": "драм"},
    "Украина": {"code": "UAH", "symbol": "грн."},
    "Азербайджан": {"code": "AZN", "symbol": "AZN"},
    "Грузия": {"code": "GEL", "symbol": "GEL"},
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
      "RUB": 95.0, "BYN": 3.3, "KZT": 480.0, "MDL": 18.0,
      "UZS": 12600.0, "KGS": 89.0, "TJS": 10.9, "AMD": 390.0,
      "UAH": 41.5, "AZN": 1.7, "GEL": 2.7,
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
          [InlineKeyboardButton(text="🛒 Каталог", callback_data="start_order")],
          [
              InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders"),
              InlineKeyboardButton(text="📊 Репутация", callback_data="reputation"),
          ],
          [
              InlineKeyboardButton(text="💬 Поддержка", callback_data="contact_admin"),
              InlineKeyboardButton(text="💼 Вакансии", callback_data="start_vacancy"),
          ],
      ]
  )
  text = (
      "🏆 <b>СПОРТ УСЛУГИ</b>\n\n"
      "Добро пожаловать!\n\n"
      "Выберите нужный раздел. Если возникнут вопросы — наша поддержка поможет разобраться."
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

# === ДИНАМИЧЕСКИЙ ТАЙМЕР ОПЛАТЫ (КАЖДУЮ СЕКУНДУ КАК В ОРИГИНАЛЕ) ===
async def run_payment_timer(bot: Bot, chat_id: int, message_id: int, base_text: str, keyboard_buttons_factory):
  total_seconds = 20 * 60
  task_key = (chat_id, message_id)
  
  try:
    while total_seconds > 0:
      mins, secs = divmod(total_seconds, 60)
      timer_str = f"{mins:02d}:{secs:02d}"
      
      current_text = (
          f"⏳ <b>Бронирование зафиксировано</b>\n"
          f"Время на завершение оплаты: <b><u>{timer_str}</u></b>\n\n"
          f"{base_text}"
      )
      keyboard = keyboard_buttons_factory()
      
      try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=current_text, reply_markup=keyboard, parse_mode="HTML"
        )
      except Exception:
        pass
      
      await asyncio.sleep(1)
      total_seconds -= 1
      
    expired_text = "⌛ <b>Время бронирования истекло</b>\n\nСрок резерва по заказу завершился. Вы можете повторить оформление в каталоге."
    expired_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛒 В каталог", callback_data="start_order")]])
    try:
      await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=expired_text, reply_markup=expired_kb, parse_mode="HTML")
    except Exception:
      pass
      
    if task_key in PAYMENT_TIMERS:
      del PAYMENT_TIMERS[task_key]
  except asyncio.CancelledError:
    pass

# === ФОНОВАЯ ЗАДАЧА АВТО-РАССЫЛКИ КАЖДЫЕ 24 ЧАСА ===
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
    await asyncio.sleep(1800)
    if user_id in ABANDONED_CHECKOUTS:
      reminder_text = (
          "👋 <b>Завершить оформление?</b>\n\n"
          "Мы заметили, что вы остановились на шаге оплаты. Если у вас возникли вопросы по переводу или деталей заказа — наша поддержка всегда на связи.\n\n"
          "Вернуться к оформлению можно в один клик 👇"
      )
      keyboard = InlineKeyboardMarkup(inline_keyboard=[
          [InlineKeyboardButton(text="🛒 Вернуться к заказу", callback_data="start_order")],
          [InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="contact_admin")]
      ])
      await bot.send_message(chat_id=user_id, text=reminder_text, reply_markup=keyboard, parse_mode="HTML")
      ABANDONED_CHECKOUTS.pop(user_id, None)
  except asyncio.CancelledError:
    pass

# === ОБРАБОТЧИКИ СОБЫТИЙ И КОМАНД ===
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
  await show_main_menu(message, state)

@router.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  task_key = (callback.message.chat.id, callback.message.message_id)
  if task_key in PAYMENT_TIMERS:
    PAYMENT_TIMERS[task_key].cancel()
    del PAYMENT_TIMERS[task_key]
  ABANDONED_CHECKOUTS.pop(user_id, None)
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
    text = "📦 <b>Мои заказы</b>\n\nУ вас пока нет активных или завершенных заказов."
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
  text = "💬 <b>Служба поддержки</b>\n\nОпишите вашу ситуацию или задайте вопрос:"
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
  task_key = (callback.message.chat.id, callback.message.message_id)
  if task_key in PAYMENT_TIMERS:
    PAYMENT_TIMERS[task_key].cancel()
    del PAYMENT_TIMERS[task_key]
  ABANDONED_CHECKOUTS.pop(user_id, None)

  await state.set_state(OrderForm.service)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🟢 Облить зеленкой — 20$", callback_data="srv_Облить_зеленкой_20")],
          [InlineKeyboardButton(text="🔥 Поджег дверей — 50$", callback_data="srv_Поджег_дверей_50")],
          [InlineKeyboardButton(text="🥊 Избить — 80$", callback_data="srv_Избить_80")],
          [InlineKeyboardButton(text="🦴 Сломать пальцы — 120$", callback_data="srv_Сломать_пальцы_120")],
          [InlineKeyboardButton(text="🦿 Сломать конечности — 150$", callback_data="srv_Сломать_конечности_150")],
          [InlineKeyboardButton(text="🏥 Реанимация — 200$", callback_data="srv_Реанимация_200")],
          [InlineKeyboardButton(text="🪓 Отрубить конечности — 300$", callback_data="srv_Отрубить_конечности_300")],
          [InlineKeyboardButton(text="🏹 Сделать инвалидом — 500$", callback_data="srv_Сделать_инвалидом_500")],
          [InlineKeyboardButton(text="🌳 В лес в багажнике — 1000$", callback_data="srv_В_лес_в_багажнике_1000")],
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
  await state.set_state(OrderForm.targets_count)

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="1 цель", callback_data="targets_1_0")],
          [InlineKeyboardButton(text="2 цели (+50$)", callback_data="targets_2_50")],
          [InlineKeyboardButton(text="3 цели (+100$)", callback_data="targets_3_100")],
          [InlineKeyboardButton(text="4 цели (+150$)", callback_data="targets_4_150")],
          [InlineKeyboardButton(text="5 целей (+200$)", callback_data="targets_5_200")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="start_order")],
      ]
  )
  await callback.message.edit_text(f"🎯 Выбрано: <b>{service_name}</b> ({price}$)\n\nУкажите количество целей:", reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()

@router.callback_query(OrderForm.targets_count, F.data.startswith("targets_"))
async def process_targets_count(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  count = int(parts[1])
  target_price = int(parts[2])

  await state.update_data(targets_count=count, target_price=target_price)
  await state.set_state(OrderForm.country)

  countries = [
      ("🇷🇺 Россия", "country_Russia"), ("🇧🇾 Беларусь", "country_Belarus"),
      ("🇰🇿 Казахстан", "country_Kazakhstan"), ("🇺🇿 Узбекистан", "country_Uzbekistan"),
      ("🇹🇯 Таджикистан", "country_Tajikistan"), ("🇰🇬 Кыргызстан", "country_Kyrgyzstan"),
      ("🇦🇲 Армения", "country_Armenia"), ("🇲🇩 Молдова", "country_Moldova"),
      ("🇺🇦 Украина", "country_Ukraine"), ("🇦🇿 Азербайджан", "country_Azerbaijan"),
      ("🇬🇪 Грузия", "country_Georgia")
  ]
  kb_rows = [[InlineKeyboardButton(text=c[0], callback_data=c[1])] for c in countries]
  kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="start_order")])

  await callback.message.edit_text("🌍 <b>Страна проведения — Страна вашей цели</b>\n\nВыберите страну:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
  await callback.answer()

@router.callback_query(OrderForm.country, F.data.startswith("country_"))
async def process_country(callback: CallbackQuery, state: FSMContext):
  c_code = callback.data.split("_")[1]
  names = {
      "Russia": "Россия", "Belarus": "Беларусь", "Kazakhstan": "Казахстан",
      "Moldova": "Молдова", "Uzbekistan": "Узбекистан", "Kyrgyzstan": "Кыргызстан",
      "Tajikistan": "Таджикистан", "Armenia": "Армения", "Ukraine": "Украина",
      "Azerbaijan": "Азербайджан", "Georgia": "Грузия"
  }
  selected = names.get(c_code, c_code)
  curr_info = COUNTRY_CURRENCIES.get(selected, {"code": "USD", "symbol": "USD"})
  await state.update_data(country=selected, curr_code=curr_info["code"], curr_symbol=curr_info["symbol"])

  await state.set_state(OrderForm.location_and_target)
  await callback.message.edit_text(
      f"📍 Страна: <b>{selected}</b>\n\n"
      f"📍 <b>Локация и данные цели:</b>\n"
      f"Укажите точный адрес (город, улица, дом/квартира), а также ФИО или просто имя, данные цели (одним сообщением):",
      parse_mode="HTML"
  )
  await callback.answer()

@router.message(OrderForm.location_and_target, F.text)
async def process_location_and_target(message: Message, state: FSMContext):
  await state.update_data(location_and_target=message.text.strip(), photos=[])
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
  await state.set_state(OrderForm.task_and_urgency)
  await callback.message.edit_text(
      "📝 <b>Опишите задачу подробно</b>\n\n"
      "Вы можете рассказать свою историю или объяснить в деталях, что хотите сделать с целью и т.д.:",
      parse_mode="HTML"
  )
  await callback.answer()

@router.message(OrderForm.task_and_urgency, F.text)
async def process_task_and_urgency(message: Message, state: FSMContext):
  await state.update_data(task=message.text.strip())
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="⚡ За 2-3 часа (+50$)", callback_data="urg_fast_50")],
          [InlineKeyboardButton(text="🕐 Завтра (+20$)", callback_data="urg_tomorrow_20")],
          [InlineKeyboardButton(text="📅 Стандартно (2-5 дней)", callback_data="urg_standard_0")],
      ]
  )
  await message.answer("⏱ Выберите срочность выполнения:", reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("urg_"))
async def process_urgency(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  urg_price = int(parts[2])
  urg_map = {"fast": "⚡ За 2-3 часа", "tomorrow": "🕐 Завтра", "standard": "📅 2-5 дней"}
  urgency = urg_map.get(parts[1], "📅 2-5 дней")

  await state.update_data(urgency=urgency, urgency_price=urg_price)
  data = await state.get_data()
  
  total_price = data.get("service_price", 0) + data.get("target_price", 0) + urg_price
  await state.update_data(total_price=total_price)

  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(total_price * rate)

  summary_text = (
      "✨ <b>Готово! Детали заказа:</b>\n\n"
      f"• Услуга: <b>{data.get('service_name')}</b>\n"
      f"• Целей: {data.get('targets_count')} шт.\n"
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
  chat_id = callback.message.chat.id
  message_id = callback.message.message_id
  
  if user_id in ABANDONED_CHECKOUTS:
    ABANDONED_CHECKOUTS[user_id].cancel()
  ABANDONED_CHECKOUTS[user_id] = asyncio.create_task(delayed_abandoned_cart_reminder(callback.bot, user_id))

  data = await state.get_data()
  total_price = data.get("total_price", 250)
  rate = await get_exchange_rate(data.get("curr_code", "USD"))
  local_amount = round(total_price * rate)

  base_text = f"💳 <b>Способ оплаты</b>\n\nСумма: <b>{total_price}$</b> <i>(≈ {local_amount:,} {data.get('curr_symbol')})</i>\n\nВыберите вариант:"

  def get_payment_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 CryptoBot (без комиссий)", callback_data="pay_cryptobot")],
            [InlineKeyboardButton(text="🪙 Криптовалюта (выбор сети)", callback_data="crypto_expert")],
            [InlineKeyboardButton(text="💬 Нужна помощь", callback_data="payment_help_manager")]
        ]
    )

  initial_text = f"⏳ <b>Бронирование зафиксировано</b>\nВремя на завершение оплаты: <b><u>20:00</u></b>\n\n{base_text}"
  await callback.message.edit_text(initial_text, reply_markup=get_payment_keyboard(), parse_mode="HTML")
  
  PAYMENT_TIMERS[(chat_id, message_id)] = asyncio.create_task(
      run_payment_timer(callback.bot, chat_id, message_id, base_text, get_payment_keyboard)
  )
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
          [InlineKeyboardButton(text="🔴 USDT (TRC-20)", callback_data="pay_crypto_trc20")],
          [InlineKeyboardButton(text="🟢 USDT (BEP-20)", callback_data="pay_crypto_bep20")],
          [InlineKeyboardButton(text="🔵 TON", callback_data="pay_crypto_ton")],
          [InlineKeyboardButton(text="🟠 Bitcoin (BTC)", callback_data="pay_crypto_btc")],
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
  ABANDONED_CHECKOUTS.pop(user.id, None)
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
      ("🇷🇺 Россия", "vcountry_Russia"), ("🇧🇾 Беларусь", "vcountry_Belarus"),
      ("🇰🇿 Казахстан", "vcountry_Kazakhstan"), ("🇺🇿 Узбекистан", "vcountry_Uzbekistan"),
      ("🇹🇯 Таджикистан", "vcountry_Tajikistan"), ("🇰🇬 Кыргызстан", "vcountry_Kyrgyzstan"),
      ("🇦🇲 Армения", "vcountry_Armenia"), ("🇲🇩 Молдова", "vcountry_Moldova"),
      ("🇺🇦 Украина", "vcountry_Ukraine"), ("🇦🇿 Азербайджан", "vcountry_Azerbaijan"),
      ("🇬🇪 Грузия", "vcountry_Georgia")
  ]
  kb_rows = [[InlineKeyboardButton(text=c[0], callback_data=c[1])] for c in countries]
  kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")])

  await callback.message.edit_text("💼 <b>Анкета кандидата</b>\n\nВыберите вашу страну:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
  await callback.answer()

@router.callback_query(VacancyForm.country, F.data.startswith("vcountry_"))
async def process_vacancy_country(callback: CallbackQuery, state: FSMContext):
  c_code = callback.data.split("_")[1]
  names = {
      "Russia": "Россия", "Belarus": "Беларусь", "Kazakhstan": "Казахстан",
      "Moldova": "Молдова", "Uzbekistan": "Узбекистан", "Kyrgyzstan": "Кыргызстан",
      "Tajikistan": "Таджикистан", "Armenia": "Армения", "Ukraine": "Украина",
      "Azerbaijan": "Азербайджан", "Georgia": "Грузия"
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
          [InlineKeyboardButton(text="🔴 USDT (TRC-20)", callback_data="vpay_crypto_trc20")],
          [InlineKeyboardButton(text="🟢 USDT (BEP-20)", callback_data="vpay_crypto_bep20")],
          [InlineKeyboardButton(text="🔵 TON", callback_data="vpay_crypto_ton")],
          [InlineKeyboardButton(text="🟠 Bitcoin (BTC)", callback_data="vpay_crypto_btc")],
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
  asyncio.create_task(start_web_server())
  asyncio.create_task(scheduled_broadcast(bot))
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)

if __name__ == "__main__":
  asyncio.run(main())
