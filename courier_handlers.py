# courier_handlers.py

import logging
from aiogram import Dispatcher, F, html, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, KeyboardButton, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import joinedload
from typing import Dict, Any
from urllib.parse import quote_plus

from models import Employee, Order, OrderStatus, Settings, OrderStatusHistory
from notification_manager import notify_all_parties_on_status_change

logger = logging.getLogger(__name__)

class CourierAuthStates(StatesGroup):
    waiting_for_phone = State()

def get_staff_login_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🔐 Вход оператора"))
    builder.row(KeyboardButton(text="🚚 Вход курьера"))
    return builder.as_markup(resize_keyboard=True)

def get_courier_keyboard(is_on_shift: bool):
    builder = ReplyKeyboardBuilder()
    if is_on_shift:
        builder.row(KeyboardButton(text="📦 Мои заказы"))
        builder.row(KeyboardButton(text="🔴 Завершить смену"))
    else:
        builder.row(KeyboardButton(text="🟢 Начать смену"))
    builder.row(KeyboardButton(text="🚪 Выйти"))
    return builder.as_markup(resize_keyboard=True)

def get_operator_keyboard(is_on_shift: bool):
    builder = ReplyKeyboardBuilder()
    if is_on_shift:
        builder.row(KeyboardButton(text="📦 Активные заказы"))
        builder.row(KeyboardButton(text="🔴 Завершить смену"))
    else:
        builder.row(KeyboardButton(text="🟢 Начать смену"))
    builder.row(KeyboardButton(text="🚪 Выйти"))
    return builder.as_markup(resize_keyboard=True)

async def show_courier_orders(message_or_callback: Message | CallbackQuery, session: AsyncSession, **kwargs: Dict[str, Any]):
    user_id = message_or_callback.from_user.id
    message = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback

    employee = await session.scalar(select(Employee).where(Employee.telegram_user_id == user_id).options(joinedload(Employee.role)))
    
    if not employee or not employee.role.can_be_assigned:
         return await message.answer("❌ У вас нет прав курьера.")

    final_statuses_res = await session.execute(
        select(OrderStatus.id).where(or_(OrderStatus.is_completed_status == True, OrderStatus.is_cancelled_status == True))
    )
    final_status_ids = final_statuses_res.scalars().all()

    orders_res = await session.execute(
        select(Order).options(joinedload(Order.status)).where(
            Order.courier_id == employee.id,
            Order.status_id.not_in(final_status_ids)
        ).order_by(Order.id.desc())
    )
    orders = orders_res.scalars().all()

    text = "🚚 <b>Ваши активные заказы:</b>\n\n"
    if not employee.is_on_shift:
         text += "🔴 Вы не на смене. Нажмите '🟢 Начать смену', чтобы получать новые заказы.\n\n"
    if not orders:
        text += "На данный момент нет активных заказов, назначенных вам."
    
    kb = InlineKeyboardBuilder()
    if orders:
        for order in orders:
            status_name = order.status.name if order.status else "Неизвестный"
            address_info = order.address if order.is_delivery else 'Самовывоз'
            text += (f"<b>Заказ #{order.id}</b> ({status_name})\n"
                     f"📍 Адрес: {html.quote(address_info)}\n"
                     f"💰 Сумма: {order.total_price} грн\n\n")
            kb.row(InlineKeyboardButton(text=f"Действия по заказу #{order.id}", callback_data=f"courier_view_order_{order.id}"))
        kb.adjust(1)
    
    try:
        if isinstance(message_or_callback, CallbackQuery):
            await message.edit_text(text, reply_markup=kb.as_markup())
            await message_or_callback.answer()
        else:
            await message.answer(text, reply_markup=kb.as_markup())
    except TelegramBadRequest as e:
         if "message is not modified" in str(e):
             await message_or_callback.answer("Данные не изменились.")
         else:
             logger.error(f"Error in show_courier_orders: {e}")
             await message.answer(text, reply_markup=kb.as_markup())


async def show_operator_orders(message_or_callback: Message | CallbackQuery, session: AsyncSession):
    is_callback = isinstance(message_or_callback, CallbackQuery)
    message = message_or_callback.message if is_callback else message_or_callback

    final_statuses_res = await session.execute(
        select(OrderStatus.id).where(
            or_(OrderStatus.is_completed_status == True, OrderStatus.is_cancelled_status == True)
        )
    )
    final_status_ids = final_statuses_res.scalars().all()

    orders_res = await session.execute(
        select(Order).options(joinedload(Order.status), joinedload(Order.courier)).where(
            Order.status_id.not_in(final_status_ids)
        ).order_by(Order.id.desc())
    )
    orders = orders_res.scalars().all()
    text = "🖥️ <b>Активные заказы для обработки:</b>\n\n"
    if not orders:
        text += "На данный момент нет активных заказов."
    else:
        for order in orders:
             courier_name = order.courier.full_name if order.courier else "Не назначен"
             status_name = order.status.name if order.status else "Неизвестный"
             text += (f"<b>#{order.id}</b> - {status_name} (Курьер: {courier_name})\n"
                      f"<i>{html.quote(order.customer_name)}, {order.total_price} грн</i>\n\n")

    if is_callback:
        try:
            await message.edit_text(text)
        except TelegramBadRequest:
            await message.answer(text)
        await message_or_callback.answer()
    else:
        await message.answer(text)


async def start_handler(message: Message, state: FSMContext, session: AsyncSession, **kwargs: Dict[str, Any]):
    await state.clear()
    employee = await session.scalar(
        select(Employee).where(Employee.telegram_user_id == message.from_user.id).options(joinedload(Employee.role))
    )
    if employee:
        if employee.role.can_be_assigned:
            await message.answer(f"🎉 Здравствуйте, {employee.full_name}! Вы вошли в режим курьера.",
                                 reply_markup=get_courier_keyboard(employee.is_on_shift))
        elif employee.role.can_manage_orders:
            await message.answer(f"🎉 Здравствуйте, {employee.full_name}! Вы вошли в режим оператора.",
                                 reply_markup=get_operator_keyboard(employee.is_on_shift))
        else:
            await message.answer("Вы авторизованы, но ваша роль не определена. Обратитесь к администратору.")
    else:
        await message.answer("👋 Добро пожаловать! Используйте этот бот для управления или доставки заказов.",
                             reply_markup=get_staff_login_keyboard())


def register_courier_handlers(dp_admin: Dispatcher):
    dp_admin.message.register(start_handler, CommandStart())

    @dp_admin.message(F.text == "🚚 Вход курьера")
    async def courier_login_start(message: Message, state: FSMContext, session: AsyncSession, **kwargs: Dict[str, Any]):
        employee = await session.scalar(select(Employee).where(Employee.telegram_user_id == message.from_user.id).options(joinedload(Employee.role)))
        if employee:
            if employee.role.can_be_assigned:
                return await message.answer(f"✅ Вы уже авторизованы как курьер.", reply_markup=get_courier_keyboard(employee.is_on_shift))
            elif employee.role.can_manage_orders:
                 return await message.answer("❌ Вы авторизованы как оператор. Для входа как курьер, сначала выйдите из системы.", reply_markup=get_operator_keyboard(employee.is_on_shift))
        
        await state.set_state(CourierAuthStates.waiting_for_phone)
        kb = InlineKeyboardBuilder().add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_auth")).as_markup()
        await message.answer("Пожалуйста, введите номер телефона, закрепленный за вами в системе для роли **курьера**:", reply_markup=kb)

    @dp_admin.message(CourierAuthStates.waiting_for_phone)
    async def process_courier_phone(message: Message, state: FSMContext, session: AsyncSession):
        phone = message.text.strip()
        employee = await session.scalar(select(Employee).options(joinedload(Employee.role)).where(Employee.phone_number == phone))
        
        if employee and employee.role.can_be_assigned:
            employee.telegram_user_id = message.from_user.id
            await session.commit()
            await state.clear()
            await message.answer(f"🎉 Здравствуйте, {employee.full_name}! Вы успешно авторизованы как {employee.role.name}.", reply_markup=get_courier_keyboard(employee.is_on_shift))
        else:
            await message.answer("❌ Сотрудник с таким номером не найден или не имеет прав Курьера. Попробуйте еще раз или обратитесь к администратору.")

    @dp_admin.callback_query(F.data == "cancel_auth")
    async def cancel_auth(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        try:
             await callback.message.edit_text("Авторизация отменена.")
        except Exception:
             await callback.message.delete()
             await callback.message.answer("Авторизация отменена.", reply_markup=get_staff_login_keyboard())
    
    @dp_admin.message(F.text.in_({"🟢 Начать смену", "🔴 Завершить смену"}))
    async def toggle_shift(message: Message, session: AsyncSession):
        employee = await session.scalar(
            select(Employee).where(Employee.telegram_user_id == message.from_user.id).options(joinedload(Employee.role))
        )
        if not employee:
            return

        is_start = message.text.startswith("🟢")
        
        if employee.is_on_shift == is_start:
            await message.answer(f"Ваш статус уже {'на смене' if is_start else 'не на смене'}.")
            return

        employee.is_on_shift = is_start
        if not is_start and employee.role.can_be_assigned:
             employee.current_order_id = None 

        await session.commit()
        action = "начали" if is_start else "завершили"
        
        keyboard = None
        if employee.role.can_be_assigned:
            keyboard = get_courier_keyboard(employee.is_on_shift)
        elif employee.role.can_manage_orders:
            keyboard = get_operator_keyboard(employee.is_on_shift)
        
        await message.answer(f"✅ Вы успешно {action} смену.", reply_markup=keyboard)


    @dp_admin.message(F.text == "🚪 Выйти")
    async def logout_handler(message: Message, session: AsyncSession):
        employee = await session.scalar(select(Employee).where(Employee.telegram_user_id == message.from_user.id))
        if employee:
            employee.telegram_user_id = None
            employee.is_on_shift = False
            employee.current_order_id = None
            await session.commit()
            await message.answer("👋 Вы вышли из системы.", reply_markup=get_staff_login_keyboard())
        else:
            await message.answer("❌ Вы не авторизованы.")

    @dp_admin.message(F.text.in_({"📦 Мои заказы", "📦 Активные заказы"}))
    async def handle_show_orders_by_role(message: Message, session: AsyncSession, **kwargs: Dict[str, Any]):
        employee = await session.scalar(
            select(Employee).where(Employee.telegram_user_id == message.from_user.id).options(joinedload(Employee.role))
        )
        if not employee:
            return await message.answer("❌ Вы не авторизованы.")

        if employee.role.can_be_assigned:
            await show_courier_orders(message, session)
        elif employee.role.can_manage_orders:
            await show_operator_orders(message, session)
        else:
            await message.answer("❌ Ваша роль не позволяет просматривать заказы.")

    @dp_admin.callback_query(F.data.startswith("courier_view_order_"))
    async def courier_view_order_details(callback: CallbackQuery, session: AsyncSession, **kwargs: Dict[str, Any]):
        parts = callback.data.split("_")
        order_id = int(parts[3])

        order = await session.get(Order, order_id)
        if not order: return await callback.answer("Заказ не найден.")

        status_name = order.status.name if order.status else 'Неизвестный'
        address_info = order.address if order.is_delivery else 'Самовывоз'
        text = f"<b>Детали заказа #{order.id}</b>\n\n"
        text += f"Статус: {status_name}\n"
        text += f"Адрес: {html.quote(address_info)}\n"
        text += f"Клиент: {html.quote(order.customer_name)}\n"
        text += f"Телефон: {html.quote(order.phone_number)}\n"
        text += f"Состав: {html.quote(order.products)}\n"
        text += f"Сумма: {order.total_price} грн\n\n"
        
        kb = InlineKeyboardBuilder()
        statuses_res = await session.execute(
            select(OrderStatus).where(OrderStatus.visible_to_courier == True).order_by(OrderStatus.id)
        )
        courier_statuses = statuses_res.scalars().all()
        
        status_buttons = [
            InlineKeyboardButton(text=status.name, callback_data=f"courier_set_status_{order.id}_{status.id}")
            for status in courier_statuses
        ]
        kb.row(*status_buttons)

        if order.is_delivery and order.address:
            encoded_address = quote_plus(order.address)
            map_query = f"https://www.google.com/maps/search/?api=1&query={encoded_address}"
            kb.row(InlineKeyboardButton(text="🗺️ Показать на карте", url=map_query))

        kb.row(InlineKeyboardButton(text="⬅️ К моим заказам", callback_data="show_courier_orders_list"))
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
        await callback.answer()

    @dp_admin.callback_query(F.data == "show_courier_orders_list")
    async def back_to_list(callback: CallbackQuery, session: AsyncSession, **kwargs: Dict[str, Any]):
        await show_courier_orders(callback, session)

    @dp_admin.callback_query(F.data.startswith("courier_set_status_"))
    async def courier_set_status(callback: CallbackQuery, session: AsyncSession, **kwargs: Dict[str, Any]):
        client_bot = dp_admin.get("client_bot")
        employee = await session.scalar(select(Employee).where(Employee.telegram_user_id == callback.from_user.id))
        actor_info = f"Курьер: {employee.full_name}" if employee else f"Курьер (ID: {callback.from_user.id})"
        
        parts = callback.data.split("_")
        order_id = int(parts[3])
        new_status_id = int(parts[4])
        
        order = await session.get(Order, order_id)
        if not order: return await callback.answer("Заказ не найден.")
        
        new_status = await session.get(OrderStatus, new_status_id)
        if not new_status:
            return await callback.answer(f"Ошибка: Статус с ID {new_status_id} не найден.")

        old_status_name = order.status.name if order.status else 'Неизвестный'
        order.status_id = new_status.id
        alert_text = f"Статус изменен: {new_status.name}"

        if new_status.is_completed_status or new_status.is_cancelled_status:
            if employee and employee.current_order_id == order_id:
                employee.current_order_id = None
            if new_status.is_completed_status:
                order.completed_by_courier_id = order.courier_id

        # ДОБАВЛЕНО: Создание записи в истории
        history_entry = OrderStatusHistory(
            order_id=order.id,
            status_id=new_status.id,
            actor_info=actor_info
        )
        session.add(history_entry)

        await session.commit()
        
        await notify_all_parties_on_status_change(
            order=order,
            old_status_name=old_status_name,
            actor_info=actor_info,
            admin_bot=callback.bot,
            client_bot=client_bot,
            session=session
        )

        await callback.answer(alert_text)
        await show_courier_orders(callback, session)