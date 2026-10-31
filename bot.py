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
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
  raise ValueError("❌ BOT_TOKEN не найден!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderForm(StatesGroup):
  country = State()
  city = State()
  address = State()
  photos = State()
  task = State()
  urgency = State()


router = Router()


# === 0. СТАРТ ===
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
  text = (
      "<b>Добро пожаловать в сервис «СПОРТ УСЛУГИ»!</b> 🏅\n\n"
      "Мы предоставляем профессиональные услуги и решение ваших задач быстро, "
      "качественно и конфиденциально.\n\n"
      "Нажмите кнопку ниже, чтобы начать оформление заказа."
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


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
              )
          ],
      ]
  )
  await callback.message.edit_text(
      "<b>Шаг 1 из 6: Выбор страны</b>\n\nВыберите страну из списка:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )
  await callback.answer()


# === 1. СТРАНА -> 2. ГОРОД ===
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
  }
  selected = names.get(c_code, c_code)

  await state.update_data(country=selected)
  await state.set_state(OrderForm.city)
  await callback.message.edit_text(
      f"<b>Шаг 2 из 6: Город</b>\n\nВыбрано: <b>{selected}</b>\n\nВведите"
      " название города текстом:",
      parse_mode="HTML",
  )
  await callback.answer()


# === 2. ГОРОД -> 3. АДРЕС ===
@router.message(OrderForm.city, F.text)
async def process_city(message: Message, state: FSMContext):
  await state.update_data(city=message.text.strip())
  await state.set_state(OrderForm.address)
  await message.answer(
      f"<b>Шаг 3 из 6: Адрес цели</b>\n\nГород:"
      f" <b>{message.text.strip()}</b>\n\nВведите точный адрес цели:",
      parse_mode="HTML",
  )


# === 3. АДРЕС -> 4. ФОТО ===
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
      "<b>Шаг 4 из 6: Фотографии цели</b>\n\n📷 Отправьте от 1 до 3 фото. Как"
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
      "<b>Шаг 5 из 6: Задача</b>\n\nПодробно опишите, что нужно сделать:",
      parse_mode="HTML",
  )
  await callback.answer()


# === 5. ЗАДАЧА -> 6. СРОЧНОСТЬ ===
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
      "<b>Шаг 6 из 6: Срочность</b>\n\nВыберите срочность:",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# === 6. СРОЧНОСТЬ -> СВОДКА И КНОПКА "ОПЛАТИТЬ" ===
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
  summary_text = (
      "🎉 <b>Ваша анкета успешно сформирована!</b>\n\n"
      "📋 <b>Сводка заказа:</b>\n"
      f"• Страна: <b>{data.get('country')}</b>\n"
      f"• Город: <b>{data.get('city')}</b>\n"
      f"• Адрес: <b>{data.get('address')}</b>\n"
      f"• Фотографий: <b>{len(data.get('photos', []))}</b>\n"
      f"• Задача: <b>{data.get('task')}</b>\n"
      f"• Срочность: <b>{urgency}</b>\n\n"
      "💵 <b>Сумма к оплате:</b> <b>250$</b>\n\n"
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
  text = (
      "💳 <b>ВЫБОР СПОСОБА ОПЛАТЫ</b>\n\n"
      "• <b>Сумма к оплате:</b> 250$\n\n"
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
  payment_text = (
      "💳 <b>ОПЛАТА USDT (BEP-20)</b>\n\n"
      "• <b>Сумма:</b> 250$\n"
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
  payment_text = (
      "💳 <b>ОПЛАТА USDT (TON)</b>\n\n"
      "• <b>Сумма:</b> 250$\n"
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


# === КНОПКА "ОПЛАЧЕНО" -> ФИНАЛЬНОЕ СООБЩЕНИЕ ===
@router.callback_query(F.data == "confirm_payment")
async def process_confirm_payment(callback: CallbackQuery, state: FSMContext):
  final_text = (
      "✅ <b>Заявка принята в обработку!</b>\n\n"
      "Администратор проверяет поступление средств. С вами свяжутся в"
      " течение <b>25 минут</b>."
  )

  await callback.message.edit_text(final_text, parse_mode="HTML")
  await state.clear()  # Очищаем состояние после завершения
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
