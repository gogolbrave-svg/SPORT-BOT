import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
  raise ValueError(
      "❌ Ошибка: Не найден BOT_TOKEN в переменных окружения или .env файле!"
  )

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Определение состояний FSM (шагов анкеты)
class OrderForm(StatesGroup):
  country = State()
  city = State()
  address = State()
  photos = State()
  task = State()
  urgency = State()


router = Router()


# ==========================================
# ШАГ 0: СТАРТ
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
  await state.clear()
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🛒 Сделать заказ", callback_data="start_order"
              )
          ]
      ]
  )
  welcome_text = (
      "<b>Добро пожаловать в сервис «СПОРТ УСЛУГИ»!</b> 🏅\n\n"
      "Мы предоставляем профессиональные услуги и решение ваших задач быстро, "
      "качественно и конфиденциально.\n\n"
      "Нажмите кнопку ниже, чтобы начать оформление заказа."
  )
  await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


# Обработка нажатия «Сделать заказ» -> Переход к Шагу 1 (Страна)
@router.callback_query(F.data == "start_order")
async def process_start_order(callback: CallbackQuery, state: FSMContext):
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
      ]
  )
  await callback.message.edit_text(
      "<b>Шаг 1 из 6: Выбор страны</b>\n\nПожалуйста, выберите страну из списка:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


# ==========================================
# ШАГ 1: ВЫБОР СТРАНЫ -> ШАГ 2: ГОРОД
# ==========================================
@router.callback_query(OrderForm.country, F.data.startswith("country_"))
async def process_country(callback: CallbackQuery, state: FSMContext):
  country_code = callback.data.split("_")[1]
  country_names = {
      "Ukraine": "Украина",
      "Russia": "Россия",
      "Belarus": "Беларусь",
      "Kazakhstan": "Казахстан",
  }
  selected_country = country_names.get(country_code, country_code)

  await state.update_data(country=selected_country)
  await state.set_state(OrderForm.city)

  await callback.message.edit_text(
      f"<b>Шаг 2 из 6: Город</b>\n\n"
      f"Выбранная страна: <b>{selected_country}</b>\n\n"
      f"Введите название города текстовым сообщением:",
      parse_mode="HTML",
  )
  await callback.answer()


# ==========================================
# ШАГ 2: ВВОД ГОРОДА -> ШАГ 3: АДРЕС
# ==========================================
@router.message(OrderForm.city, F.text)
async def process_city(message: Message, state: FSMContext):
  city = message.text.strip()
  await state.update_data(city=city)
  await state.set_state(OrderForm.address)

  await message.answer(
      f"<b>Шаг 3 из 6: Адрес цели</b>\n\n"
      f"Город: <b>{city}</b>\n\n"
      f"Введите точный адрес цели (улица, дом, квартира/офис или ориентир):",
      parse_mode="HTML",
  )


# ==========================================
# ШАГ 3: ВВОД АДРЕСА -> ШАГ 4: ФОТО
# ==========================================
@router.message(OrderForm.address, F.text)
async def process_address(message: Message, state: FSMContext):
  address = message.text.strip()
  await state.update_data(address=address, photos=[])
  await state.set_state(OrderForm.photos)

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Готово / Продолжить без фото",
                  callback_data="finish_photos",
              )
          ]
      ]
  )
  await message.answer(
      f"<b>Шаг 4 из 6: Фотографии цели</b>\n\n"
      f"Адрес: <b>{address}</b>\n\n"
      f"📷 Загрузите от 1 до 3 фото цели.\n"
      f"Отправляйте фотографии по одной. Как закончите, нажмите кнопку ниже:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# Обработка загрузки фотографий (от 1 до 3)
@router.message(OrderForm.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
  data = await state.get_data()
  photos = data.get("photos", [])

  if len(photos) >= 3:
    await message.answer(
        "⚠️ Вы уже загрузили максимальное количество фото (3). Нажмите кнопку"
        " «Готово»."
    )
    return

  photo_id = message.photo[-1].file_id
  photos.append(photo_id)
  await state.update_data(photos=photos)

  keyboard_buttons = []
  if len(photos) < 3:
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"✅ Готово ({len(photos)}/3 загружено)",
            callback_data="finish_photos",
        )
    ])
  else:
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="✅ Готово (3/3 загружено) — Далее",
            callback_data="finish_photos",
        )
    ])

  keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

  await message.answer(
      f"📸 Фото #{len(photos)} успешно добавлено!\n"
      f"Можете отправить еще фото (осталось {3 - len(photos)}) или завершить"
      " загрузку кнопкой ниже:",
      reply_markup=keyboard,
  )


# ==========================================
# ШАГ 4 (ЗАВЕРШЕНИЕ ФОТО) -> ШАГ 5: ЗАДАЧА
# ==========================================
@router.callback_query(OrderForm.photos, F.data == "finish_photos")
async def finish_photos(callback: CallbackQuery, state: FSMContext):
  await state.set_state(OrderForm.task)
  await callback.message.edit_text(
      "<b>Шаг 5 из 6: Задача</b>\n\n"
      "Опишите подробно, что именно нужно сделать («Что нужно сделать»):",
      parse_mode="HTML",
  )
  await callback.answer()


# ==========================================
# ШАГ 5: ВВОД ЗАДАЧИ -> ШАГ 6: СРОЧНОСТЬ
# ==========================================
@router.message(OrderForm.task, F.text)
async def process_task(message: Message, state: FSMContext):
  task = message.text.strip()
  await state.update_data(task=task)
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
                  text="📅 В течение 2-3 дней",
                  callback_data="urgency_2-3_дня",
              )
          ],
      ]
  )

  await message.answer(
      f"<b>Шаг 6 из 6: Срочность</b>\n\n"
      f"Задача принята.\n"
      f"Выберите срочность выполнения заказа:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# ==========================================
# ШАГ 6: СРОЧНОСТЬ -> ФИНАЛ И БЛОК ОПЛАТЫ
# ==========================================
@router.callback_query(OrderForm.urgency, F.data.startswith("urgency_"))
async def process_urgency(callback: CallbackQuery, state: FSMContext):
  urgency_raw = callback.data.split("_", 1)[1]
  urgency_map = {
      "Сейчас": "⚡ Сейчас",
      "Сегодня": "🕐 Сегодня",
      "2-3_дня": "📅 В течение 2-3 дней",
  }
  urgency = urgency_map.get(urgency_raw, urgency_raw)
  await state.update_data(urgency=urgency)

  data = await state.get_data()
  country = data.get("country")
  city = data.get("city")
  address = data.get("address")
  photos = data.get("photos", [])
  task = data.get("task")

  summary_text = (
      "🎉 <b>Ваша анкета успешно сформирована!</b>\n\n"
      "📋 <b>Сводка заказа:</b>\n"
      f"• Страна: <b>{country}</b>\n"
      f"• Город: <b>{city}</b>\n"
      f"• Адрес: <b>{address}</b>\n"
      f"• Фотографий прикреплено: <b>{len(photos)}</b>\n"
      f"• Задача: <b>{task}</b>\n"
      f"• Срочность: <b>{urgency}</b>\n\n"
      "━━━━━━━━━━━━━━━━━━━\n"
      "💳 <b>БЛОК ОПЛАТЫ</b>\n"
      "• <b>Сумма к оплате:</b> 200$\n"
      "• <b>Валюта / Сеть:</b> USDT (TRC20)\n"
      "• <b>Реквизиты для оплаты:</b>\n"
      "<code>TCRbjQUidQfszDWEMnyWQVUscRj7CoqRTn</code>\n\n"
      "ℹ️ <i>Пожалуйста, переведите точную сумму на указанный кошелек. Оплата"
      " проверяется вручную администратором. После оплаты ожидайте"
      " подтверждения.</i>"
  )

  await callback.message.edit_text(summary_text, parse_mode="HTML")
  await state.clear()  # Очищаем состояние для новых заказов
  await callback.answer()


# Главная функция запуска бота
async def main():
  bot = Bot(token=BOT_TOKEN)
  dp = Dispatcher()
  dp.include_router(router)

  logger.info("Бот запущен и ожидает сообщения...")
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
