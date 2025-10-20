# main.py

import asyncio
import logging
import sys
from os import getenv
from contextlib import asynccontextmanager
import secrets
import re
import os
import aiofiles
from typing import Dict, Any, Generator, Optional, List
from datetime import date, datetime, timedelta
import html
import json
from dotenv import load_dotenv

# --- FastAPI & Uvicorn ---
from fastapi import FastAPI, Form, Request, Depends, HTTPException, status, Query, File, UploadFile, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# --- Aiogram ---
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SQLAlchemy ---
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
import sqlalchemy as sa
from sqlalchemy import func, and_

# --- Локальні імпорти ---
from templates import ADMIN_HTML_TEMPLATE, WEB_ORDER_HTML, ADMIN_EMPLOYEE_BODY, ADMIN_ROLES_BODY, ADMIN_REPORTS_BODY, ADMIN_ORDER_FORM_BODY, ADMIN_SETTINGS_BODY, ADMIN_MENU_BODY, ADMIN_ORDER_MANAGE_BODY
from models import *
from admin_handlers import register_admin_handlers, parse_products_string
from courier_handlers import register_courier_handlers
from notification_manager import notify_new_order_to_staff
from admin_clients import router as clients_router
from dependencies import get_db_session, check_credentials
# --- НОВИЙ ІМПОРТ для керування замовленнями ---
from admin_order_management import router as admin_order_router
# -----------------------------------------------

# --- Інтеграція з R-Keeper ---
try:
    from r_keeper import RKeeperAPI
except ImportError:
    class RKeeperAPI:
        def __init__(self, settings): pass
        async def send_order(self, order, items):
            logging.warning("r_keeper.py не знайдено, інтеграція з R-Keeper вимкнена.")
            pass

# --- КОНФІГУРАЦІЯ ---
load_dotenv()
PRODUCTS_PER_PAGE = 5

class CheckoutStates(StatesGroup):
    waiting_for_delivery_type = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    confirm_data = State()
    waiting_for_order_time = State()
    waiting_for_specific_time = State()

# --- TELEGRAM БОТИ ---
dp = Dispatcher()
dp_admin = Dispatcher()

async def get_main_reply_keyboard(session: AsyncSession):
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🍽️ Меню"), KeyboardButton(text="🛒 Кошик"))
    builder.row(KeyboardButton(text="📋 Мої замовлення"), KeyboardButton(text="❓ Допомога"))

    menu_items_res = await session.execute(
        sa.select(MenuItem).where(MenuItem.show_in_telegram == True).order_by(MenuItem.sort_order)
    )
    menu_items = menu_items_res.scalars().all()
    if menu_items:
        dynamic_buttons = [KeyboardButton(text=item.title.strip()) for item in menu_items]
        for i in range(0, len(dynamic_buttons), 2):
            builder.row(*dynamic_buttons[i:i+2])

    return builder.as_markup(resize_keyboard=True)

async def handle_dynamic_menu_item(message: Message, session: AsyncSession):
    menu_item_res = await session.execute(
        sa.select(MenuItem.content).where(func.trim(MenuItem.title) == message.text, MenuItem.show_in_telegram == True)
    )
    content = menu_item_res.scalar_one_or_none()

    if content is not None:
        if not content.strip():
            await message.answer("Ця сторінка наразі порожня.")
            return

        try:
            await message.answer(content, parse_mode=ParseMode.HTML)
        except TelegramBadRequest:
            try:
                await message.answer(content, parse_mode=None)
            except Exception as e:
                logging.error(f"Не вдалося надіслати вміст пункту меню '{message.text}': {e}")
                await message.answer("Вибачте, сталася помилка під час відображення цієї сторінки.")
    else:
        await message.answer("Вибачте, я не зрозумів цю команду.")


@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    welcome_photo_url = 'https://i.postimg.cc/4y2BL0ck/14e9a2ee-449d-4881-ac89-c2b42b51abc0.jpg'
    caption = f"Шановний {html.escape(message.from_user.full_name)}, ласкаво просимо до ресторану Дайберг! 👋\n\nМи раді вас бачити. Оберіть опцію:"
    keyboard = await get_main_reply_keyboard(session)
    await message.answer_photo(photo=welcome_photo_url, caption=caption, reply_markup=keyboard)


@dp.message(F.text == "🍽️ Меню")
async def handle_menu_message(message: Message, session: AsyncSession):
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await show_menu(message, session)

@dp.message(F.text == "🛒 Кошик")
async def handle_cart_message(message: Message, session: AsyncSession):
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await show_cart(message, session)

@dp.message(F.text == "📋 Мої замовлення")
async def handle_my_orders_message(message: Message, session: AsyncSession):
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await show_my_orders(message, session)

@dp.message(F.text == "❓ Допомога")
async def handle_help_message(message: Message):
    text = "Шановний клієнте, ось інструкція:\n- /start: Розпочати роботу з ботом\n- Додайте страви до кошика\n- Оформлюйте замовлення з доставкою\n- Переглядайте свої замовлення\nМи завжди раді допомогти! З повагою, ресторан Дайберг."
    await message.answer(text)

@dp.message(Command("cancel"))
async def cancel_checkout(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Шановний клієнте, оформлення замовлення скасовано. Будь ласка, звертайтеся, якщо потрібна допомога.")

@dp.callback_query(F.data == "start_menu")
async def back_to_start_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logging.warning(f"Не вдалося видалити повідомлення в back_to_start_menu: {e}")

    welcome_photo_url = 'https://i.postimg.cc/4y2BL0ck/14e9a2ee-449d-4881-ac89-c2b42b51abc0.jpg'
    caption = f"Шановний {html.escape(callback.from_user.full_name)}, ласкаво просимо до ресторану Дайберг! 👋\n\nМи раді вас бачити. Оберіть опцію:"
    keyboard = await get_main_reply_keyboard(session)
    await callback.message.answer_photo(photo=welcome_photo_url, caption=caption, reply_markup=keyboard)
    await callback.answer()

async def show_my_orders(message_or_callback: Message | CallbackQuery, session: AsyncSession):
    is_callback = isinstance(message_or_callback, CallbackQuery)
    message = message_or_callback.message if is_callback else message_or_callback
    user_id = message_or_callback.from_user.id

    orders_result = await session.execute(
        sa.select(Order).options(joinedload(Order.status)).where(Order.user_id == user_id).order_by(Order.id.desc())
    )
    orders = orders_result.scalars().all()

    if not orders:
        text = "Шановний клієнте, у вас поки що немає замовлень. Чекаємо на ваше перше!"
        if is_callback:
            await message_or_callback.answer(text, show_alert=True)
        else:
            await message.answer(text)
        return

    text = "📋 <b>Ваші замовлення в ресторані Дайберг:</b>\n\n"
    for order in orders:
        status_name = order.status.name if order.status else 'Невідомий'
        text += f"<b>Замовлення #{order.id} ({status_name})</b>\nСтрави: {html.escape(order.products)}\nСума: {order.total_price} грн\n\n"

    kb = InlineKeyboardBuilder().add(InlineKeyboardButton(text="⬅️ Головне меню", callback_data="start_menu")).as_markup()

    if is_callback:
        try:
            await message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await message.delete()
            await message.answer(text, reply_markup=kb)
        await message_or_callback.answer()
    else:
        await message.answer(text, reply_markup=kb)

async def show_menu(message_or_callback: Message | CallbackQuery, session: AsyncSession):
    is_callback = isinstance(message_or_callback, CallbackQuery)
    message = message_or_callback.message if is_callback else message_or_callback

    keyboard = InlineKeyboardBuilder()
    categories_result = await session.execute(sa.select(Category).order_by(Category.sort_order, Category.name))
    categories = categories_result.scalars().all()

    if not categories:
        text = "Шановний клієнте, меню поки що порожнє. Зачекайте на оновлення!"
        if is_callback: await message_or_callback.answer(text, show_alert=True)
        else: await message.answer(text)
        return

    for category in categories:
        keyboard.add(InlineKeyboardButton(text=category.name, callback_data=f"show_category_{category.id}_1"))
    keyboard.add(InlineKeyboardButton(text="⬅️ Головне меню", callback_data="start_menu"))
    keyboard.adjust(1)

    text = "Шановний клієнте, ось категорії страв у ресторані Дайберг:"

    if is_callback:
        try:
            await message.edit_text(text, reply_markup=keyboard.as_markup())
        except TelegramBadRequest:
            await message.delete()
            await message.answer(text, reply_markup=keyboard.as_markup())
        await message_or_callback.answer()
    else:
        await message.answer(text, reply_markup=keyboard.as_markup())

@dp.callback_query(F.data == "menu")
async def show_menu_callback(callback: CallbackQuery, session: AsyncSession):
    await show_menu(callback, session)

@dp.callback_query(F.data.startswith("show_category_"))
async def show_category_paginated(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Завантаження...")
    parts = callback.data.split("_")
    category_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1

    category = await session.get(Category, category_id)
    if not category:
        await callback.answer("Категорію не знайдено!", show_alert=True)
        return

    offset = (page - 1) * PRODUCTS_PER_PAGE
    query_total = sa.select(sa.func.count(Product.id)).where(Product.category_id == category_id, Product.is_active == True)
    query_products = sa.select(Product).where(Product.category_id == category_id, Product.is_active == True).order_by(Product.name).offset(offset).limit(PRODUCTS_PER_PAGE)

    total_products = await session.scalar(query_total)
    total_pages = (total_products + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE

    products_result = await session.execute(query_products)
    products_on_page = products_result.scalars().all()

    keyboard = InlineKeyboardBuilder()
    for product in products_on_page:
        keyboard.add(InlineKeyboardButton(text=f"{product.name} - {product.price} грн", callback_data=f"show_product_{product.id}"))

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"show_category_{category_id}_{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"show_category_{category_id}_{page+1}"))
    if nav_buttons:
        keyboard.row(*nav_buttons)

    keyboard.row(InlineKeyboardButton(text="Меню категорій", callback_data="menu"))
    keyboard.adjust(1)

    text = f"<b>{html.escape(category.name)}</b> (Сторінка {page}):"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
    except TelegramBadRequest as e:
        if "there is no text in the message to edit" in str(e):
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=keyboard.as_markup())
        else:
            logging.error(f"Неочікувана помилка TelegramBadRequest у show_category_paginated: {e}")

async def get_photo_input(image_url: str):
    if image_url and os.path.exists(image_url) and os.path.getsize(image_url) > 0:
        return FSInputFile(image_url)
    return None

@dp.callback_query(F.data.startswith("show_product_"))
async def show_product(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Завантаження...")
    product_id = int(callback.data.split("_")[2])
    product = await session.get(Product, product_id)

    if not product or not product.is_active:
        await callback.answer("Страву не знайдено або вона тимчасово недоступна!", show_alert=True)
        return

    text = (f"<b>{html.escape(product.name)}</b>\n\n"
            f"<i>{html.escape(product.description or 'Опис відсутній.')}</i>\n\n"
            f"<b>Ціна: {product.price} грн</b>")

    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="➕ Додати в кошик", callback_data=f"add_to_cart_{product.id}"))
    kb.add(InlineKeyboardButton(text="⬅️ Назад до страв", callback_data=f"show_category_{product.category_id}_1"))
    kb.adjust(1)

    photo_input = await get_photo_input(product.image_url)
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logging.warning(f"Не вдалося видалити повідомлення в show_product: {e}")

    if photo_input:
        await callback.message.answer_photo(photo=photo_input, caption=text, reply_markup=kb.as_markup())
    else:
        await callback.message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery, session: AsyncSession):
    try:
        product_id = int(callback.data.split("_")[3])
    except (IndexError, ValueError):
        await callback.answer("Помилка! Не вдалося обробити запит.", show_alert=True)
        logging.error(f"Не вдалося розпарсити product_id з даних колбеку: {callback.data}")
        return

    user_id = callback.from_user.id

    product = await session.get(Product, product_id)
    if not product or not product.is_active:
        await callback.answer("Ця страва тимчасово недоступна.", show_alert=True)
        return

    result = await session.execute(sa.select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id))
    cart_item = result.scalars().first()

    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = CartItem(user_id=user_id, product_id=product_id, quantity=1)
        session.add(cart_item)

    await session.commit()
    await callback.answer(f"✅ {html.escape(product.name)} додано до кошика!", show_alert=False)

async def show_cart(message_or_callback: Message | CallbackQuery, session: AsyncSession):
    is_callback = isinstance(message_or_callback, CallbackQuery)
    message = message_or_callback.message if is_callback else message_or_callback
    user_id = message_or_callback.from_user.id

    cart_items_result = await session.execute(sa.select(CartItem).options(joinedload(CartItem.product)).where(CartItem.user_id == user_id).order_by(CartItem.id))
    cart_items = cart_items_result.scalars().all()

    if not cart_items:
        text = "Шановний клієнте, ваш кошик порожній. Оберіть щось смачненьке з меню!"
        if is_callback:
            await message_or_callback.answer(text, show_alert=True)
            await show_menu(message_or_callback, session)
        else:
            await message.answer(text)
        return

    text = "🛒 <b>Ваш кошик:</b>\n\n"
    total_price = 0
    kb = InlineKeyboardBuilder()

    for item in cart_items:
        if item.product:
            item_total = item.product.price * item.quantity
            total_price += item_total
            text += f"<b>{html.escape(item.product.name)}</b>\n"
            text += f"<i>{item.quantity} шт. x {item.product.price} грн</i> = <code>{item_total} грн</code>\n\n"
            kb.row(
                InlineKeyboardButton(text="➖", callback_data=f"change_qnt_{item.product.id}_-1"),
                InlineKeyboardButton(text=f"{item.quantity}", callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"change_qnt_{item.product.id}_1"),
                InlineKeyboardButton(text="❌", callback_data=f"delete_item_{item.product.id}")
            )

    text += f"\n<b>Разом до сплати: {total_price} грн</b>"

    kb.row(InlineKeyboardButton(text="✅ Оформити замовлення", callback_data="checkout"))
    kb.row(InlineKeyboardButton(text="🗑️ Очистити кошик", callback_data="clear_cart"))
    kb.row(InlineKeyboardButton(text="⬅️ Продовжити покупки", callback_data="menu"))

    if is_callback:
        try:
            await message.edit_text(text, reply_markup=kb.as_markup())
        except TelegramBadRequest:
            await message.delete()
            await message.answer(text, reply_markup=kb.as_markup())
        await message_or_callback.answer()
    else:
        await message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "cart")
async def show_cart_callback(callback: CallbackQuery, session: AsyncSession):
    await show_cart(callback, session)

@dp.callback_query(F.data.startswith("change_qnt_"))
async def change_quantity(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Оновлюю...")
    product_id, change = map(int, callback.data.split("_")[2:])
    cart_item = await session.scalar(sa.select(CartItem).where(CartItem.user_id == callback.from_user.id, CartItem.product_id == product_id))

    if not cart_item: return

    cart_item.quantity += change
    if cart_item.quantity < 1:
        await session.delete(cart_item)
    await session.commit()
    await show_cart(callback, session)

@dp.callback_query(F.data.startswith("delete_item_"))
async def delete_from_cart(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Видаляю...")
    product_id = int(callback.data.split("_")[2])
    await session.execute(sa.delete(CartItem).where(CartItem.user_id == callback.from_user.id, CartItem.product_id == product_id))
    await session.commit()
    await show_cart(callback, session)

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, session: AsyncSession):
    await session.execute(sa.delete(CartItem).where(CartItem.user_id == callback.from_user.id))
    await session.commit()
    await callback.answer("Кошик очищено!", show_alert=True)
    await show_menu(callback, session)

@dp.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    cart_items_result = await session.execute(
        sa.select(CartItem).options(joinedload(CartItem.product)).where(CartItem.user_id == user_id)
    )
    cart_items = cart_items_result.scalars().all()

    if not cart_items:
        await callback.answer("Шановний клієнте, кошик порожній! Оберіть щось з меню.", show_alert=True)
        return

    total_price = sum(item.product.price * item.quantity for item in cart_items if item.product)
    products_str = [f"{item.product.name} x {item.quantity}" for item in cart_items if item.product]

    await state.update_data(
        total_price=total_price,
        products=", ".join(products_str),
        user_id=user_id,
        username=callback.from_user.username
    )
    await state.set_state(CheckoutStates.waiting_for_delivery_type)
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="🚚 Доставка", callback_data="delivery_type_delivery"))
    kb.add(InlineKeyboardButton(text="🏠 Самовивіз", callback_data="delivery_type_pickup"))
    kb.adjust(1)

    try:
        await callback.message.edit_text("Шановний клієнте, оберіть тип отримання замовлення:", reply_markup=kb.as_markup())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer("Шановний клієнте, оберіть тип отримання замовлення:", reply_markup=kb.as_markup())

    await callback.answer()

@dp.callback_query(F.data.startswith("delivery_type_"))
async def process_delivery_type(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    delivery_type = callback.data.split("_")[2]
    is_delivery = delivery_type == "delivery"
    await state.update_data(is_delivery=is_delivery)
    customer = await session.get(Customer, callback.from_user.id)
    if customer and customer.name and customer.phone_number and (not is_delivery or customer.address):
        text = f"Шановний клієнте, ми маємо ваші дані:\nІм'я: {customer.name}\nТелефон: {customer.phone_number}"
        if is_delivery:
            text += f"\nАдреса: {customer.address}"
        text += "\nБажаєте використати ці дані?"
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="✅ Так", callback_data="confirm_data_yes"))
        kb.add(InlineKeyboardButton(text="✏️ Змінити", callback_data="confirm_data_no"))
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
        await state.set_state(CheckoutStates.confirm_data)
    else:
        await state.set_state(CheckoutStates.waiting_for_name)
        await callback.message.edit_text("Шановний клієнте, будь ласка, введіть ваше ім'я (наприклад, Іван):")
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_data_"))
async def process_confirm_data(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    confirm = callback.data.split("_")[2]
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logging.warning(f"Не вдалося видалити повідомлення в process_confirm_data: {e}")

    message = callback.message

    if confirm == "yes":
        customer = await session.get(Customer, callback.from_user.id)
        data_to_update = {"customer_name": customer.name, "phone_number": customer.phone_number}
        if (await state.get_data()).get("is_delivery"):
            data_to_update["address"] = customer.address
        await state.update_data(**data_to_update)

        await ask_for_order_time(message, state, session)
    else:
        await state.set_state(CheckoutStates.waiting_for_name)
        await message.answer("Шановний клієнте, будь ласка, введіть ваше ім'я (наприклад, Іван Іванов):")
    await callback.answer()

@dp.message(CheckoutStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) < 3:
        await message.answer("Шановний клієнте, ім'я повинно бути не менше 3 символів! Спробуйте ще раз.")
        return
    await state.update_data(customer_name=name)
    await state.set_state(CheckoutStates.waiting_for_phone)
    await message.answer("Будь ласка, введіть номер телефону (наприклад, +380XXXXXXXXX):")

@dp.message(CheckoutStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext, session: AsyncSession):
    phone = message.text.strip()
    if not re.match(r'^\+?\d{10,15}$', phone):
        await message.answer("Шановний клієнте, некоректний номер телефону! Він повинен бути у форматі +380XXXXXXXXX. Спробуйте ще раз.")
        return
    await state.update_data(phone_number=phone)
    data = await state.get_data()
    if data.get('is_delivery'):
        await state.set_state(CheckoutStates.waiting_for_address)
        await message.answer("Будь ласка, введіть вулицю та номер будинку для доставки (наприклад, вул. Головна, 1):")
    else:
        await ask_for_order_time(message, state, session)

@dp.message(CheckoutStates.waiting_for_address)
async def process_address(message: Message, state: FSMContext, session: AsyncSession):
    address = message.text.strip()
    if not address or len(address) < 5:
        await message.answer("Шановний клієнте, адреса повинна бути не менше 5 символів! Спробуйте ще раз.")
        return
    await state.update_data(address=address)
    await ask_for_order_time(message, state, session)

async def ask_for_order_time(message_or_callback: Message | CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.set_state(CheckoutStates.waiting_for_order_time)
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="🚀 Якнайшвидше", callback_data="order_time_asap"))
    kb.add(InlineKeyboardButton(text="🕒 На конкретний час", callback_data="order_time_specific"))
    text = "Чудово! Останній крок: коли доставити замовлення?"

    current_message = message_or_callback if isinstance(message_or_callback, Message) else message_or_callback.message
    await current_message.answer(text, reply_markup=kb.as_markup())
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer()

@dp.callback_query(CheckoutStates.waiting_for_order_time, F.data.startswith("order_time_"))
async def process_order_time(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    time_choice = callback.data.split("_")[2]

    if time_choice == "asap":
        await state.update_data(delivery_time="Якнайшвидше")
        try:
            await callback.message.delete()
        except TelegramBadRequest as e:
            logging.warning(f"Не вдалося видалити повідомлення в process_order_time: {e}")
        await finalize_order(callback.message, state, session)
    else: # "specific"
        await state.set_state(CheckoutStates.waiting_for_specific_time)
        await callback.message.edit_text("Будь ласка, введіть бажаний час доставки (наприклад, '18:30' або 'на 14:00'):")
    await callback.answer()

@dp.message(CheckoutStates.waiting_for_specific_time)
async def process_specific_time(message: Message, state: FSMContext, session: AsyncSession):
    specific_time = message.text.strip()
    if not specific_time:
        await message.answer("Час не може бути порожнім. Спробуйте ще раз.")
        return
    await state.update_data(delivery_time=specific_time)
    await finalize_order(message, state, session)

async def finalize_order(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    user_id = data.get('user_id')
    admin_bot = dp_admin.get("bot_instance")

    cart_items_for_rkeeper = []
    if user_id:
        cart_items_res = await session.execute(
            sa.select(CartItem).options(joinedload(CartItem.product)).where(CartItem.user_id == user_id)
        )
        cart_items = cart_items_res.scalars().all()
        for item in cart_items:
            if item.product and item.product.r_keeper_id:
                cart_items_for_rkeeper.append({
                    "r_keeper_id": item.product.r_keeper_id,
                    "quantity": item.quantity,
                    "price": item.product.price
                })

    order = Order(
        user_id=data['user_id'], username=data.get('username'), products=data['products'],
        total_price=data['total_price'], customer_name=data['customer_name'],
        phone_number=data['phone_number'], address=data.get('address'),
        is_delivery=data.get('is_delivery', True), delivery_time=data.get('delivery_time', 'Якнайшвидше')
    )
    session.add(order)

    if user_id:
        customer = await session.get(Customer, user_id)
        if not customer:
            customer = Customer(user_id=user_id)
            session.add(customer)
        customer.name, customer.phone_number = data['customer_name'], data['phone_number']
        if 'address' in data and data['address'] is not None:
            customer.address = data.get('address')
        await session.execute(sa.delete(CartItem).where(CartItem.user_id == user_id))

    await session.commit()
    await session.refresh(order)

    try:
        settings = await get_settings(session)
        if settings.r_keeper_enabled and cart_items_for_rkeeper:
            api = RKeeperAPI(settings)
            await api.send_order(order, cart_items_for_rkeeper)
    except Exception as e:
        logging.error(f"Не вдалося надіслати замовлення #{order.id} в R-Keeper: {e}")

    if admin_bot:
        await notify_new_order_to_staff(admin_bot, order, session)

    await message.answer("Шановний клієнте, ваше замовлення оформлено! Дякуємо за вибір ресторану Дайберг. Смачного!")

    await state.clear()
    await command_start_handler(message, state, session)

async def start_bot(client_dp: Dispatcher, admin_dp: Dispatcher):
    try:
        async with async_session_maker() as session:
            settings = await get_settings(session)
            if not all([settings.client_bot_token, settings.admin_bot_token]):
                logging.warning("Токени ботів не встановлені в базі даних. Боти не будуть запущені.")
                return

            bot = Bot(token=settings.client_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            admin_bot = Bot(token=settings.admin_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

            admin_dp["client_bot"] = bot
            admin_dp["bot_instance"] = admin_bot
            client_dp["admin_bot_instance"] = admin_bot
            client_dp["session_factory"] = async_session_maker
            admin_dp["session_factory"] = async_session_maker

            menu_items_res = await session.execute(sa.select(MenuItem.title).where(MenuItem.show_in_telegram == True))
            menu_titles = [title.strip() for title in menu_items_res.scalars().all() if title]
            if menu_titles:
                client_dp.message.register(handle_dynamic_menu_item, F.text.in_(menu_titles))

        register_admin_handlers(admin_dp)
        register_courier_handlers(admin_dp)

        client_dp.callback_query.middleware(DbSessionMiddleware(session_pool=async_session_maker))
        client_dp.message.middleware(DbSessionMiddleware(session_pool=async_session_maker))
        admin_dp.callback_query.middleware(DbSessionMiddleware(session_pool=async_session_maker))
        admin_dp.message.middleware(DbSessionMiddleware(session_pool=async_session_maker))

        await bot.delete_webhook(drop_pending_updates=True)
        await admin_bot.delete_webhook(drop_pending_updates=True)

        logging.info("Запускаємо ботів...")
        await asyncio.gather(
            client_dp.start_polling(bot),
            admin_dp.start_polling(admin_bot)
        )
    except Exception as e:
        logging.critical(f"Не вдалося запустити ботів: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Запуск...")
    os.makedirs("static/images", exist_ok=True)
    os.makedirs("static/favicons", exist_ok=True)
    await create_db_tables()
    bot_task = asyncio.create_task(start_bot(dp, dp_admin))
    yield
    logging.info("Зупинка...")
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        logging.info("Завдання бота успішно скасовано.")

app = FastAPI(lifespan=lifespan)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(clients_router)
# --- ПІДКЛЮЧЕННЯ НОВОГО РОУТЕРА ---
app.include_router(admin_order_router)
# ------------------------------------

class DbSessionMiddleware:
    def __init__(self, session_pool): self.session_pool = session_pool
    async def __call__(self, handler, event, data: Dict[str, Any]):
        async with self.session_pool() as session:
            data['session'] = session
            return await handler(event, data)

# --- FastAPI ендпоінти ---
@app.get("/", response_class=HTMLResponse)
async def get_web_ordering_page(session: AsyncSession = Depends(get_db_session)):
    settings = await get_settings(session)
    logo_html = f'<img src="/{settings.logo_url}" alt="Логотип" class="header-logo">' if settings.logo_url else ''

    menu_items_res = await session.execute(
        sa.select(MenuItem).where(MenuItem.show_on_website == True).order_by(MenuItem.sort_order)
    )
    menu_items = menu_items_res.scalars().all()
    menu_links_html = "".join(
        [f'<a href="#" class="menu-popup-trigger" data-item-id="{item.id}">{html.escape(item.title)}</a>' for item in menu_items]
    )

    return HTMLResponse(content=WEB_ORDER_HTML.format(logo_html=logo_html, menu_links_html=menu_links_html))


@app.get("/api/page/{item_id}", response_class=JSONResponse)
async def get_menu_page_content(item_id: int, session: AsyncSession = Depends(get_db_session)):
    menu_item = await session.get(MenuItem, item_id)
    if not menu_item or not menu_item.show_on_website:
        raise HTTPException(status_code=404, detail="Сторінку не знайдено")
    return {"title": menu_item.title, "content": menu_item.content}


@app.get("/api/menu")
async def get_menu_data(session: AsyncSession = Depends(get_db_session)):
    categories_res = await session.execute(sa.select(Category).order_by(Category.sort_order, Category.name))
    products_res = await session.execute(sa.select(Product).where(Product.is_active == True))

    categories = [{"id": c.id, "name": c.name} for c in categories_res.scalars().all()]
    products = [{"id": p.id, "name": p.name, "description": p.description, "price": p.price, "image_url": p.image_url, "category_id": p.category_id} for p in products_res.scalars().all()]

    return {"categories": categories, "products": products}

@app.get("/api/customer_info/{phone_number}")
async def get_customer_info(phone_number: str, session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        sa.select(Order).where(Order.phone_number == phone_number).order_by(Order.id.desc()).limit(1)
    )
    last_order = result.scalars().first()
    if last_order:
        return {"customer_name": last_order.customer_name, "phone_number": last_order.phone_number, "address": last_order.address}
    raise HTTPException(status_code=404, detail="Клієнта не знайдено")

@app.post("/api/place_order")
async def place_web_order(order_data: dict = Body(...), session: AsyncSession = Depends(get_db_session)):
    items = order_data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Кошик порожній")

    total_price = sum(item['price'] * item['quantity'] for item in items)
    products_str = ", ".join([f"{item['name']} x {item['quantity']}" for item in items])

    is_delivery = order_data.get('is_delivery', True)
    address = order_data.get('address') if is_delivery else None

    order = Order(
        customer_name=order_data.get('customer_name'), phone_number=order_data.get('phone_number'),
        address=address, products=products_str, total_price=total_price,
        is_delivery=is_delivery, delivery_time=order_data.get('delivery_time', "Якнайшвидше")
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)

    admin_bot = dp_admin.get("bot_instance")
    if admin_bot:
        await notify_new_order_to_staff(admin_bot, order, session)

    try:
        settings = await get_settings(session)
        if settings.r_keeper_enabled:
            product_ids = [item['id'] for item in items]
            products_res = await session.execute(sa.select(Product).where(Product.id.in_(product_ids)))
            products_map = {str(p.id): p for p in products_res.scalars().all()}
            items_for_rkeeper = [
                {"r_keeper_id": products_map.get(str(item['id'])).r_keeper_id, "quantity": item['quantity'], "price": item['price']}
                for item in items if products_map.get(str(item['id'])) and products_map.get(str(item['id'])).r_keeper_id
            ]
            if items_for_rkeeper:
                api = RKeeperAPI(settings)
                await api.send_order(order, items_for_rkeeper)
    except Exception as e:
        logging.error(f"Не вдалося надіслати веб-замовлення #{order.id} в R-Keeper: {e}")

    return JSONResponse(content={"message": "Замовлення успішно розміщено", "order_id": order.id})

# --- ВЕБ АДМІН-ПАНЕЛЬ ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    orders_res = await session.execute(sa.select(Order).order_by(Order.id.desc()).limit(5))
    orders_count = await session.scalar(sa.select(sa.func.count(Order.id)))
    products_count = await session.scalar(sa.select(sa.func.count(Product.id)))

    body = f"""
    <div class="card"><strong>Ласкаво просимо, {username}!</strong></div>
    <div class="card"><h2>📈 Швидка статистика</h2><p><strong>Всього страв:</strong> {products_count}</p><p><strong>Всього замовлень:</strong> {orders_count}</p></div>
    <div class="card"><h2>📦 5 останніх замовлень</h2>
        <table><thead><tr><th>ID</th><th>Клієнт</th><th>Телефон</th><th>Сума</th></tr></thead><tbody>
        {''.join([f"<tr><td><a href='/admin/orders?search=%23{o.id}'>#{o.id}</a></td><td>{html.escape(o.customer_name)}</td><td>{html.escape(o.phone_number)}</td><td>{o.total_price} грн</td></tr>" for o in orders_res.scalars().all()]) or "<tr><td colspan='4'>Немає замовлень</td></tr>"}
        </tbody></table></div>"""
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Головна панель", body=body, main_active="active", **{k: "" for k in ["clients_active", "categories_active", "products_active", "orders_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))

@app.get("/admin/products", response_class=HTMLResponse)
async def admin_products(page: int = Query(1, ge=1), q: str = Query(None, alias="search"), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    per_page = 10; offset = (page - 1) * per_page

    query = sa.select(Product).options(joinedload(Product.category)).order_by(Product.id.desc())
    if q:
        query = query.where(Product.name.ilike(f"%{q}%"))

    total = await session.scalar(sa.select(sa.func.count()).select_from(query.subquery()))
    products_res = await session.execute(query.limit(per_page).offset(offset))
    products = products_res.scalars().all()

    pages = (total // per_page) + (1 if total % per_page else 0)

    product_rows = "".join([f"""
    <tr>
        <td>{p.id}</td>
        <td><img src="/{p.image_url or ''}" class="table-img" alt="" loading="lazy"> {html.escape(p.name)}</td>
        <td>{p.price} грн</td>
        <td>{html.escape(p.category.name if p.category else '–')}</td>
        <td>{'✅' if p.is_active else '❌'}</td>
        <td class='actions'>
            <a href='/admin/product/toggle_active/{p.id}' class='button-sm'>{'🔴' if p.is_active else '🟢'}</a>
            <a href='/admin/edit_product/{p.id}' class='button-sm'>✏️</a>
            <a href='/admin/delete_product/{p.id}' onclick="return confirm('Ви впевнені?');" class='button-sm danger'>🗑️</a>
        </td>
    </tr>""" for p in products])

    categories_res = await session.execute(sa.select(Category))
    category_options = "".join([f'<option value="{c.id}">{html.escape(c.name)}</option>' for c in categories_res.scalars().all()])
    pagination = f"<div class='pagination'>{' '.join([f'<a href=\"/admin/products?page={i}{f'&search={q}' if q else ''}\" class=\"{'active' if i == page else ''}\">{i}</a>' for i in range(1, pages+1)])}</div>"

    body = f"""
    <div class="card"><h2>📝 Додати нову страву</h2><form action="/admin/add_product" method="post" enctype="multipart/form-data">
        <label for="name">Назва страви:</label><input type="text" id="name" name="name" required>
        <label for="description">Опис:</label><textarea id="description" name="description" rows="4"></textarea>
        <label for="image">Зображення:</label><input type="file" id="image" name="image" accept="image/*">
        <label for="price">Ціна (в грн):</label><input type="number" id="price" name="price" min="1" required>
        <label for="r_keeper_id">ID в R-Keeper (необов'язково):</label><input type="text" id="r_keeper_id" name="r_keeper_id">
        <label for="category_id">Категорія:</label><select id="category_id" name="category_id" required>{category_options}</select><button type="submit">Додати страву</button></form></div>
    <div class="card">
        <h2>🛍️ Список страв</h2>
        <form action="/admin/products" method="get" class="search-form">
            <input type="text" name="search" placeholder="Пошук за назвою..." value="{q or ''}">
            <button type="submit">🔍 Знайти</button>
        </form>
        <table><thead><tr><th>ID</th><th>Назва</th><th>Ціна</th><th>Категорія</th><th>Статус</th><th>Дії</th></tr></thead><tbody>
        {product_rows or "<tr><td colspan='6'>Немає страв</td></tr>"}
        </tbody></table>{pagination if pages > 1 else ''}
    </div>"""
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Управління стравами", body=body, products_active="active", **{k: "" for k in ["clients_active", "main_active", "categories_active", "orders_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))

@app.post("/admin/add_product")
async def add_product(name: str=Form(...), price: int=Form(...), description: str=Form(""), category_id: int=Form(...),
                      r_keeper_id: str = Form(None), image: UploadFile=File(None),
                      session: AsyncSession=Depends(get_db_session), username: str=Depends(check_credentials)):
    if price <= 0: raise HTTPException(status_code=400, detail="Ціна повинна бути позитивною")
    image_url = None
    if image and image.filename:
        ext = image.filename.split('.')[-1] if '.' in image.filename else 'jpg'
        path = f"static/images/{secrets.token_hex(8)}.{ext}"
        try:
            async with aiofiles.open(path, 'wb') as f: await f.write(await image.read())
            image_url = path
        except Exception as e:
            logging.error(f"Не вдалося зберегти зображення: {e}")

    session.add(Product(name=name, price=price, description=description, image_url=image_url, category_id=category_id, r_keeper_id=r_keeper_id))
    await session.commit()
    return RedirectResponse(url="/admin/products", status_code=303)

@app.get("/admin/edit_product/{product_id}", response_class=HTMLResponse)
async def get_edit_product_form(product_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    categories_res = await session.execute(sa.select(Category))
    category_options = "".join([f'<option value="{c.id}" {"selected" if c.id == product.category_id else ""}>{html.escape(c.name)}</option>' for c in categories_res.scalars().all()])

    body = f"""
    <div class="card">
      <h2>Редагування страви: {html.escape(product.name)}</h2>
      <form action="/admin/edit_product/{product_id}" method="post" enctype="multipart/form-data">
        <label for="name">Назва страви:</label>
        <input type="text" id="name" name="name" value="{html.escape(product.name)}" required>
        <label for="description">Опис:</label>
        <textarea id="description" name="description" rows="4">{html.escape(product.description or '')}</textarea>
        <label for="image">Нове зображення (залишіть порожнім, щоб не змінювати):</label>
        <input type="file" id="image" name="image" accept="image/*">
        {f'<p>Поточне зображення: <img src="/{product.image_url}" class="table-img"></p>' if product.image_url else ''}
        <label for="price">Ціна (в грн):</label>
        <input type="number" id="price" name="price" min="1" value="{product.price}" required>
        <label for="r_keeper_id">ID в R-Keeper (необов'язково):</label>
        <input type="text" id="r_keeper_id" name="r_keeper_id" value="{html.escape(product.r_keeper_id or '')}">
        <label for="category_id">Категорія:</label>
        <select id="category_id" name="category_id" required>{category_options}</select>
        <button type="submit">Зберегти зміни</button>
      </form>
    </div>
    """
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Редагування страви", body=body, products_active="active", **{k: "" for k in ["clients_active", "main_active", "categories_active", "orders_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))

@app.post("/admin/edit_product/{product_id}")
async def edit_product(product_id: int, name: str=Form(...), price: int=Form(...), description: str=Form(""), category_id: int=Form(...),
                      r_keeper_id: str = Form(None), image: UploadFile=File(None),
                      session: AsyncSession=Depends(get_db_session), username: str=Depends(check_credentials)):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    product.name = name
    product.price = price
    product.description = description
    product.category_id = category_id
    product.r_keeper_id = r_keeper_id

    if image and image.filename:
        if product.image_url and os.path.exists(product.image_url):
            os.remove(product.image_url)

        ext = image.filename.split('.')[-1] if '.' in image.filename else 'jpg'
        path = f"static/images/{secrets.token_hex(8)}.{ext}"
        async with aiofiles.open(path, 'wb') as f: await f.write(await image.read())
        product.image_url = path

    await session.commit()
    return RedirectResponse(url="/admin/products", status_code=303)

@app.get("/admin/product/toggle_active/{product_id}")
async def toggle_product_active(product_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    product = await session.get(Product, product_id)
    if product:
        product.is_active = not product.is_active
        await session.commit()
    return RedirectResponse(url="/admin/products", status_code=303)

@app.get("/admin/delete_product/{product_id}")
async def delete_product(product_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    product = await session.get(Product, product_id)
    if product:
        if product.image_url and os.path.exists(product.image_url):
            os.remove(product.image_url)
        await session.delete(product)
        await session.commit()
    return RedirectResponse(url="/admin/products", status_code=303)

@app.get("/admin/categories", response_class=HTMLResponse)
async def admin_categories(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    categories_res = await session.execute(sa.select(Category).order_by(Category.sort_order, Category.name))
    categories = categories_res.scalars().all()

    rows = "".join([f"""
    <tr>
      <td>{c.id}</td>
      <td><form action="/admin/edit_category/{c.id}" method="post" class="inline-form">
          <input type="text" name="name" value="{html.escape(c.name)}">
          <input type="number" name="sort_order" value="{c.sort_order}" style="width: 80px;">
          <button type="submit">💾</button>
      </form></td>
      <td class='actions'><a href='/admin/delete_category/{c.id}' onclick="return confirm('Ви впевнені?');" class='button-sm danger'>🗑️</a></td>
    </tr>""" for c in categories])

    body = f"""
    <div class="card">
        <h2>Додати нову категорію</h2>
        <form action="/admin/add_category" method="post">
            <label for="name">Назва категорії:</label><input type="text" id="name" name="name" required>
            <label for="sort_order">Порядок сортування (менше = вище):</label><input type="number" id="sort_order" name="sort_order" value="100">
            <button type="submit">Додати</button>
        </form>
    </div>
    <div class="card">
        <h2>Список категорій</h2>
        <table><thead><tr><th>ID</th><th>Назва та сортування</th><th>Дії</th></tr></thead><tbody>
        {rows or "<tr><td colspan='3'>Немає категорій</td></tr>"}
        </tbody></table>
    </div>"""
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Категорії", body=body, categories_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "orders_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))

@app.post("/admin/add_category")
async def add_category(name: str = Form(...), sort_order: int = Form(100), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    session.add(Category(name=name, sort_order=sort_order))
    await session.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@app.post("/admin/edit_category/{cat_id}")
async def edit_category(cat_id: int, name: str = Form(...), sort_order: int = Form(...), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    category = await session.get(Category, cat_id)
    if category:
        category.name = name
        category.sort_order = sort_order
        await session.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@app.get("/admin/delete_category/{cat_id}")
async def delete_category(cat_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    category = await session.get(Category, cat_id)
    if category:
        await session.delete(category)
        await session.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@app.get("/admin/menu", response_class=HTMLResponse)
async def admin_menu_items(edit_id: Optional[int] = None, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    menu_items_res = await session.execute(sa.select(MenuItem).order_by(MenuItem.sort_order, MenuItem.title))
    menu_items = menu_items_res.scalars().all()

    item_to_edit = None
    if edit_id:
        item_to_edit = await session.get(MenuItem, edit_id)

    rows = "".join([f"""
    <tr>
        <td>{item.id}</td>
        <td>{html.escape(item.title)}</td>
        <td>{item.sort_order}</td>
        <td>{'✅' if item.show_on_website else '❌'}</td>
        <td>{'✅' if item.show_in_telegram else '❌'}</td>
        <td class="actions">
            <a href="/admin/menu?edit_id={item.id}" class="button-sm">✏️</a>
            <a href="/admin/menu/delete/{item.id}" onclick="return confirm('Ви впевнені?');" class="button-sm danger">🗑️</a>
        </td>
    </tr>
    """ for item in menu_items])

    body = ADMIN_MENU_BODY.format(
        rows=rows or "<tr><td colspan='6'>Немає пунктів меню</td></tr>",
        form_action=f"/admin/menu/edit/{edit_id}" if item_to_edit else "/admin/menu/add",
        form_title="Редагування пункту" if item_to_edit else "Додати новий пункт",
        item_id=item_to_edit.id if item_to_edit else "",
        item_title=html.escape(item_to_edit.title) if item_to_edit else "",
        item_content=html.escape(item_to_edit.content) if item_to_edit else "",
        item_sort_order=item_to_edit.sort_order if item_to_edit else 100,
        item_show_on_website_checked='checked' if item_to_edit and item_to_edit.show_on_website else "",
        item_show_in_telegram_checked='checked' if item_to_edit and item_to_edit.show_in_telegram else "",
        button_text="Зберегти зміни" if item_to_edit else "Додати пункт"
    )
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Сторінки меню", body=body, menu_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "employees_active", "settings_active", "reports_active"]}))

@app.post("/admin/menu/add")
async def add_menu_item(title: str = Form(...), content: str = Form(...), sort_order: int = Form(100),
                        show_on_website: bool = Form(False), show_in_telegram: bool = Form(False),
                        session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    new_item = MenuItem(title=title.strip(), content=content, sort_order=sort_order,
                        show_on_website=show_on_website, show_in_telegram=show_in_telegram)
    session.add(new_item)
    await session.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

@app.post("/admin/menu/edit/{item_id}")
async def edit_menu_item(item_id: int, title: str = Form(...), content: str = Form(...), sort_order: int = Form(100),
                         show_on_website: bool = Form(False), show_in_telegram: bool = Form(False),
                         session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    item = await session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Пункт меню не знайдено")
    item.title = title.strip()
    item.content = content
    item.sort_order = sort_order
    item.show_on_website = show_on_website
    item.show_in_telegram = show_in_telegram
    await session.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

@app.get("/admin/menu/delete/{item_id}")
async def delete_menu_item(item_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    item = await session.get(MenuItem, item_id)
    if item:
        await session.delete(item)
        await session.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

# --- ОНОВЛЕНИЙ РОУТ ДЛЯ ЗАМОВЛЕНЬ ---
@app.get("/admin/orders", response_class=HTMLResponse)
async def admin_orders(page: int = Query(1, ge=1), q: str = Query(None, alias="search"), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    per_page = 15
    offset = (page - 1) * per_page
    query = sa.select(Order).options(joinedload(Order.status)).order_by(Order.id.desc())
    if q:
        search_term = q.replace('#', '')
        query = query.where(sa.or_(Order.id.like(f"%{search_term}%"), Order.customer_name.ilike(f"%{q}%"), Order.phone_number.ilike(f"%{q}%")))

    total = await session.scalar(sa.select(sa.func.count()).select_from(query.subquery()))
    orders_res = await session.execute(query.limit(per_page).offset(offset))
    orders = orders_res.scalars().all()
    pages = (total // per_page) + (1 if total % per_page else 0)

    rows = "".join([f"""
    <tr>
        <td><a href="/admin/order/manage/{o.id}" title="Керувати замовленням">#{o.id}</a></td>
        <td>{html.escape(o.customer_name)}</td>
        <td>{html.escape(o.phone_number)}</td>
        <td>{o.total_price} грн</td>
        <td><span class='status'>{o.status.name if o.status else '-'}</span></td>
        <td>{html.escape(o.products[:50] + '...' if len(o.products) > 50 else o.products)}</td>
        <td class='actions'>
            <a href='/admin/order/manage/{o.id}' class='button-sm' title="Керувати статусом та кур'єром">⚙️ Керувати</a>
            <a href='/admin/order/edit/{o.id}' class='button-sm' title="Редагувати склад замовлення">✏️ Редагувати</a>
        </td>
    </tr>""" for o in orders])

    pagination = f"<div class='pagination'>{' '.join([f'<a href=\"/admin/orders?page={i}{f'&search={q}' if q else ''}\" class=\"{'active' if i == page else ''}\">{i}</a>' for i in range(1, pages+1)])}</div>"

    body = f"""
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <h2>📋 Список замовлень</h2>
            <a href="/admin/order/new" class="button"><i class="fa-solid fa-plus"></i> Створити замовлення</a>
        </div>
        <form action="/admin/orders" method="get" class="search-form">
            <input type="text" name="search" placeholder="Пошук за ID, іменем, телефоном..." value="{q or ''}">
            <button type="submit">🔍 Знайти</button>
        </form>
        <table><thead><tr><th>ID</th><th>Клієнт</th><th>Телефон</th><th>Сума</th><th>Статус</th><th>Склад</th><th>Дії</th></tr></thead><tbody>
        {rows or "<tr><td colspan='7'>Немає замовлень</td></tr>"}
        </tbody></table>{pagination if pages > 1 else ''}
    </div>"""
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Замовлення", body=body, orders_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))
# ----------------------------------------

@app.get("/admin/statuses", response_class=HTMLResponse)
async def admin_statuses(error: Optional[str] = None, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    statuses_res = await session.execute(sa.select(OrderStatus).order_by(OrderStatus.id))
    statuses = statuses_res.scalars().all()

    error_html = ""
    if error == "in_use":
        error_html = "<div class='card' style='background-color: #f8d7da; color: #721c24;'><strong>Помилка!</strong> Неможливо видалити статус, оскільки він використовується в існуючих замовленнях.</div>"

    def bool_to_icon(val):
        return '✅' if val else '❌'

    rows = "".join([f"""
    <tr>
        <td>{s.id}</td>
        <td><form action="/admin/edit_status/{s.id}" method="post" class="inline-form">
            <input type="text" name="name" value="{html.escape(s.name)}" style="width: 150px;" required>
            <button type="submit">💾</button>
        </form></td>
        <td>
            <form action="/admin/edit_status/{s.id}" method="post" class="inline-form">
                <input type="hidden" name="name" value="{html.escape(s.name)}">
                <input type="hidden" name="field" value="notify_customer">
                <input type="hidden" name="value" value="{'false' if s.notify_customer else 'true'}">
                <button type="submit" class="button-sm" style="background-color: transparent; color: inherit; padding: 0;">{bool_to_icon(s.notify_customer)}</button>
            </form>
        </td>
        <td>
            <form action="/admin/edit_status/{s.id}" method="post" class="inline-form">
                <input type="hidden" name="name" value="{html.escape(s.name)}">
                <input type="hidden" name="field" value="visible_to_operator">
                <input type="hidden" name="value" value="{'false' if s.visible_to_operator else 'true'}">
                <button type="submit" class="button-sm" style="background-color: transparent; color: inherit; padding: 0;">{bool_to_icon(s.visible_to_operator)}</button>
            </form>
        </td>
        <td>
            <form action="/admin/edit_status/{s.id}" method="post" class="inline-form">
                <input type="hidden" name="name" value="{html.escape(s.name)}">
                <input type="hidden" name="field" value="visible_to_courier">
                <input type="hidden" name="value" value="{'false' if s.visible_to_courier else 'true'}">
                <button type="submit" class="button-sm" style="background-color: transparent; color: inherit; padding: 0;">{bool_to_icon(s.visible_to_courier)}</button>
            </form>
        </td>
        <td>
            <form action="/admin/edit_status/{s.id}" method="post" class="inline-form">
                <input type="hidden" name="name" value="{html.escape(s.name)}">
                <input type="hidden" name="field" value="is_completed_status">
                <input type="hidden" name="value" value="{'false' if s.is_completed_status else 'true'}">
                <button type="submit" class="button-sm" style="background-color: transparent; color: inherit; padding: 0;">{bool_to_icon(s.is_completed_status)}</button>
            </form>
        </td>
        <td>
            <form action="/admin/edit_status/{s.id}" method="post" class="inline-form">
                <input type="hidden" name="name" value="{html.escape(s.name)}">
                <input type="hidden" name="field" value="is_cancelled_status">
                <input type="hidden" name="value" value="{'false' if s.is_cancelled_status else 'true'}">
                <button type="submit" class="button-sm" style="background-color: transparent; color: inherit; padding: 0;">{bool_to_icon(s.is_cancelled_status)}</button>
            </form>
        </td>
        <td class="actions">
            <a href="/admin/delete_status/{s.id}" onclick="return confirm('Ви впевнені?');" class="button-sm danger">🗑️</a>
        </td>
    </tr>
    """ for s in statuses])

    body = f"""
    {error_html}
    <div class="card">
        <h2>Додати новий статус</h2>
        <form action="/admin/add_status" method="post">
            <label for="name">Назва статусу:</label>
            <input type="text" name="name" placeholder="Назва статусу" required>
            <div class="checkbox-group"><input type="checkbox" id="notify_customer" name="notify_customer" value="true" checked><label for="notify_customer">Сповіщати клієнта</label></div>
            <div class="checkbox-group"><input type="checkbox" id="visible_to_operator" name="visible_to_operator" value="true" checked><label for="visible_to_operator">Показувати оператору</label></div>
            <div class="checkbox-group"><input type="checkbox" id="visible_to_courier" name="visible_to_courier" value="true"><label for="visible_to_courier">Показувати кур'єру</label></div>
            <div class="checkbox-group"><input type="checkbox" id="is_completed_status" name="is_completed_status" value="true"><label for="is_completed_status">Цей статус ЗАВЕРШУЄ замовлення</label></div>
            <div class="checkbox-group"><input type="checkbox" id="is_cancelled_status" name="is_cancelled_status" value="true"><label for="is_cancelled_status">Цей статус СКАСОВУЄ замовлення</label></div>
            <button type="submit">Додати</button>
        </form>
    </div>
    <div class="card">
        <h2>Список статусів</h2>
        <table>
            <thead><tr><th>ID</th><th>Назва</th><th>Сповіщ.</th><th>Оператору</th><th>Кур'єру</th><th>Завершує</th><th>Скасовує</th><th>Дії</th></tr></thead>
            <tbody>{rows or "<tr><td colspan='8'>Немає статусів</td></tr>"}</tbody>
        </table>
    </div>
    """
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Статуси замовлень", body=body, statuses_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))

@app.post("/admin/add_status")
async def add_status(
    name: str = Form(...),
    notify_customer: Optional[bool] = Form(False),
    visible_to_operator: Optional[bool] = Form(False),
    visible_to_courier: Optional[bool] = Form(False),
    is_completed_status: Optional[bool] = Form(False),
    is_cancelled_status: Optional[bool] = Form(False),
    session: AsyncSession = Depends(get_db_session),
    username: str = Depends(check_credentials)
):
    new_status = OrderStatus(
        name=name,
        notify_customer=bool(notify_customer),
        visible_to_operator=bool(visible_to_operator),
        visible_to_courier=bool(visible_to_courier),
        is_completed_status=bool(is_completed_status),
        is_cancelled_status=bool(is_cancelled_status)
    )
    session.add(new_status)
    await session.commit()
    return RedirectResponse(url="/admin/statuses", status_code=303)

@app.post("/admin/edit_status/{status_id}")
async def edit_status(
    status_id: int,
    name: Optional[str] = Form(None),
    field: Optional[str] = Form(None),
    value: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_db_session),
    username: str = Depends(check_credentials)
):
    status_to_edit = await session.get(OrderStatus, status_id)
    if not status_to_edit:
        raise HTTPException(status_code=404, detail="Статус не знайдено")

    if name and not field:
        status_to_edit.name = name
    elif field in ["notify_customer", "visible_to_operator", "visible_to_courier", "is_completed_status", "is_cancelled_status"]:
        setattr(status_to_edit, field, value.lower() == 'true')

    await session.commit()
    return RedirectResponse(url="/admin/statuses", status_code=303)


@app.get("/admin/delete_status/{status_id}")
async def delete_status(status_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    status_to_delete = await session.get(OrderStatus, status_id)
    if status_to_delete:
        try:
            await session.delete(status_to_delete)
            await session.commit()
        except IntegrityError:
            return RedirectResponse(url="/admin/statuses?error=in_use", status_code=302)
    return RedirectResponse(url="/admin/statuses", status_code=303)

@app.get("/admin/roles", response_class=HTMLResponse)
async def admin_roles(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    roles_res = await session.execute(sa.select(Role).order_by(Role.id))
    roles = roles_res.scalars().all()

    rows = "".join([f"""
    <tr>
        <td>{r.id}</td>
        <td>{html.escape(r.name)}</td>
        <td>{'✅' if r.can_manage_orders else '❌'}</td>
        <td>{'✅' if r.can_be_assigned else '❌'}</td>
        <td class="actions">
            <a href="/admin/edit_role/{r.id}" class="button-sm">✏️</a>
            <a href="/admin/delete_role/{r.id}" onclick="return confirm('Ви впевнені?');" class="button-sm danger">🗑️</a>
        </td>
    </tr>""" for r in roles])

    if not rows:
        rows = "<tr><td colspan='5'>Немає ролей</td></tr>"

    body = ADMIN_ROLES_BODY.format(rows=rows)
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Ролі співробітників", body=body, employees_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "settings_active", "reports_active", "menu_active"]}))

@app.post("/admin/add_role")
async def add_role(name: str = Form(...), can_manage_orders: Optional[bool] = Form(False), can_be_assigned: Optional[bool] = Form(False), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    new_role = Role(name=name, can_manage_orders=bool(can_manage_orders), can_be_assigned=bool(can_be_assigned))
    session.add(new_role)
    await session.commit()
    return RedirectResponse(url="/admin/roles", status_code=303)

@app.get("/admin/edit_role/{role_id}", response_class=HTMLResponse)
async def get_edit_role_form(role_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    role = await session.get(Role, role_id)
    if not role: raise HTTPException(status_code=404, detail="Роль не знайдено")

    body = f"""
    <div class="card">
        <ul class="nav-tabs"><li class="nav-item"><a href="/admin/employees">Співробітники</a></li><li class="nav-item"><a href="/admin/roles" class="active">Ролі</a></li></ul>
        <h2>Редагування ролі: {html.escape(role.name)}</h2>
        <form action="/admin/edit_role/{role_id}" method="post">
            <label for="name">Назва ролі:</label><input type="text" id="name" name="name" value="{html.escape(role.name)}" required>
            <div class="checkbox-group">
                <input type="checkbox" id="can_manage_orders" name="can_manage_orders" {'checked' if role.can_manage_orders else ''}>
                <label for="can_manage_orders">Може керувати замовленнями (Оператор)</label>
            </div>
            <div class="checkbox-group">
                <input type="checkbox" id="can_be_assigned" name="can_be_assigned" {'checked' if role.can_be_assigned else ''}>
                <label for="can_be_assigned">Може бути призначений на замовлення (Кур'єр)</label>
            </div>
            <button type="submit">Зберегти зміни</button>
        </form>
    </div>"""
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Редагування ролі", body=body, employees_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "settings_active", "reports_active", "menu_active"]}))

@app.post("/admin/edit_role/{role_id}")
async def edit_role(role_id: int, name: str = Form(...), can_manage_orders: Optional[bool] = Form(False), can_be_assigned: Optional[bool] = Form(False), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    role = await session.get(Role, role_id)
    if role:
        role.name = name
        role.can_manage_orders = bool(can_manage_orders)
        role.can_be_assigned = bool(can_be_assigned)
        await session.commit()
    return RedirectResponse(url="/admin/roles", status_code=303)

@app.get("/admin/delete_role/{role_id}")
async def delete_role(role_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    role = await session.get(Role, role_id)
    if role:
        try:
            await session.delete(role)
            await session.commit()
        except IntegrityError:
            raise HTTPException(status_code=400, detail="Неможливо видалити роль, оскільки до неї прив'язані співробітники.")
    return RedirectResponse(url="/admin/roles", status_code=303)

@app.get("/admin/employees", response_class=HTMLResponse)
async def admin_employees(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    employees_res = await session.execute(sa.select(Employee).options(joinedload(Employee.role)).order_by(Employee.id.desc()))
    employees = employees_res.scalars().all()
    roles_res = await session.execute(sa.select(Role).order_by(Role.id))
    roles = roles_res.scalars().all()

    role_options = "".join([f'<option value="{r.id}">{html.escape(r.name)}</option>' for r in roles])

    rows = "".join([f"""
    <tr>
        <td>{e.id}</td>
        <td>{html.escape(e.full_name)}</td>
        <td>{html.escape(e.phone_number or '-')}</td>
        <td>{html.escape(e.role.name)}</td>
        <td>{'🟢 На зміні' if e.is_on_shift else '🔴 Вихідний'}</td>
        <td>{e.telegram_user_id or '–'}</td>
        <td class="actions">
            <a href='/admin/edit_employee/{e.id}' class='button-sm'>✏️</a>
            <a href='/admin/delete_employee/{e.id}' onclick="return confirm('Ви впевнені?');" class='button-sm danger'>🗑️</a>
        </td>
    </tr>""" for e in employees])

    if not rows:
        rows = '<tr><td colspan="7">Немає співробітників</td></tr>'

    body = ADMIN_EMPLOYEE_BODY.format(role_options=role_options, rows=rows)
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Співробітники", body=body, employees_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "settings_active", "reports_active", "menu_active"]}))

@app.post("/admin/add_employee")
async def add_employee(full_name: str = Form(...), phone_number: str = Form(None), role_id: int = Form(...), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    new_employee = Employee(full_name=full_name, phone_number=phone_number or None, role_id=role_id)
    session.add(new_employee)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Співробітник з таким номером телефону вже існує.")
    return RedirectResponse(url="/admin/employees", status_code=303)

@app.get("/admin/edit_employee/{employee_id}", response_class=HTMLResponse)
async def get_edit_employee_form(employee_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    employee = await session.get(Employee, employee_id)
    roles_res = await session.execute(sa.select(Role).order_by(Role.id))
    roles = roles_res.scalars().all()
    if not employee: raise HTTPException(status_code=404, detail="Співробітника не знайдено")

    role_options = "".join([f'<option value="{r.id}" {"selected" if r.id == employee.role_id else ""}>{html.escape(r.name)}</option>' for r in roles])

    body = f"""
    <div class="card">
        <ul class="nav-tabs"><li class="nav-item"><a href="/admin/employees" class="active">Співробітники</a></li><li class="nav-item"><a href="/admin/roles">Ролі</a></li></ul>
        <h2>Редагування співробітника: {html.escape(employee.full_name)}</h2>
        <form action="/admin/edit_employee/{employee_id}" method="post">
            <label for="full_name">Повне ім'я:</label><input type="text" id="full_name" name="full_name" value="{html.escape(employee.full_name)}" required>
            <label for="phone_number">Номер телефону:</label><input type="text" id="phone_number" name="phone_number" value="{html.escape(employee.phone_number or '')}">
            <label for="telegram_user_id">Telegram User ID:</label><input type="number" id="telegram_user_id" name="telegram_user_id" value="{employee.telegram_user_id or ''}" disabled>
            <label for="role_id">Роль:</label><select id="role_id" name="role_id" required>{role_options}</select>
            <button type="submit">Зберегти зміни</button>
        </form>
    </div>"""
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Редагування співробітника", body=body, employees_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "settings_active", "reports_active", "menu_active"]}))

@app.post("/admin/edit_employee/{employee_id}")
async def edit_employee(employee_id: int, full_name: str = Form(...), phone_number: str = Form(None), role_id: int = Form(...), session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    employee = await session.get(Employee, employee_id)
    if employee:
        employee.full_name = full_name
        employee.phone_number = phone_number or None
        employee.role_id = role_id
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=400, detail="Співробітник з таким номером телефону вже існує.")
    return RedirectResponse(url="/admin/employees", status_code=303)

@app.get("/admin/delete_employee/{employee_id}")
async def delete_employee(employee_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    employee = await session.get(Employee, employee_id)
    if employee:
        await session.delete(employee)
        await session.commit()
    return RedirectResponse(url="/admin/employees", status_code=303)

@app.get("/admin/reports", response_class=HTMLResponse)
async def admin_reports_menu(username: str = Depends(check_credentials)):
    body = """
    <div class="card">
        <h2>Доступні звіти</h2>
        <ul>
            <li><a href="/admin/reports/couriers">Звіт по замовленнях кур'єрів</a></li>
        </ul>
    </div>
    """
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Звіти", body=body, reports_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "employees_active", "settings_active", "menu_active"]}))

@app.get("/admin/reports/couriers", response_class=HTMLResponse)
async def report_couriers(
    date_from_str: str = Query(None, alias="date_from"),
    date_to_str: str = Query(None, alias="date_to"),
    session: AsyncSession = Depends(get_db_session),
    username: str = Depends(check_credentials)
):
    report_data = []
    date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else date.today()
    date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() if date_from_str else date_to - timedelta(days=7)

    completed_status_res = await session.execute(
        sa.select(OrderStatus.id).where(OrderStatus.is_completed_status == True).limit(1)
    )
    completed_status_id = completed_status_res.scalar_one_or_none()

    if completed_status_id:
        report_query = (
            sa.select(
                Employee.full_name,
                func.count(Order.id).label("completed_orders")
            )
            .join(Employee, Order.completed_by_courier_id == Employee.id)
            .where(
                and_(
                    func.date(Order.created_at) >= date_from,
                    func.date(Order.created_at) <= date_to,
                    Order.status_id == completed_status_id
                )
            )
            .group_by(Employee.full_name)
            .order_by(func.count(Order.id).desc())
        )
        result = await session.execute(report_query)
        report_data = result.all()

    report_rows = "".join([f'<tr><td>{html.escape(row.full_name)}</td><td>{row.completed_orders}</td></tr>' for row in report_data])
    if not report_data and date_from_str:
        report_rows = '<tr><td colspan="2">Немає даних за вибраний період.</td></tr>'
    elif not report_data:
        report_rows = '<tr><td colspan="2">Оберіть період та сформуйте звіт.</td></tr>'


    body = ADMIN_REPORTS_BODY.format(
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        date_from_formatted=date_from.strftime("%d.%m.%Y"),
        date_to_formatted=date_to.strftime("%d.%m.%Y"),
        report_rows=report_rows
    )
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Звіт по кур'єрах", body=body, reports_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "employees_active", "settings_active", "menu_active"]}))



@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    settings = await get_settings(session)

    current_logo_html = f'<p>Поточне лого: <img src="/{settings.logo_url}" class="table-img"></p>' if settings.logo_url else ''

    body = ADMIN_SETTINGS_BODY.format(
        client_bot_token=settings.client_bot_token or '',
        admin_bot_token=settings.admin_bot_token or '',
        admin_chat_id=settings.admin_chat_id or '',
        current_logo_html=current_logo_html,
        r_keeper_enabled_checked='checked' if settings.r_keeper_enabled else '',
        r_keeper_api_url=settings.r_keeper_api_url or '',
        r_keeper_user=settings.r_keeper_user or '',
        r_keeper_password=settings.r_keeper_password or '',
        r_keeper_station_code=settings.r_keeper_station_code or '',
        r_keeper_payment_type=settings.r_keeper_payment_type or '',
        cache_buster=secrets.token_hex(4)
    )
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Налаштування", body=body, settings_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "orders_active", "statuses_active", "employees_active", "reports_active", "menu_active"]}))

@app.post("/admin/settings")
async def save_admin_settings(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials),
                               client_bot_token: str = Form(""), admin_bot_token: str = Form(""), admin_chat_id: str = Form(""),
                               logo_file: UploadFile = File(None), r_keeper_enabled: bool = Form(False),
                               r_keeper_api_url: str = Form(""), r_keeper_user: str = Form(""), r_keeper_password: str = Form(""),
                               r_keeper_station_code: str = Form(""), r_keeper_payment_type: str = Form(""),
                               apple_touch_icon: UploadFile = File(None), favicon_32x32: UploadFile = File(None),
                               favicon_16x16: UploadFile = File(None), favicon_ico: UploadFile = File(None),
                               site_webmanifest: UploadFile = File(None)):
    settings = await get_settings(session)
    settings.client_bot_token=client_bot_token
    settings.admin_bot_token=admin_bot_token
    settings.admin_chat_id=admin_chat_id
    settings.r_keeper_enabled=r_keeper_enabled
    settings.r_keeper_api_url=r_keeper_api_url
    settings.r_keeper_user=r_keeper_user
    settings.r_keeper_password=r_keeper_password
    settings.r_keeper_station_code=r_keeper_station_code
    settings.r_keeper_payment_type=r_keeper_payment_type

    if logo_file and logo_file.filename:
        if settings.logo_url and os.path.exists(settings.logo_url): os.remove(settings.logo_url)
        path = f"static/images/{secrets.token_hex(8)}.{logo_file.filename.split('.')[-1]}"
        async with aiofiles.open(path, 'wb') as f: await f.write(await logo_file.read())
        settings.logo_url = path

    favicon_dir = "static/favicons"
    os.makedirs(favicon_dir, exist_ok=True)

    favicon_files = {
        "apple-touch-icon.png": apple_touch_icon,
        "favicon-32x32.png": favicon_32x32,
        "favicon-16x16.png": favicon_16x16,
        "favicon.ico": favicon_ico,
        "site.webmanifest": site_webmanifest,
    }

    for filename, file in favicon_files.items():
        if file and file.filename:
            path = os.path.join(favicon_dir, filename)
            try:
                async with aiofiles.open(path, 'wb') as f:
                    await f.write(await file.read())
            except Exception as e:
                logging.error(f"Не вдалося зберегти favicon {filename}: {e}")

    await session.commit()
    return RedirectResponse(url="/admin/settings?saved=true", status_code=303)

async def get_settings(session: AsyncSession) -> Settings:
    settings = await session.get(Settings, 1)
    if not settings:
        settings = Settings(id=1, client_bot_token=getenv("CLIENT_BOT_TOKEN", ""), admin_bot_token=getenv("ADMIN_BOT_TOKEN", ""), admin_chat_id=getenv("ADMIN_CHAT_ID", ""))
        session.add(settings)
        await session.commit()
    return settings

@app.get("/api/admin/products", response_class=JSONResponse)
async def api_get_products(session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    res = await session.execute(
        sa.select(Product.id, Product.name, Product.price, Category.name.label("category"))
        .join(Category, Product.category_id == Category.id)
        .where(Product.is_active == True)
        .order_by(Category.sort_order, Product.name)
    )
    products = [dict(row) for row in res.mappings().all()]
    return JSONResponse(content=products)

@app.get("/admin/order/new", response_class=HTMLResponse)
async def get_add_order_form(username: str = Depends(check_credentials)):
    initial_data = {
        "items": {},
        "action": "/api/admin/order/new",
        "submit_text": "Створити замовлення",
        "form_values": None
    }
    script_data_injection = f"""
    <script>
        document.addEventListener('DOMContentLoaded', () => {{
            if (window.initializeForm) {{
                window.initializeForm({json.dumps(initial_data)});
            }}
        }});
    </script>
    """
    body = ADMIN_ORDER_FORM_BODY + script_data_injection
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Нове замовлення", body=body, orders_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))

@app.get("/admin/order/edit/{order_id}", response_class=HTMLResponse)
async def get_edit_order_form(order_id: int, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    order = await session.get(Order, order_id)
    if not order: raise HTTPException(404, "Замовлення не знайдено")

    products_dict = parse_products_string(order.products)
    initial_items = {}
    if products_dict:
        products_res = await session.execute(sa.select(Product).where(Product.name.in_(list(products_dict.keys()))))
        db_products_map = {p.name: p for p in products_res.scalars().all()}
        for name, quantity in products_dict.items():
            if p := db_products_map.get(name):
                initial_items[p.id] = {"name": p.name, "price": p.price, "quantity": quantity}

    initial_data = {
        "items": initial_items,
        "action": f"/api/admin/order/edit/{order_id}",
        "submit_text": "Зберегти зміни",
        "form_values": {
            "phone_number": order.phone_number or "",
            "customer_name": order.customer_name or "",
            "is_delivery": order.is_delivery,
            "address": order.address or ""
        }
    }
    script_injection = f"""
    <script>
        document.addEventListener('DOMContentLoaded', () => {{
            if (window.initializeForm) {{
                window.initializeForm({json.dumps(initial_data)});
            }}
        }});
    </script>
    """
    body = ADMIN_ORDER_FORM_BODY + script_injection
    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title=f"Редагування замовлення #{order.id}", body=body, orders_active="active", **{k: "" for k in ["clients_active", "main_active", "products_active", "categories_active", "statuses_active", "settings_active", "employees_active", "reports_active", "menu_active"]}))


async def _process_and_save_order(order: Order, data: dict, session: AsyncSession):
    """
    Обробляє та зберігає дані замовлення, отримані з веб-інтерфейсу адміністратора.
    Використовує ID товарів для надійного пошуку та перерахунку.
    """
    is_new_order = order.id is None
    actor_info = "Адміністративна панель"

    order.customer_name = data.get("customer_name")
    order.phone_number = data.get("phone_number")
    order.is_delivery = data.get("delivery_type") == "delivery"
    order.address = data.get("address") if order.is_delivery else None

    items_from_js = data.get("items", {})

    if not items_from_js:
        order.products = ""
        order.total_price = 0
    else:
        product_ids = [int(pid) for pid in items_from_js.keys()]
        if not product_ids:
            order.products = ""
            order.total_price = 0
        else:
            products_res = await session.execute(sa.select(Product).where(Product.id.in_(product_ids)))
            db_products_map = {p.id: p for p in products_res.scalars().all()}

            total_price = 0
            product_strings = []

            for pid_str, item_data in items_from_js.items():
                pid = int(pid_str)
                if product := db_products_map.get(pid):
                    quantity = int(item_data.get('quantity', 0))
                    if quantity > 0:
                        total_price += product.price * quantity
                        product_strings.append(f"{product.name} x {quantity}")

            order.products = ", ".join(product_strings)
            order.total_price = total_price

    if is_new_order:
        session.add(order)
        if not order.status_id:
            order.status_id = 1

    await session.commit()
    await session.refresh(order)

    if is_new_order:
        history_entry = OrderStatusHistory(
            order_id=order.id,
            status_id=order.status_id,
            actor_info=actor_info
        )
        session.add(history_entry)
        await session.commit()

        admin_bot = dp_admin.get("bot_instance")
        if admin_bot:
            try:
                await notify_new_order_to_staff(admin_bot, order, session)
                logging.info(f"Сповіщення для нового веб-адмін замовлення #{order.id} надіслано успішно.")
            except Exception as e:
                logging.error(f"Не вдалося надіслати сповіщення для нового веб-адмін замовлення #{order.id}: {e}")

@app.post("/api/admin/order/new", response_class=JSONResponse)
async def api_create_order(request: Request, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    data = await request.json()
    new_order = Order()
    await _process_and_save_order(new_order, data, session)
    return JSONResponse(content={"message": "Замовлення створено успішно", "redirect_url": "/admin/orders"})

@app.post("/api/admin/order/edit/{order_id}", response_class=JSONResponse)
async def api_update_order(order_id: int, request: Request, session: AsyncSession = Depends(get_db_session), username: str = Depends(check_credentials)):
    data = await request.json()
    order = await session.get(Order, order_id)
    if not order: raise HTTPException(404, "Замовлення не знайдено")
    await _process_and_save_order(order, data, session)
    return JSONResponse(content={"message": "Замовлення оновлено успішно", "redirect_url": "/admin/orders"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
