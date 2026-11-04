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

if not BOT_TOKEN:
  raise ValueError("❌ BOT_TOKEN не найден!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderForm(StatesGroup):
  target_count = State()
  service = State()
  addon = State()
  country = State()
  city = State()
  address = State()
  photos = State()
  task = State()
  urgency = State()
  receipt = State()


class VacancyForm(StatesGroup):
  country = State()
  city = State()
  name = State()
  age = State()
  parameters = State()
  sports_exp = State()
  experience = State()
  photo = State()
  receipt = State()


class AdForm(StatesGroup):
  platform = State()
  duration = State()
  niche = State()
  link = State()
  creative = State()
  network = State()
  receipt = State()


# База данных в памяти для хранения заказов пользователей
USER_ORDERS = {}

router = Router()


# === СЛОВАРЬ ВАЛЮТ ДЛЯ СТРАН ===
COUNTRY_CURRENCIES = {
    "Украина": {"code": "UAH", "symbol": "грн."},
    "Россия": {"code": "RUB", "symbol": "руб."},
    "Беларусь": {"code": "BYN", "symbol": "byn"},
    "Казахстан": {"code": "KZT", "symbol": "тңг."},
    "Молдова": {"code": "MDL", "symbol": "лей"},
    "Узбекистан": {"code": "UZS", "symbol": "сум"},
    "Кыргызстан": {"code": "KGS", "symbol": "сом"},
    "Таджикистан": {"code": "TJS", "symbol": "сом."},
    "Грузия": {"code": "GEL", "symbol": "lari"},
    "Армения": {"code": "AMD", "symbol": "драм"},
    "Азербайджан": {"code": "AZN", "symbol": "манат"},
}


# === ФУНКЦИЯ ПОЛУЧЕНИЯ РЕАЛЬНЫХ КУРСОВ ВАЛЮТ ===
async def get_exchange_rate(target_currency: str) -> float:
  """Получает актуальный курс USD к целевой валюте из публичных API."""
  url = f"https://open.er-api.com/v6/latest/USD"
  try:
    async with ClientSession() as session:
      async with session.get(url, timeout=5) as response:
        if response.status == 200:
          data = await response.json()
          rates = data.get("rates", {})
          if target_currency in rates:
            return float(rates[target_currency])
  except Exception as e:
    logger.warning(
        f"Не удалось получить курс для {target_currency}: {e}. Используем"
        " резервные значения."
    )

  fallback_rates = {
      "UAH": 41.5,
      "RUB": 95.0,
      "BYN": 3.3,
      "KZT": 480.0,
      "MDL": 18.0,
      "UZS": 12600.0,
      "KGS": 89.0,
      "TJS": 10.9,
      "GEL": 2.7,
      "AMD": 390.0,
      "AZN": 1.7,
  }
  return fallback_rates.get(target_currency, 1.0)


# === ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ РЕПУТАЦИИ (РАСТЕТ ЕЖЕДНЕВНО) ===
async def get_reputation_text_and_keyboard():
  current_date = datetime.date.today()
  base_date = datetime.date(2026, 1, 1)
  days_passed = max(0, (current_date - base_date).days)

  completed = min(3752 + days_passed * 25, 20000)

  rng = random.Random(current_date.toordinal())
  in_progress = rng.randint(170, 500)
  new_requests = rng.randint(30, 80)

  text = (
      "📊 <b>СТАТИСТИКА И РЕПУТАЦИЯ СЕРВИСА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"🛡️ Успешно выполненных задач: <b>{completed}</b>\n"
      f"⚡ Активных проектов в работе: <b>{in_progress}</b>\n"
      f"📥 Новых заявок за сутки: <b>{new_requests}</b>\n\n"
      "<i>⚡ Высочайшие стандарты конфиденциальности, оперативности и безопасности.</i>"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="◀️ На главную", callback_data="back_home")]
      ]
  )
  return text, keyboard


# === 0. ГЛАВНОЕ МЕНЮ И КОМАНДЫ ===
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
  await state.clear()
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💎 Оформить заказ", callback_data="start_order"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📂 Мои заказы", callback_data="my_orders"
              ),
              InlineKeyboardButton(
                  text="📈 Репутация", callback_data="reputation"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="📢 Размещение рекламы", callback_data="start_ads"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💬 Поддержка / Администратор",
                  callback_data="contact_admin",
              )
          ],
          [
              InlineKeyboardButton(
                  text="⚡ Карьера в команде", callback_data="start_vacancy"
              )
          ],
      ]
  )
  text = (
      "🛡️ <b>ПЕРИМЕТР БЕЗОПАСНОСТИ И СПЕЦУСЛУГ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Добро пожаловать в защищенный операционный центр.\n"
      "Мы предоставляем эксклюзивный спектр решений с гарантией абсолютной конфиденциальности.\n\n"
      "👇 <i>Выберите необходимый раздел в меню ниже:</i>"
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("reputation"))
async def cmd_reputation(message: Message):
  text, keyboard = await get_reputation_text_and_keyboard()
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("my_orders"))
async def cmd_my_orders(message: Message):
  user_id = message.from_user.id
  orders = USER_ORDERS.get(user_id, [])

  if not orders:
    text = (
        "📂 <b>МОИ ОПЕРАЦИИ</b>\n━━━━━━━━━━━━━━━━━━━\n\nУ вас пока нет активных"
        " или завершенных заказов в системе."
    )
  else:
    text = "📂 <b>ВАШИ АКТИВНЫЕ ОПЕРАЦИИ:</b>\n━━━━━━━━━━━━━━━━━━━\n\n"
    for idx, ord_data in enumerate(orders, 1):
      text += (
          f"🔹 <b>Заказ #{idx}</b>\n• Услуга: {ord_data['service_name']}\n•"
          f" Сумма: {ord_data['total_price']}$\n• Статус:"
          f" {ord_data['status']}\n\n"
      )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]
      ]
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("order", "make_order"))
async def cmd_order(message: Message, state: FSMContext):
  await state.clear()
  await state.set_state(OrderForm.target_count)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="👤 1 цель (Базовый тариф)", callback_data="targets_1_0"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 2 цели (+50$)", callback_data="targets_2_50"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 3 цели (+100$)", callback_data="targets_3_100"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 4 цели (+150$)", callback_data="targets_4_150"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 5 целей (+200$)", callback_data="targets_5_200"
              )
          ],
          [InlineKeyboardButton(text="❌ Отмена", callback_data="back_home")],
      ]
  )
  await message.answer(
      "🎯 <b>ЭТАП 1 из 8: МАСШТАБ ОПЕРАЦИИ</b>\n━━━━━━━━━━━━━━━━━━━\n\nВыберите"
      " количество целей для выполнения задачи:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


@router.callback_query(F.data == "reputation")
async def show_reputation(callback: CallbackQuery):
  text, keyboard = await get_reputation_text_and_keyboard()
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "contact_admin")
async def contact_admin_info(callback: CallbackQuery):
  text = (
      "💬 <b>СВЯЗЬ С АДМИНИСТРАЦИЕЙ</b>\n━━━━━━━━━━━━━━━━━━━\n\nСистема"
      " автоматизации:\nМодератор оперативно свяжется с вами сразу после"
      " подтверждения оплаты заказа."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "my_orders")
async def show_my_orders(callback: CallbackQuery):
  user_id = callback.from_user.id
  orders = USER_ORDERS.get(user_id, [])

  if not orders:
    text = (
        "📂 <b>МОИ ОПЕРАЦИИ</b>\n━━━━━━━━━━━━━━━━━━━\n\nУ вас пока нет активных"
        " или завершенных заказов в системе."
    )
  else:
    text = "📂 <b>ВАШИ АКТИВНЫЕ ОПЕРАЦИИ:</b>\n━━━━━━━━━━━━━━━━━━━\n\n"
    for idx, ord_data in enumerate(orders, 1):
      text += (
          f"🔹 <b>Заказ #{idx}</b>\n• Услуга: {ord_data['service_name']}\n•"
          f" Сумма: {ord_data['total_price']}$\n• Статус:"
          f" {ord_data['status']}\n\n"
      )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💎 Оформить заказ", callback_data="start_order"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📂 Мои заказы", callback_data="my_orders"
              ),
              InlineKeyboardButton(
                  text="📈 Репутация", callback_data="reputation"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="📢 Размещение рекламы", callback_data="start_ads"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💬 Поддержка / Администратор",
                  callback_data="contact_admin",
              )
          ],
          [
              InlineKeyboardButton(
                  text="⚡ Карьера в команде", callback_data="start_vacancy"
              )
          ],
      ]
  )
  text = (
      "🛡️ <b>ПЕРИМЕТР БЕЗОПАСНОСТИ И СПЕЦУСЛУГ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Добро пожаловать в защищенный операционный центр.\n"
      "Мы предоставляем эксклюзивный спектр решений с гарантией абсолютной конфиденциальности.\n\n"
      "👇 <i>Выберите необходимый раздел в меню ниже:</i>"
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "start_order")
async def process_start_order(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.target_count)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="👤 1 цель (Базовый тариф)", callback_data="targets_1_0"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 2 цели (+50$)", callback_data="targets_2_50"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 3 цели (+100$)", callback_data="targets_3_100"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 4 цели (+150$)", callback_data="targets_4_150"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👥 5 целей (+200$)", callback_data="targets_5_200"
              )
          ],
          [InlineKeyboardButton(text="❌ Отмена", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text(
      "🎯 <b>ЭТАП 1 из 8: МАСШТАБ ОПЕРАЦИИ</b>\n━━━━━━━━━━━━━━━━━━━\n\nВыберите"
      " количество целей для выполнения задачи:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


@router.callback_query(OrderForm.target_count, F.data.startswith("targets_"))
async def process_target_count(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  count = int(parts[1])
  price = int(parts[2])

  await state.update_data(target_count=count, target_count_price=price)
  await state.set_state(OrderForm.service)

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🟢 Ликвидация репутации (Зеленка) — 30$",
                  callback_data="srv_Ликвидация_репутации_(Зеленка)_30",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🔥 Термический кейс (Дверь) — 70$",
                  callback_data="srv_Термический_кейс_(Дверь)_70",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🥊 Физическое воздействие — 150$",
                  callback_data="srv_Физическое_воздействие_150",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🧎‍♂️ Публичное извинение (Колени) — 200$",
                  callback_data="srv_Публичное_извинение_(Колени)_200",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🦴 Хирургия костей (Пальцы) — 300$",
                  callback_data="srv_Хирургия_костей_(Пальцы)_300",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🦴 Перелом конечностей — 500$",
                  callback_data="srv_Перелом_конечностей_500",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🏥 Медицинский кейс (Реанимация) — 800$",
                  callback_data="srv_Медицинский_кейс_(Реанимация)_800",
              )
          ],
          [
              InlineKeyboardButton(
                  text="⚠️ Радикальный метод (Конечности) — 1000$",
                  callback_data="srv_Радикальный_метод_(Конечности)_1000",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎯 Спецоперация «Колени» — 1500$",
                  callback_data="srv_Спецоперация_«Колени»_1500",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎂 VIP-проект «Тортик» — 6000$",
                  callback_data="srv_VIP-проект_«Тортик»_6000",
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ Назад", callback_data="start_order"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      f"🛡️ <b>ЭТАП 2 из 8: ВЫБОР УСЛУГИ</b>\n━━━━━━━━━━━━━━━━━━━\nВыбрано"
      f" целей: <b>{count} шт.</b> (+{price}$)\n\nВыберите категорию"
      " воздействия:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


@router.callback_query(OrderForm.service, F.data.startswith("srv_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  price = int(parts[-1])
  service_name = " ".join(parts[1:-1]).replace("_", " ")

  await state.update_data(service_name=service_name, service_price=price)
  await state.set_state(OrderForm.addon)

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="📷 Фото-фиксация отчета (Бесплатно)",
                  callback_data="addon_photo_0",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎥 Полный видеоотчет HD (+50$)",
                  callback_data="addon_video_50",
              )
          ],
      ]
  )
  await callback.message.edit_text(
      f"📸 <b>ЭТАП 3 из 8: ФОРМАТ ОТЧЕТА</b>\n━━━━━━━━━━━━━━━━━━━\nВыбранная"
      f" услуга: <b>{service_name}</b> ({price}$)\n\nВыберите способ фиксации"
      " результата:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


@router.callback_query(OrderForm.addon, F.data.startswith("addon_"))
async def process_addon(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  addon_price = int(parts[-1])
  addon_type = "Видеоотчет HD" if addon_price > 0 else "Фотоотчет"

  await state.update_data(addon_type=addon_type, addon_price=addon_price)
  await state.set_state(OrderForm.country)

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🇺🇦 Украина", callback_data="country_Ukraine"
              ),
              InlineKeyboardButton(
                  text="🇷🇺 Россия", callback_data="country_Russia"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇧🇾 Беларусь", callback_data="country_Belarus"
              ),
              InlineKeyboardButton(
                  text="🇰🇿 Казахстан", callback_data="country_Kazakhstan"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇲🇩 Молдова", callback_data="country_Moldova"
              ),
              InlineKeyboardButton(
                  text="🇺🇿 Узбекистан", callback_data="country_Uzbekistan"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇰🇬 Кыргызстан", callback_data="country_Kyrgyzstan"
              ),
              InlineKeyboardButton(
                  text="🇹🇯 Таджикистан", callback_data="country_Tajikistan"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇬🇪 Грузия", callback_data="country_Georgia"
              ),
              InlineKeyboardButton(
                  text="🇦🇲 Армения", callback_data="country_Armenia"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇦🇿 Азербайджан", callback_data="country_Azerbaijan"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      "🌍 <b>ЭТАП 4 из 8: ВЫБОР СТРАНЫ</b>\n━━━━━━━━━━━━━━━━━━━\nУкажите регион"
      " проведения операции:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


@router.callback_query(OrderForm.country, F.data.startswith("country_"))
async def process_country(callback: CallbackQuery, state: FSMContext):
  c_code = callback.data.split("_")[1]
  names = {
      "Ukraine": "Украина",
      "Russia": "Россия",
      "Belarus": "Беларусь",
      "Kazakhstan": "Казахстан",
      "Moldova": "Молдова",
      "Uzbekistan": "Узбекистан",
      "Kyrgyzstan": "Кыргызстан",
      "Tajikistan": "Таджикистан",
      "Georgia": "Грузия",
      "Armenia": "Армения",
      "Azerbaijan": "Азербайджан",
  }
  selected = names.get(c_code, c_code)

  curr_info = COUNTRY_CURRENCIES.get(
      selected, {"code": "USD", "symbol": "USD"}
  )
  await state.update_data(
      country=selected,
      curr_code=curr_info["code"],
      curr_symbol=curr_info["symbol"],
  )

  data = await state.get_data()
  target_count = data.get("target_count", 1)

  await state.set_state(OrderForm.city)
  city_prompt = (
      f"🏙️ <b>ЭТАП 5 из 8: ГОРОД ОПЕРАЦИИ</b>\n━━━━━━━━━━━━━━━━━━━\nРегион:"
      f" <b>{selected}</b>\n\n"
      f"{'Введите названия городов для каждой цели текстом:' if target_count > 1 else 'Введите название населенного пункта текстом:'}"
  )
  await callback.message.edit_text(city_prompt, parse_mode="HTML")
  await callback.answer()


@router.message(OrderForm.city, F.text)
async def process_city(message: Message, state: FSMContext):
  await state.update_data(city=message.text.strip())
  await state.set_state(OrderForm.address)
  data = await state.get_data()
  target_count = data.get("target_count", 1)
  address_prompt = (
      f"📍 <b>ЭТАП 6 из 8: ТОЧНЫЕ АДРЕСА</b>\n━━━━━━━━━━━━━━━━━━━\nГород(а):"
      f" <b>{message.text.strip()}</b>\n\n"
      f"{'Укажите точные адреса для всех целей:' if target_count > 1 else 'Укажите точный адрес цели:'}"
  )
  await message.answer(address_prompt, parse_mode="HTML")


@router.message(OrderForm.address, F.text)
async def process_address(message: Message, state: FSMContext):
  await state.update_data(address=message.text.strip(), photos=[])
  await state.set_state(OrderForm.photos)
  data = await state.get_data()
  target_count = data.get("target_count", 1)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="⏩ Пропустить / Готово без фото",
                  callback_data="finish_photos",
              )
          ]
      ]
  )
  photos_prompt = (
      f"📷 <b>ЭТАП 7 из 8: МАТЕРИАЛЫ И ФОТО</b>\n━━━━━━━━━━━━━━━━━━━\nПрикрепите"
      f" фотографии объектов (до 3 шт. для {'каждой цели' if target_count > 1 else 'цели'}).\n\nКак закончите, нажмите кнопку ниже:"
  )
  await message.answer(photos_prompt, reply_markup=keyboard, parse_mode="HTML")


@router.message(OrderForm.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
  data = await state.get_data()
  photos = data.get("photos", [])
  if len(photos) >= 3:
    await message.answer(
        "⚠️ Достигнут лимит в 3 фотографии. Нажмите «Готово»."
    )
    return

  photos.append(message.photo[-1].file_id)
  await state.update_data(photos=photos)

  btn_text = (
      f"✅ Готово ({len(photos)}/3)"
      if len(photos) < 3
      else "✅ Готово (3/3) — Далее ⏩"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text=btn_text, callback_data="finish_photos"
              )
          ]
      ]
  )
  await message.answer(
      f"📸 Фотография #{len(photos)} успешно загружена!", reply_markup=keyboard
  )


@router.callback_query(OrderForm.photos, F.data == "finish_photos")
async def finish_photos(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.task)
  await callback.message.edit_text(
      "📝 <b>ЭТАП 8 из 8: ДЕТАЛИ ЗАДАЧИ</b>\n━━━━━━━━━━━━━━━━━━━\nОпишите"
      " подробные инструкции, вводные данные или контекст для выполнения"
      " операции:",
      parse_mode="HTML",
  )
  await callback.answer()


@router.message(OrderForm.task, F.text)
async def process_task(message: Message, state: FSMContext):
  await state.update_data(task=message.text.strip())
  await state.set_state(OrderForm.urgency)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="⚡ Экстренно (2-3 часа) — +80$",
                  callback_data="urg_fast_80",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🕐 Ускоренно (Завтра) — +50$",
                  callback_data="urg_tomorrow_50",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📅 Стандарт (2-5 дней) — Бесплатно",
                  callback_data="urg_standard_0",
              )
          ],
      ]
  )
  await message.answer(
      "⏱️ <b>СРОЧНОСТЬ ВЫПОЛНЕНИЯ</b>\n━━━━━━━━━━━━━━━━━━━\nВыберите"
      " приоритет выполнения заказа:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


@router.callback_query(OrderForm.urgency, F.data.startswith("urg_"))
async def process_urgency(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  urg_type = parts[1]
  urg_price = int(parts[2])

  urg_map = {
      "fast": "⚡ Экстренно (2-3 часа)",
      "tomorrow": "🕐 Ускоренно (Завтра)",
      "standard": "📅 Стандарт (2-5 дней)",
  }
  urgency = urg_map.get(urg_type, "📅 Стандарт (2-5 дней)")

  await state.update_data(urgency=urgency, urgency_price=urg_price)

  data = await state.get_data()
  service_price = data.get("service_price", 0)
  target_count = data.get("target_count", 1)
  target_count_price = data.get("target_count_price", 0)
  addon_price = data.get("addon_price", 0)
  total_price = (
      service_price + target_count_price + addon_price + urg_price
  )

  await state.update_data(total_price=total_price)

  curr_code = data.get("curr_code", "USD")
  curr_symbol = data.get("curr_symbol", "USD")
  rate = await get_exchange_rate(curr_code)
  local_amount = round(total_price * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  urgency_display = (
      f"{urgency} (+{urg_price}$)"
      if urg_price > 0
      else f"{urgency} (Бесплатно)"
  )

  summary_text = (
      "🎉 <b>АНКЕТА УСПЕШНО СФОРМИРОВАНА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"📋 <b>Сводка операции:</b>\n"
      f"• Количество целей: <b>{target_count} шт.</b>"
      + (
          f" (+{target_count_price}$)"
          if target_count_price > 0
          else " (Базово)"
      )
      + f"\n• Услуга: <b>{data.get('service_name')}</b> ({service_price}$)\n"
      f"• Отчет: <b>{data.get('addon_type')}</b> ({addon_price}$)\n"
      f"• Срочность: <b>{urgency_display}</b>\n"
      f"• Страна: <b>{data.get('country')}</b>\n"
      f"• Город(а): <b>{data.get('city')}</b>\n"
      f"• Адрес(а): <b>{data.get('address')}</b>\n"
      f"• Медиафайлов: <b>{len(data.get('photos', []))} шт.</b>\n"
      f"• Задача: <b>{data.get('task')}</b>\n\n"
      f"💵 <b>Итого к оплате:</b> <b>{total_price}$</b>\n"
      f"<i>(≈ {local_str} {curr_symbol})</i>\n\n"
      "⚠️ <b>Внимание: Оплата принимается исключительно в криптовалюте.</b>\n"
      "Нажмите кнопку ниже для перехода к плателю 👇"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💳 Перейти к оплате", callback_data="go_to_payment"
              )
          ]
      ]
  )

  await callback.message.edit_text(
      summary_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === ВЫБОР СПОСОБА ОПЛАТЫ ИЛИ ГАЙД ===
@router.callback_query(F.data == "go_to_payment")
async def process_go_to_payment(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)
  curr_symbol = data.get("curr_symbol", "USD")
  curr_code = data.get("curr_code", "USD")
  rate = await get_exchange_rate(curr_code)
  local_amount = round(total_price * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  text = (
      "💳 <b>БРОНИРОВАНИЕ ОПЛАТЫ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• <b>Сумма к списанию:</b> <b>{total_price}$</b> <i>(≈ {local_str}"
      f" {curr_symbol})</i>\n\n"
      "🛡️ Расчеты проводятся строго через защищенный криптовалютный шлюз.\n\n"
      "Выберите уровень подготовки:"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я опытный пользователь крипто",
                  callback_data="crypto_expert",
              )
          ],
          [
              InlineKeyboardButton(
                  text="❓ Нужен гайд по оплате (Новичкам)",
                  callback_data="crypto_guide",
              )
          ],
      ]
  )

  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === МИНИ-ГАЙД ДЛЯ НОВИЧКОВ ===
@router.callback_query(F.data == "crypto_guide")
async def process_crypto_guide(callback: CallbackQuery):
  text = (
      "📖 <b>РУКОВОДСТВО ПО ОПЛАТЕ КРИПТОВАЛЮТОЙ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Оплату можно легко произвести с любой банковской карты (Visa/Mastercard,"
      " Сбер, Тинькофф, Казкоммерц и др.):\n\n"
      "1. Воспользуйтесь официальным мониторингом обменников:"
      " <b>https://exchangesumo.com</b>\n"
      "2. В столбце «Отдаете» выберите вашу локальную валюту и банк.\n"
      "3. В столбце «Получаете» выберите <b>USDT (TRC20 / BEP20), TON или"
      " Bitcoin (BTC)</b>.\n"
      "4. Выберите подходящий по лимитам обменный пункт из списка.\n"
      "5. Заполните реквизиты нашего кошелька (которые выдадим на следующем"
      " шаге) и совершите перевод.\n\n"
      "Как будете готовы, нажмите кнопку ниже:"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🟢 Перейти к выбору сети", callback_data="crypto_expert"
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ Назад к оплате", callback_data="go_to_payment"
              )
          ],
      ]
  )

  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === ВЫБОР СПОСОБА ОПЛАТЫ (BEP-20 / TON / TRC-20 / BTC) ===
@router.callback_query(F.data == "crypto_expert")
async def process_crypto_expert(callback: CallbackQuery, state: FSMContext):
  text = (
      "💎 <b>ВЫБОР КРИПТОСЕТИ ДЛЯ ПЕРЕВОДА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Выберите предпочтительную блокчейн-сеть:"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🔴 USDT (TRC-20)", callback_data="pay_trc20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🟢 USDT (BEP-20)", callback_data="pay_bep20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🔵 TON Network", callback_data="pay_ton"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🟠 Bitcoin (BTC)", callback_data="pay_btc"
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ Назад", callback_data="go_to_payment"
              )
          ],
      ]
  )

  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === ОПЛАТА TRC-20 ===
@router.callback_query(F.data == "pay_trc20")
async def process_pay_trc20(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)
  curr_symbol = data.get("curr_symbol", "USD")
  curr_code = data.get("curr_code", "USD")
  rate = await get_exchange_rate(curr_code)
  local_amount = round(total_price * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  payment_text = (
      "🔴 <b>РЕКВИЗИТЫ: USDT (TRC-20)</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• <b>Сумма к оплате:</b> <b>{total_price}$</b> <i>(≈ {local_str}"
      f" {curr_symbol})</i>\n"
      "• <b>Сеть:</b> TRC-20 (Tron)\n"
      "• <b>Адрес кошелька:</b>\n"
      "<code>TYd1ekJgTHnFfgAVYXsi7689GaG5oZN3Xe</code>\n\n"
      "⚠️ <b>ВАЖНО:</b>\n"
      "<i>Переводите строго точную сумму. После транзакции обязательно"
      " прикрепите скриншот чека кнопкой ниже.</i>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ask_for_receipt",
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ К выбору сети", callback_data="crypto_expert"
              )
          ],
      ]
  )

  await callback.message.edit_text(
      payment_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === ОПЛАТА BEP-20 ===
@router.callback_query(F.data == "pay_bep20")
async def process_pay_bep20(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)
  curr_symbol = data.get("curr_symbol", "USD")
  curr_code = data.get("curr_code", "USD")
  rate = await get_exchange_rate(curr_code)
  local_amount = round(total_price * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  payment_text = (
      "🟢 <b>РЕКВИЗИТЫ: USDT (BEP-20)</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• <b>Сумма к оплате:</b> <b>{total_price}$</b> <i>(≈ {local_str}"
      f" {curr_symbol})</i>\n"
      "• <b>Сеть:</b> BEP-20 (Binance Smart Chain)\n"
      "• <b>Адрес кошелька:</b>\n"
      "<code>0x0A6C6634f8FD920a5E9E0d241CD46d6C15377f39</code>\n\n"
      "⚠️ <b>ВАЖНО:</b>\n"
      "<i>Переводите строго точную сумму. После транзакции обязательно"
      " прикрепите скриншот чека кнопкой ниже.</i>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ask_for_receipt",
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ К выбору сети", callback_data="crypto_expert"
              )
          ],
      ]
  )

  await callback.message.edit_text(
      payment_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === ОПЛАТА TON ===
@router.callback_query(F.data == "pay_ton")
async def process_pay_ton(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)
  curr_symbol = data.get("curr_symbol", "USD")
  curr_code = data.get("curr_code", "USD")
  rate = await get_exchange_rate(curr_code)
  local_amount = round(total_price * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  payment_text = (
      "🔵 <b>РЕКВИЗИТЫ: TON NETWORK</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• <b>Сумма к оплате:</b> <b>{total_price}$</b> <i>(≈ {local_str}"
      f" {curr_symbol})</i>\n"
      "• <b>Сеть:</b> TON\n"
      "• <b>Адрес кошелька:</b>\n"
      "<code>UQDwk7PZoWr0zHv-BItBEGxnq4uyj81z6BlIw74heDgF-Shd</code>\n\n"
      "⚠️ <b>ВАЖНО:</b>\n"
      "<i>Переводите строго точную сумму. После транзакции обязательно"
      " прикрепите скриншот чека кнопкой ниже.</i>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ask_for_receipt",
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ К выбору сети", callback_data="crypto_expert"
              )
          ],
      ]
  )

  await callback.message.edit_text(
      payment_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === ОПЛАТА BITCOIN (BTC) ===
@router.callback_query(F.data == "pay_btc")
async def process_pay_btc(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)
  curr_symbol = data.get("curr_symbol", "USD")
  curr_code = data.get("curr_code", "USD")
  rate = await get_exchange_rate(curr_code)
  local_amount = round(total_price * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  payment_text = (
      "🟠 <b>РЕКВИЗИТЫ: BITCOIN (BTC)</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• <b>Сумма к оплате:</b> <b>{total_price}$</b> <i>(≈ {local_str}"
      f" {curr_symbol})</i>\n"
      "• <b>Сеть:</b> Bitcoin\n"
      "• <b>Адрес кошелька:</b>\n"
      "<code>bc1qj7xy0645vcza7l3et5s8nuahllua9a439c0795</code>\n\n"
      "⚠️ <b>ВАЖНО:</b>\n"
      "<i>Переводите строго точную сумму. После транзакции обязательно"
      " прикрепите скриншот чека кнопкой ниже.</i>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ask_for_receipt",
              )
          ],
          [
              InlineKeyboardButton(
                  text="◀️ К выбору сети", callback_data="crypto_expert"
              )
          ],
      ]
  )

  await callback.message.edit_text(
      payment_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === ЗАПРОС ЧЕКА У ПОЛЬЗОВАТЕЛЯ ===
@router.callback_query(F.data == "ask_for_receipt")
async def ask_for_receipt(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.receipt)
  text = (
      "🧾 <b>ПОДТВЕРЖДЕНИЕ ТРАНЗАКЦИИ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Отправьте в чат <b>фотографию или скриншот чека</b> о перечислении"
      " средств.\n<i>Без подтверждающего скриншота система не сможет передать"
      " заявку в работу.</i>"
  )
  await callback.message.edit_text(text, parse_mode="HTML")
  await callback.answer()


# === ПОЛУЧЕНИЕ ЧЕКА И СОХРАНЕНИЕ ===
@router.message(OrderForm.receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext):
  user = message.from_user
  data = await state.get_data()

  order_info = {
      "service_name": data.get("service_name"),
      "total_price": data.get("total_price"),
      "status": "⏳ Проверка транзакции",
  }

  user_id = user.id
  if user_id not in USER_ORDERS:
    USER_ORDERS[user_id] = []
  USER_ORDERS[user_id].append(order_info)

  final_text = (
      "✅ <b>ЗАЯВКА И ЧЕК УСПЕШНО ПРИНЯТЫ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Оператор проверяет поступление средств в сети.\n"
      "Связь с вами будет установлена в течение <b>15-25 минут</b>."
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏠 На главную", callback_data="back_home"
              )
          ]
      ]
  )

  await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
  await state.clear()


@router.message(OrderForm.receipt, ~F.photo)
async def process_receipt_invalid(message: Message):
  await message.answer(
      "⚠️ Пожалуйста, отправьте <b>изображение (скриншот) чека</b>."
      " Текстовые сообщения не принимаются системой проверки!"
  )


# =====================================================================
# === АНКЕТА ДЛЯ ТРУДОУСТРОЙСТВА В КОМАНДУ (ВАКАНСИИ) ===================
# =====================================================================


@router.callback_query(F.data == "start_vacancy")
async def process_start_vacancy(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  await state.set_state(VacancyForm.country)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🇺🇦 Украина", callback_data="vcountry_Ukraine"
              ),
              InlineKeyboardButton(
                  text="🇷🇺 Россия", callback_data="vcountry_Russia"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇧🇾 Беларусь", callback_data="vcountry_Belarus"
              ),
              InlineKeyboardButton(
                  text="🇰🇿 Казахстан", callback_data="vcountry_Kazakhstan"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇲🇩 Молдова", callback_data="vcountry_Moldova"
              ),
              InlineKeyboardButton(
                  text="🇺🇿 Узбекистан", callback_data="vcountry_Uzbekistan"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇰🇬 Кыргызстан", callback_data="vcountry_Kyrgyzstan"
              ),
              InlineKeyboardButton(
                  text="🇹🇯 Таджикистан", callback_data="vcountry_Tajikistan"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇬🇪 Грузия", callback_data="vcountry_Georgia"
              ),
              InlineKeyboardButton(
                  text="🇦🇲 Армения", callback_data="vcountry_Armenia"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="🇦🇿 Азербайджан", callback_data="vcountry_Azerbaijan"
              )
          ],
          [InlineKeyboardButton(text="❌ Отмена", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 1 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Выберите вашу страну текущего пребывания:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


@router.callback_query(VacancyForm.country, F.data.startswith("vcountry_"))
async def process_vacancy_country(callback: CallbackQuery, state: FSMContext):
  c_code = callback.data.split("_")[1]
  names = {
      "Ukraine": "Украина",
      "Russia": "Россия",
      "Belarus": "Беларусь",
      "Kazakhstan": "Казахстан",
      "Молдова": "Молдова",
      "Uzbekistan": "Узбекистан",
      "Kyrgyzstan": "Кыргызстан",
      "Tajikistan": "Таджикистан",
      "Georgia": "Грузия",
      "Armenia": "Армения",
      "Azerbaijan": "Азербайджан",
  }
  selected = names.get(c_code, c_code)
  curr_info = COUNTRY_CURRENCIES.get(
      selected, {"code": "USD", "symbol": "USD"}
  )
  await state.update_data(
      country=selected,
      curr_code=curr_info["code"],
      curr_symbol=curr_info["symbol"],
  )
  await state.set_state(VacancyForm.city)
  await callback.message.edit_text(
      f"⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 2 из 8</b>\n"
      f"━━━━━━━━━━━━━━━━━━━\n\n"
      f"Страна: <b>{selected}</b>\n\n"
      "Введите название вашего города текстом:",
      parse_mode="HTML",
  )
  await callback.answer()


@router.message(VacancyForm.city, F.text)
async def process_vacancy_city(message: Message, state: FSMContext):
  await state.update_data(city=message.text.strip())
  await state.set_state(VacancyForm.name)
  await message.answer(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 3 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Введите ваше имя или рабочий псевдоним:",
      parse_mode="HTML",
  )


@router.message(VacancyForm.name, F.text)
async def process_vacancy_name(message: Message, state: FSMContext):
  await state.update_data(name=message.text.strip())
  await state.set_state(VacancyForm.age)
  await message.answer(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 4 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Укажите ваш возраст:",
      parse_mode="HTML",
  )


@router.message(VacancyForm.age, F.text)
async def process_vacancy_age(message: Message, state: FSMContext):
  await state.update_data(age=message.text.strip())
  await state.set_state(VacancyForm.parameters)
  await message.answer(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 5 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Укажите ваши физические параметры (рост, вес, телосложение):\n"
      "<i>Пример: 185 см, 95 кг, плотное</i>",
      parse_mode="HTML",
  )


@router.message(VacancyForm.parameters, F.text)
async def process_vacancy_parameters(message: Message, state: FSMContext):
  await state.update_data(parameters=message.text.strip())
  await state.set_state(VacancyForm.sports_exp)
  await message.answer(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 6 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Был ли опыт в единоборствах или спортивный стаж? Укажите детали:",
      parse_mode="HTML",
  )


@router.message(VacancyForm.sports_exp, F.text)
async def process_vacancy_sports_exp(message: Message, state: FSMContext):
  await state.update_data(sports_exp=message.text.strip())
  await state.set_state(VacancyForm.experience)
  await message.answer(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 7 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Опишите ваш предыдущий опыт в аналогичной сфере:",
      parse_mode="HTML",
  )


@router.message(VacancyForm.experience, F.text)
async def process_vacancy_experience(message: Message, state: FSMContext):
  await state.update_data(experience=message.text.strip())
  await state.set_state(VacancyForm.photo)
  await message.answer(
      "⚡ <b>КАРЬЕРА В КОМАНДЕ — ШАГ 8 из 8</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "📸 Прикрепите актуальное фото физической формы (можно скрыть лицо для безопасности).",
      parse_mode="HTML",
  )


@router.message(VacancyForm.photo, F.photo)
async def process_vacancy_photo(message: Message, state: FSMContext):
  photo_id = message.photo[-1].file_id
  await state.update_data(photo=photo_id)

  data = await state.get_data()
  curr_code = data.get("curr_code", "USD")
  curr_symbol = data.get("curr_symbol", "USD")
  rate = await get_exchange_rate(curr_code)
  deposit_usd = 200
  local_amount = round(deposit_usd * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  text = (
      "✅ <b>АНКЕТА УСПЕШНО ЗАРЕГИСТРИРОВАНА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Для подтверждения серьезности намерений и доступа к заданиям необходимо"
      " внести гарантийный залог в размере <b>200$</b> <i>(≈ "
      f"{local_str} {curr_symbol})</i>.\n\n"
      "⚠️ Оплата производится через криптошлюз."
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💳 Внести залог (200$)", callback_data="vacancy_pay"
              )
          ]
      ]
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(VacancyForm.photo, ~F.photo)
async def process_vacancy_photo_invalid(message: Message):
  await message.answer(
      "⚠️ Пожалуйста, прикрепите именно <b>фотографию</b> (изображением)!"
  )


@router.callback_query(F.data == "vacancy_pay")
async def process_vacancy_pay(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  curr_code = data.get("curr_code", "USD")
  curr_symbol = data.get("curr_symbol", "USD")
  rate = await get_exchange_rate(curr_code)
  deposit_usd = 200
  local_amount = round(deposit_usd * rate)
  local_str = f"{local_amount:,}".replace(",", " ")

  text = (
      "🛡️ <b>ВНЕСЕНИЕ ГАРАНТИЙНОГО ЗАЛОГА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• <b>Сумма:</b> <b>{deposit_usd}$</b> <i>(≈ {local_str} {curr_symbol})</i>\n"
      "• <b>Назначение:</b> Страховой залог сотрудника\n\n"
      "Выберите сеть для перевода:"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🔴 USDT (TRC-20)", callback_data="vpay_trc20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🟢 USDT (BEP-20)", callback_data="vpay_bep20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🔵 TON Network", callback_data="vpay_ton"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🟠 Bitcoin (BTC)", callback_data="vpay_btc"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🏠 На главную", callback_data="back_home"
              )
          ],
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "vpay_trc20")
async def vpay_trc20(callback: CallbackQuery):
  text = (
      "🔴 <b>ЗАЛОГ: USDT (TRC-20)</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      " 200$\n• <b>Адрес:</b>\n<code>TYd1ekJgTHnFfgAVYXsi7689GaG5oZN3Xe</code>\n\n⚠️"
      " После перевода отправьте скриншот чека кнопкой ниже."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="vacancy_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "vpay_bep20")
async def vpay_bep20(callback: CallbackQuery):
  text = (
      "🟢 <b>ЗАЛОГ: USDT (BEP-20)</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      " 200$\n• <b>Адрес:</b>\n<code>0x0A6C6634f8FD920a5E9E0d241CD46d6C15377f39</code>\n\n⚠️"
      " После перевода отправьте скриншот чека кнопкой ниже."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="vacancy_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "vpay_ton")
async def vpay_ton(callback: CallbackQuery):
  text = (
      "🔵 <b>ЗАЛОГ: TON NETWORK</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      " 200$\n• <b>Адрес:</b>\n<code>UQDwk7PZoWr0zHv-BItBEGxnq4uyj81z6BlIw74heDgF-Shd</code>\n\n⚠️"
      " После перевода отправьте скриншот чека кнопкой ниже."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="vacancy_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "vpay_btc")
async def vpay_btc(callback: CallbackQuery):
  text = (
      "🟠 <b>ЗАЛОГ: BITCOIN (BTC)</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      " 200$\n• <b>Адрес:</b>\n<code>bc1qj7xy0645vcza7l3et5s8nuahllua9a439c0795</code>\n\n⚠️"
      " После перевода отправьте скриншот чека кнопкой ниже."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="vacancy_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "vacancy_ask_receipt")
async def vacancy_ask_receipt(callback: CallbackQuery, state: FSMContext):
  await state.set_state(VacancyForm.receipt)
  text = (
      "🧾 <b>ПОДТВЕРЖДЕНИЕ ЗАЛОГА</b>\n━━━━━━━━━━━━━━━━━━━\n\nОтправьте в чат"
      " <b>скриншот или фото чека</b> об успешном переводе гарантийного залога."
  )
  await callback.message.edit_text(text, parse_mode="HTML")
  await callback.answer()


@router.message(VacancyForm.receipt, F.photo)
async def process_vacancy_receipt(message: Message, state: FSMContext):
  final_text = (
      "✅ <b>ЗАЯВКА НА ТРУДОУСТРОЙСТВО ПРИНЯТА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Анкета и чек переданы руководству безопасности.\n"
      "Модератор свяжется с вами для выдачи задач."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏠 На главную", callback_data="back_home"
              )
          ]
      ]
  )
  await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
  await state.clear()


@router.message(VacancyForm.receipt, ~F.photo)
async def process_vacancy_receipt_invalid(message: Message):
  await message.answer("⚠️ Отправьте чек в виде <b>изображения (фото)</b>!")


# =====================================================================
# === ПОКУПКА РЕКЛАМЫ (СОТРУДНИЧЕСТВО) =================================
# =====================================================================


@router.callback_query(F.data == "start_ads")
async def process_start_ads(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  await state.set_state(AdForm.platform)
  text = (
      "📢 <b>МЕДИЙНОЕ СОТРУДНИЧЕСТВО И РЕКЛАМА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Выберите площадку для размещения вашей рекламной кампании:"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🤖 Реклама в боте", callback_data="adplat_bot"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📢 Реклама в канале", callback_data="adplat_channel"
              )
          ],
          [InlineKeyboardButton(text="◀️ На главную", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(AdForm.platform, F.data.startswith("adplat_"))
async def process_ad_platform(callback: CallbackQuery, state: FSMContext):
  plat_code = callback.data.split("_")[1]
  platform_name = (
      "Реклама в боте" if plat_code == "bot" else "Реклама в канале"
  )
  await state.update_data(platform=platform_name, plat_code=plat_code)
  await state.set_state(AdForm.duration)

  current_date = datetime.date.today()
  base_date = datetime.date(2026, 1, 1)
  days_passed = max(0, (current_date - base_date).days)
  total_users = 1037 + days_passed * 41

  kb_list = [
      [InlineKeyboardButton(text="⏱️ 24 часа — 10$", callback_data="addur_24h_10")],
      [InlineKeyboardButton(text="📅 3 дня — 20$", callback_data="addur_3d_20")],
      [InlineKeyboardButton(text="📅 7 дней — 50$", callback_data="addur_7d_50")],
      [
          InlineKeyboardButton(
              text="🔥 30 дней — 200$", callback_data="addur_30d_200"
          )
      ],
  ]
  kb_list.append([InlineKeyboardButton(text="◀️ Назад", callback_data="start_ads")])
  keyboard = InlineKeyboardMarkup(inline_keyboard=kb_list)

  if plat_code == "bot":
    text = (
        f"🤖 <b>Площадка: Реклама в боте</b>\n"
        f"👥 База активных пользователей: <b>{total_users}</b> <i>(прирост +41 ежедневно)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите срок размещения:"
    )
  else:
    text = (
        "📢 <b>Площадка: Реклама в канале</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите срок размещения:"
    )

  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(AdForm.duration, F.data.startswith("addur_"))
async def process_ad_duration(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  duration_code = parts[1]
  price = int(parts[2])

  dur_map = {
      "24h": "24 часа",
      "3d": "3 дня",
      "7d": "7 дней",
      "30d": "30 дней",
  }
  duration_str = dur_map.get(duration_code, duration_code)

  await state.update_data(duration=duration_str, ad_price=price)
  await state.set_state(AdForm.niche)

  text = (
      f"📢 <b>ТАРИФ: {duration_str} — {price}$</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "<b>Шаг 3: Тематика (ниша) проекта</b>\n"
      "Введите краткое описание или нишу вашего ресурса:"
  )
  await callback.message.edit_text(text, parse_mode="HTML")
  await callback.answer()


@router.message(AdForm.niche, F.text)
async def process_ad_niche(message: Message, state: FSMContext):
  await state.update_data(niche=message.text.strip())
  await state.set_state(AdForm.link)
  await message.answer(
      "🔗 <b>Шаг 4: Целевая ссылка</b>\n━━━━━━━━━━━━━━━━━━━\nВведите ссылку на ваш"
      " ресурс, бота или канал:",
      parse_mode="HTML",
  )


@router.message(AdForm.link, F.text)
async def process_ad_link(message: Message, state: FSMContext):
  await state.update_data(link=message.text.strip())
  await state.set_state(AdForm.creative)
  await message.answer(
      "🎨 <b>Шаг 5: Рекламный креатив</b>\n━━━━━━━━━━━━━━━━━━━\nОтправьте готовый"
      " пост, изображение или видеоматериал для публикации:",
      parse_mode="HTML",
  )


@router.message(AdForm.creative)
async def process_ad_creative(message: Message, state: FSMContext):
  if message.photo:
    creative_desc = f"[Фотография] {message.caption or ''}"
  elif message.video:
    creative_desc = f"[Видео] {message.caption or ''}"
  else:
    creative_desc = message.text or "[Текст]"

  await state.update_data(creative=creative_desc)
  data = await state.get_data()
  price = data.get("ad_price", 0)

  text = (
      "🎉 <b>ЗАЯВКА НА РЕКЛАМУ СФОРМИРОВАНА</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      f"• Площадка: <b>{data.get('platform')}</b>\n"
      f"• Срок: <b>{data.get('duration')}</b>\n"
      f"• Ниша: <b>{data.get('niche')}</b>\n"
      f"• Ссылка: <b>{data.get('link')}</b>\n"
      f"• Креатив: <b>{creative_desc}</b>\n\n"
      f"💵 <b>К оплате: {price}$</b>\n\n"
      "⚠️ <b>Оплата принимается строго в криптовалюте!</b>\n"
      "Нажмите кнопку ниже для проведения оплаты 👇"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💳 Оплатить рекламу", callback_data="ad_pay_select"
              )
          ]
      ]
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "ad_pay_select")
async def process_ad_pay_select(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  price = data.get("ad_price", 0)

  text = (
      f"💳 <b>ОПЛАТА РЕКЛАМНОЙ КАМПАНИИ ({price}$)</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Выберите сеть для перевода:"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🔴 USDT (TRC-20)", callback_data="adpay_trc20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🟢 USDT (BEP-20)", callback_data="adpay_bep20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🔵 TON Network", callback_data="adpay_ton"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🟠 Bitcoin (BTC)", callback_data="adpay_btc"
              )
          ],
          [InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")],
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "adpay_trc20")
async def adpay_trc20(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  price = data.get("ad_price", 0)
  text = (
      f"🔴 <b>РЕКЛАМА: USDT (TRC-20)</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      f" <b>{price}$</b>\n• <b>Адрес:</b>\n<code>TYd1ekJgTHnFfgAVYXsi7689GaG5oZN3Xe</code>\n\n⚠️"
      " После перевода прикрепите чек."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ad_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "adpay_bep20")
async def adpay_bep20(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  price = data.get("ad_price", 0)
  text = (
      f"🟢 <b>РЕКЛАМА: USDT (BEP-20)</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      f" <b>{price}$</b>\n• <b>Адрес:</b>\n<code>0x0A6C6634f8FD920a5E9E0d241CD46d6C15377f39</code>\n\n⚠️"
      " После перевода прикрепите чек."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ad_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "adpay_ton")
async def adpay_ton(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  price = data.get("ad_price", 0)
  text = (
      f"🔵 <b>РЕКЛАМА: TON NETWORK</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      f" <b>{price}$</b>\n• <b>Адрес:</b>\n<code>UQDwk7PZoWr0zHv-BItBEGxnq4uyj81z6BlIw74heDgF-Shd</code>\n\n⚠️"
      " После перевода прикрепите чек."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ad_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "adpay_btc")
async def adpay_btc(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  price = data.get("ad_price", 0)
  text = (
      f"🟠 <b>РЕКЛАМА: BITCOIN (BTC)</b>\n━━━━━━━━━━━━━━━━━━━\n\n• <b>Сумма:</b>"
      f" <b>{price}$</b>\n• <b>Адрес:</b>\n<code>bc1qj7xy0645vcza7l3et5s8nuahllua9a439c0795</code>\n\n⚠️"
      " После перевода прикрепите чек."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Я оплатил(-а), прикрепить чек",
                  callback_data="ad_ask_receipt",
              )
          ]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


@router.callback_query(F.data == "ad_ask_receipt")
async def ad_ask_receipt(callback: CallbackQuery, state: FSMContext):
  await state.set_state(AdForm.receipt)
  text = (
      "🧾 <b>ПОДТВЕРЖДЕНИЕ ОПЛАТЫ РЕКЛАМЫ</b>\n━━━━━━━━━━━━━━━━━━━\n\nОтправьте в"
      " чат <b>фотографию или скриншот чека</b> о переводе средств."
  )
  await callback.message.edit_text(text, parse_mode="HTML")
  await callback.answer()


@router.message(AdForm.receipt, F.photo)
async def process_ad_receipt(message: Message, state: FSMContext):
  final_text = (
      "✅ <b>ЗАЯВКА НА РЕКЛАМУ И ЧЕК ПРИНЯТЫ</b>\n"
      "━━━━━━━━━━━━━━━━━━━\n\n"
      "Модератор проверит поступление средств в течение <b>15-25 минут</b> и"
      " активирует размещение."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏠 На главную", callback_data="back_home"
              )
          ]
      ]
  )
  await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
  await state.clear()


@router.message(AdForm.receipt, ~F.photo)
async def process_ad_receipt_invalid(message: Message):
  await message.answer("⚠️ Пожалуйста, отправьте чек в виде <b>фотографии</b>!")


# === ВЕБ-СЕРВЕР ДЛЯ ЗАЩИТЫ ОТ СНА СЕРВЕРА (RENDER) ===
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
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
