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
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Впишите сюда ваш Telegram ID администратора (числом)
# Чтобы узнать свой ID, можно написать боту @userinfobot
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
  raise ValueError("❌ BOT_TOKEN не найден!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderForm(StatesGroup):
  service = State()
  addon = State()
  country = State()
  city = State()
  address = State()
  photos = State()
  task = State()
  urgency = State()


# База данных в памяти для хранения заказов пользователей
# Структура: {user_id: [ {order_details}, ... ]}
USER_ORDERS = {}

router = Router()


# === ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ РЕПУТАЦИИ (РАСТЕТ ЕЖЕДНЕВНО) ===
async def get_reputation_text_and_keyboard():
  current_date = datetime.date.today()
  base_date = datetime.date(2026, 1, 1)
  days_passed = max(0, (current_date - base_date).days)

  # Выполненные заказы стартуют от 3500+ и плавно растут каждый день до 20000
  completed = min(3752 + days_passed * 25, 20000)

  # Используем дату как seed, чтобы цифры за день не прыгали каждую секунду
  rng = random.Random(current_date.toordinal())
  in_progress = rng.randint(170, 500)
  new_requests = rng.randint(30, 80)

  text = (
      "📊 <b>Наша статистика и репутация:</b>\n\n"
      f"• Выполненных заказов: <b>{completed}</b>\n"
      f"• Заказов в работе: <b>{in_progress}</b>\n"
      f"• Новых заявок: <b>{new_requests}</b>\n\n"
      "<i>Мы дорожим своей репутацией и гарантируем конфиденциальность.</i>"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]
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
                  text="🛒 Сделать заказ", callback_data="start_order"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📦 Мои заказы", callback_data="my_orders"
              ),
              InlineKeyboardButton(
                  text="📊 Наша репутация", callback_data="reputation"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="💬 Связаться с администратором",
                  callback_data="contact_admin",
              )
          ],
      ]
  )
  text = (
      "<b>Добро пожаловать в сервис «СПОРТ УСЛУГИ»!</b> 🏅\n\n"
      "Мы предоставляем профессиональные услуги и решение ваших задач быстро, "
      "качественно и конфиденциально.\n\n"
      "Выберите нужный пункт в меню ниже:"
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# Команда /reputation
@router.message(Command("reputation"))
async def cmd_reputation(message: Message):
  text, keyboard = await get_reputation_text_and_keyboard()
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# Команда /my_orders
@router.message(Command("my_orders"))
async def cmd_my_orders(message: Message):
  user_id = message.from_user.id
  orders = USER_ORDERS.get(user_id, [])

  if not orders:
    text = (
        "📦 <b>Мои заказы</b>\n\nУ вас пока нет активных или завершенных"
        " заказов."
    )
  else:
    text = "📦 <b>Ваши заказы:</b>\n\n"
    for idx, ord_data in enumerate(orders, 1):
      text += (
          f"<b>Заказ #{idx}</b>\n• Услуга: {ord_data['service_name']}\n• Сумма:"
          f" {ord_data['total_price']}$\n• Статус: {ord_data['status']}\n\n"
      )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]
      ]
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# Команды /order и /make_order для создания заказа
@router.message(Command("order", "make_order"))
async def cmd_order(message: Message, state: FSMContext):
  await state.clear()
  await state.set_state(OrderForm.service)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="👊 Избить (100$)", callback_data="srv_Избить_100"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🧎 Извинение на коленях (200$)",
                  callback_data="srv_Извинение_на_коленях_200",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🦴 Сломать пальцы (300$)",
                  callback_data="srv_Сломать_пальцы_300",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🦾 Сломать конечности (500$)",
                  callback_data="srv_Сломать_конечности_500",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🚗 Вывести в лес в багажнике (700$)",
                  callback_data="srv_Вывести_в_лес_в_багажнике_700",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🪓 Отрубить конечности (1000$)",
                  callback_data="srv_Отрубить_конечности_1000",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎂 Тортик (5000$)", callback_data="srv_Тортик_5000"
              )
          ],
          [
              InlineKeyboardButton(
                  text="⬅️ Отмена", callback_data="back_home"
              )
          ],
      ]
  )
  await message.answer(
      "<b>Шаг 1 из 7: Выбор услуги</b>\n\nВыберите нужную услугу:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# === РЕПУТАЦИЯ (КНОПКА) ===
@router.callback_query(F.data == "reputation")
async def show_reputation(callback: CallbackQuery):
  text, keyboard = await get_reputation_text_and_keyboard()
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === СВЯЗЬ С АДМИНИСТРАТОРОМ ===
@router.callback_query(F.data == "contact_admin")
async def contact_admin_info(callback: CallbackQuery):
  text = (
      "💬 <b>Связь с администрацией</b>\n\n"
      "Модератор с вами сам свяжется после оплаты заказа."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]
      ]
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === МОИ ЗАКАЗЫ (КНОПКА) ===
@router.callback_query(F.data == "my_orders")
async def show_my_orders(callback: CallbackQuery):
  user_id = callback.from_user.id
  orders = USER_ORDERS.get(user_id, [])

  if not orders:
    text = (
        "📦 <b>Мои заказы</b>\n\nУ вас пока нет активных или завершенных"
        " заказов."
    )
  else:
    text = "📦 <b>Ваши заказы:</b>\n\n"
    for idx, ord_data in enumerate(orders, 1):
      text += (
          f"<b>Заказ #{idx}</b>\n• Услуга: {ord_data['service_name']}\n• Сумма:"
          f" {ord_data['total_price']}$\n• Статус: {ord_data['status']}\n\n"
      )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")]
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
                  text="🛒 Сделать заказ", callback_data="start_order"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📦 Мои заказы", callback_data="my_orders"
              ),
              InlineKeyboardButton(
                  text="📊 Наша репутация", callback_data="reputation"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="💬 Связаться с администратором",
                  callback_data="contact_admin",
              )
          ],
      ]
  )
  text = (
      "<b>Добро пожаловать в сервис «СПОРТ УСЛУГИ»!</b> 🏅\n\n"
      "Выберите нужный пункт в меню ниже:"
  )
  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === НАЧАЛО ЗАКАЗА: ВЫБОР УСЛУГИ (КНОПКА) ===
@router.callback_query(F.data == "start_order")
async def process_start_order(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.service)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="👊 Избить (100$)", callback_data="srv_Избить_100"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🧎 Извинение на коленях (200$)",
                  callback_data="srv_Извинение_на_коленях_200",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🦴 Сломать пальцы (300$)",
                  callback_data="srv_Сломать_пальцы_300",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🦾 Сломать конечности (500$)",
                  callback_data="srv_Сломать_конечности_500",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🚗 Вывести в лес в багажнике (700$)",
                  callback_data="srv_Вывести_в_лес_в_багажнике_700",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🪓 Отрубить конечности (1000$)",
                  callback_data="srv_Отрубить_конечности_1000",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎂 Тортик (5000$)", callback_data="srv_Тортик_5000"
              )
          ],
          [
              InlineKeyboardButton(
                  text="⬅️ Отмена", callback_data="back_home"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      "<b>Шаг 1 из 7: Выбор услуги</b>\n\nВыберите нужную услугу:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


# === ВЫБОР УСЛУГИ -> ДОП. ОТЧЕТ ===
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
                  text="📸 Фотоотчет (Бесплатно)", callback_data="addon_photo_0"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎥 Видеоотчет (50$)", callback_data="addon_video_50"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      f"<b>Шаг 2 из 7: Отчет</b>\n\nВыбрана услуга: <b>{service_name}</b>"
      f" ({price}$)\n\nВыберите тип отчета:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


# === ДОП. ОТЧЕТ -> СТРАНА ===
@router.callback_query(OrderForm.addon, F.data.startswith("addon_"))
async def process_addon(callback: CallbackQuery, state: FSMContext):
  parts = callback.data.split("_")
  addon_price = int(parts[-1])
  addon_type = "Видеоотчет" if addon_price > 0 else "Фотоотчет"

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
      ]
  )
  await callback.message.edit_text(
      "<b>Шаг 3 из 7: Выбор страны</b>\n\nВыберите страну из списка:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


# === СТРАНА -> ГОРОД ===
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
  }
  selected = names.get(c_code, c_code)

  await state.update_data(country=selected)
  await state.set_state(OrderForm.city)
  await callback.message.edit_text(
      f"<b>Шаг 4 из 7: Город</b>\n\nВыбрано: <b>{selected}</b>\n\nВведите"
      " название города текстом:",
      parse_mode="HTML",
  )
  await callback.answer()


# === ГОРОД -> АДРЕС ===
@router.message(OrderForm.city, F.text)
async def process_city(message: Message, state: FSMContext):
  await state.update_data(city=message.text.strip())
  await state.set_state(OrderForm.address)
  await message.answer(
      f"<b>Шаг 5 из 7: Адрес цели</b>\n\nГород:"
      f" <b>{message.text.strip()}</b>\n\nВведите точный адрес цели:",
      parse_mode="HTML",
  )


# === АДРЕС -> ФОТО ===
@router.message(OrderForm.address, F.text)
async def process_address(message: Message, state: FSMContext):
  await state.update_data(address=message.text.strip(), photos=[])
  await state.set_state(OrderForm.photos)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Готово / Без фото", callback_data="finish_photos"
              )
          ]
      ]
  )
  await message.answer(
      "<b>Шаг 6 из 7: Фотографии цели</b>\n\n📷 Отправьте от 1 до 3 фото. Как"
      " закончите, нажмите «Готово»:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


@router.message(OrderForm.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
  data = await state.get_data()
  photos = data.get("photos", [])
  if len(photos) >= 3:
    await message.answer("⚠️ Уже добавлено 3 фото. Нажмите кнопку «Готово».")
    return

  photos.append(message.photo[-1].file_id)
  await state.update_data(photos=photos)

  btn_text = (
      f"✅ Готово ({len(photos)}/3)"
      if len(photos) < 3
      else "✅ Готово (3/3) — Далее"
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
      f"📸 Фото #{len(photos)} загружено!", reply_markup=keyboard
  )


@router.callback_query(OrderForm.photos, F.data == "finish_photos")
async def finish_photos(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.task)
  await callback.message.edit_text(
      "<b>Шаг 7 из 7: Задача</b>\n\nПодробно опишите, что нужно сделать:",
      parse_mode="HTML",
  )
  await callback.answer()


# === ЗАДАЧА -> СРОЧНОСТЬ ===
@router.message(OrderForm.task, F.text)
async def process_task(message: Message, state: FSMContext):
  await state.update_data(task=message.text.strip())
  await state.set_state(OrderForm.urgency)
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="⚡ Сейчас", callback_data="urgency_Сейчас"
              ),
              InlineKeyboardButton(
                  text="🕐 Сегодня", callback_data="urgency_Сегодня"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="📅 2-3 дня", callback_data="urgency_2-3_дня"
              )
          ],
      ]
  )
  await message.answer(
      "<b>Срочность выполнения</b>\n\nВыберите срочность:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# === СРОЧНОСТЬ -> СВОДКА И СУММА ===
@router.callback_query(OrderForm.urgency, F.data.startswith("urgency_"))
async def process_urgency(callback: CallbackQuery, state: FSMContext):
  urgency_raw = callback.data.split("_", 1)[1]
  u_map = {
      "Сейчас": "⚡ Сейчас",
      "Сегодня": "🕐 Сегодня",
      "2-3_дня": "📅 В течение 2-3 дней",
  }
  urgency = u_map.get(urgency_raw, urgency_raw)
  await state.update_data(urgency=urgency)

  data = await state.get_data()
  service_price = data.get("service_price", 0)
  addon_price = data.get("addon_price", 0)
  total_price = service_price + addon_price

  await state.update_data(total_price=total_price)

  summary_text = (
      "🎉 <b>Ваша анкета успешно сформирована!</b>\n\n"
      "📋 <b>Сводка заказа:</b>\n"
      f"• Услуга: <b>{data.get('service_name')}</b> ({service_price}$)\n"
      f"• Отчет: <b>{data.get('addon_type')}</b> ({addon_price}$)\n"
      f"• Страна: <b>{data.get('country')}</b>\n"
      f"• Город: <b>{data.get('city')}</b>\n"
      f"• Адрес: <b>{data.get('address')}</b>\n"
      f"• Фотографий: <b>{len(data.get('photos', []))}</b>\n"
      f"• Задача: <b>{data.get('task')}</b>\n"
      f"• Срочность: <b>{urgency}</b>\n\n"
      f"💵 <b>Итого к оплате:</b> <b>{total_price}$</b>\n\n"
      "Нажмите кнопку ниже для перехода к оплате 👇"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="💳 Оплатить", callback_data="go_to_payment")]
      ]
  )

  await callback.message.edit_text(
      summary_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === ВЫБОР СЕТИ ДЛЯ ОПЛАТЫ ===
@router.callback_query(F.data == "go_to_payment")
async def process_go_to_payment(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)

  text = (
      "💳 <b>ВЫБОР СПОСОБА ОПЛАТЫ</b>\n\n"
      f"• <b>Итого к оплате:</b> {total_price}$\n\n"
      "Пожалуйста, выберите сеть для перевода USDT:"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🟢 USDT (BEP-20)", callback_data="pay_bep20"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🔵 USDT (TON)", callback_data="pay_ton"
              )
          ],
      ]
  )

  await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
  await callback.answer()


# === ОПЛАТА BEP-20 ===
@router.callback_query(F.data == "pay_bep20")
async def process_pay_bep20(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  total_price = data.get("total_price", 250)

  payment_text = (
      "💳 <b>ОПЛАТА USDT (BEP-20)</b>\n\n"
      f"• <b>Сумма:</b> {total_price}$\n"
      "• <b>Сеть:</b> BEP-20\n"
      "• <b>Реквизиты для оплаты:</b>\n"
      "<code>0x01262ebbea8ffe27236a3ef152fc8a8f7b32ee8e</code>\n\n"
      "⚠️ <b>ВНИМАНИЕ!</b>\n"
      "<i>Если вы не производили оплату, не нажимайте кнопку «Оплачено» и не"
      " тратьте свое и чужое время — администратор связывается только после"
      " проверки реального перевода!</i>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Оплачено", callback_data="confirm_payment"
              )
          ],
          [
              InlineKeyboardButton(
                  text="⬅️ Назад к выбору сети", callback_data="go_to_payment"
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

  payment_text = (
      "💳 <b>ОПЛАТА USDT (TON)</b>\n\n"
      f"• <b>Сумма:</b> {total_price}$\n"
      "• <b>Сеть:</b> TON\n"
      "• <b>Реквизиты для оплаты:</b>\n"
      "<code>UQDdeysx3s0eh5wa-2-EAA8uMMWQS0exJVaOTbLvXU2iJmzA</code>\n\n"
      "⚠️ <b>ВНИМАНИЕ!</b>\n"
      "<i>Если вы не производили оплату, не нажимайте кнопку «Оплачено» и не"
      " тратьте свое и чужое время — администратор связывается только после"
      " проверки реального перевода!</i>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Оплачено", callback_data="confirm_payment"
              )
          ],
          [
              InlineKeyboardButton(
                  text="⬅️ Назад к выбору сети", callback_data="go_to_payment"
              )
          ],
      ]
  )

  await callback.message.edit_text(
      payment_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


# === КНОПКА "ОПЛАЧЕНО" -> УВЕДОМЛЕНИЕ АДМИНА И СОХРАНЕНИЕ ===
@router.callback_query(F.data == "confirm_payment")
async def process_confirm_payment(callback: CallbackQuery, state: FSMContext):
  user = callback.from_user
  data = await state.get_data()

  # Формируем запись для "Мои заказы"
  order_info = {
      "service_name": data.get("service_name"),
      "total_price": data.get("total_price"),
      "status": "⏳ Ожидает проверки оплаты",
  }

  user_id = user.id
  if user_id not in USER_ORDERS:
    USER_ORDERS[user_id] = []
  USER_ORDERS[user_id].append(order_info)

  # Отправляем полный чек администратору в личку (если указан ADMIN_ID)
  if ADMIN_ID != 0:
    username_str = f"@{user.username}" if user.username else f"ID: {user.id}"
    admin_text = (
        "🚨 <b>НОВЫЙ ЗАКАЗ И ОПЛАТА!</b> 🚨\n\n"
        f"👤 <b>Клиент:</b> {username_str} (ID: <code>{user.id}</code>)\n"
        f"• Услуга: <b>{data.get('service_name')}</b>\n"
        f"• Отчет: <b>{data.get('addon_type')}</b>\n"
        f"• Страна: <b>{data.get('country')}</b>\n"
        f"• Город: <b>{data.get('city')}</b>\n"
        f"• Адрес: <b>{data.get('address')}</b>\n"
        f"• Задача: <b>{data.get('task')}</b>\n"
        f"• Срочность: <b>{data.get('urgency')}</b>\n"
        f"• <b>Сумма к оплате:</b> {data.get('total_price')}$\n\n"
        "<i>Проверьте поступление средств по реквизитам!</i>"
    )
    try:
      await callback.bot.send_message(
          ADMIN_ID, admin_text, parse_mode="HTML"
      )
      # Пересылаем фото цели, если пользователь их загружал
      photos = data.get("photos", [])
      for photo_id in photos:
        await callback.bot.send_photo(ADMIN_ID, photo_id)
    except Exception as e:
      logger.error(f"Не удалось отправить уведомление админу: {e}")

  final_text = (
      "✅ <b>Заявка принята в обработку!</b>\n\n"
      "Администратор проверяет поступление средств. С вами свяжутся в"
      " течение <b>25 минут</b>."
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

  await callback.message.edit_text(
      final_text, reply_markup=keyboard, parse_mode="HTML"
  )
  await state.clear()
  await callback.answer()


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
