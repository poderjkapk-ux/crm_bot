# notification_manager.py
import logging
from aiogram import Bot, html
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from urllib.parse import quote_plus

from models import Order, Settings, OrderStatus, Employee, Role

logger = logging.getLogger(__name__)


async def notify_new_order_to_staff(admin_bot: Bot, order: Order, session: AsyncSession):
    """
    Надсилає сповіщення про НОВЕ замовлення в загальний чат і всім операторам на зміні.
    """
    settings = await session.get(Settings, 1)

    # Генеруємо текст та клавіатуру для керування
    status_name = order.status.name if order.status else 'Невідомий'
    delivery_info = f"Адреса: {html.quote(order.address or 'Не вказана')}" if order.is_delivery else 'Самовивіз'
    time_info = f"Час: {html.quote(order.delivery_time)}"
    source = f"Джерело: {'Веб-сайт' if order.user_id is None else 'Telegram-бот'}"

    # Повний текст для операторів та адмін-чату
    admin_text = (f"<b>Замовлення #{order.id}</b> ({source})\n\n"
                  f"<b>Клієнт:</b> {html.quote(order.customer_name)}\n<b>Телефон:</b> {html.quote(order.phone_number)}\n"
                  f"<b>{delivery_info}</b>\n<b>{time_info}</b>\n\n"
                  f"<b>Страви:</b>\n- {html.quote(order.products or '').replace(', ', '\n- ')}\n\n"
                  f"<b>Сума:</b> {order.total_price} грн\n\n"
                  f"<b>Статус:</b> {status_name}")

    kb_admin = InlineKeyboardBuilder()
    statuses_res = await session.execute(
        select(OrderStatus).where(OrderStatus.visible_to_operator == True).order_by(OrderStatus.id)
    )
    status_buttons = [
        InlineKeyboardButton(text=s.name, callback_data=f"change_order_status_{order.id}_{s.id}")
        for s in statuses_res.scalars().all()
    ]
    for i in range(0, len(status_buttons), 2):
        kb_admin.row(*status_buttons[i:i+2])
    kb_admin.row(InlineKeyboardButton(text="👤 Призначити кур'єра", callback_data=f"select_courier_{order.id}"))
    kb_admin.row(InlineKeyboardButton(text="✏️ Редагувати замовлення", callback_data=f"edit_order_{order.id}"))

    # 1. Відправка в загальний адмін-чат (як лог)
    if settings and settings.admin_chat_id:
        try:
            await admin_bot.send_message(
                settings.admin_chat_id,
                "✅ <b>Отримано нове замовлення!</b>\n\n" + admin_text,
                reply_markup=kb_admin.as_markup()
            )
        except Exception as e:
            logger.error(f"Не вдалося відправити нове замовлення в адмін-чат {settings.admin_chat_id}: {e}")

    # 2. Пошук та відправка всім операторам на зміні
    operator_roles_res = await session.execute(select(Role.id).where(Role.can_manage_orders == True))
    operator_role_ids = operator_roles_res.scalars().all()

    if not operator_role_ids:
        logger.warning("У системі немає ролей для керування замовленнями.")
        return

    operators_on_shift_res = await session.execute(
        select(Employee).where(
            Employee.role_id.in_(operator_role_ids),
            Employee.is_on_shift == True,
            Employee.telegram_user_id.is_not(None)
        )
    )
    operators = operators_on_shift_res.scalars().all()

    if not operators:
        logger.warning(f"Нове замовлення #{order.id}, але немає операторів на зміні.")
        if settings and settings.admin_chat_id:
            try:
                await admin_bot.send_message(settings.admin_chat_id, "❗️<b>УВАГА: Немає операторів на зміні для обробки замовлення!</b>❗️")
            except Exception: pass
        return

    notification_text = "🔔 <b>Нове замовлення для обробки!</b>\n\n" + admin_text
    for operator in operators:
        try:
            await admin_bot.send_message(operator.telegram_user_id, notification_text, reply_markup=kb_admin.as_markup())
        except Exception as e:
            logger.error(f"Не вдалося відправити замовлення оператору {operator.id} ({operator.telegram_user_id}): {e}")


async def notify_all_parties_on_status_change(
    order: Order,
    old_status_name: str,
    actor_info: str, # "Оператор: [Ім'я]" або "Кур'єр: [Ім'я]"
    admin_bot: Bot,
    client_bot: Bot | None,
    session: AsyncSession
):
    """
    Централізована функція для надсилання всіх сповіщень при зміні статусу.
    """
    await session.refresh(order, ['status', 'courier'])
    settings = await session.get(Settings, 1)
    new_status = order.status

    # 1. Сповіщення в головний АДМІН-ЧАТ
    if settings and settings.admin_chat_id:
        log_message = (
            f"🔄 <b>[Статус змінено]</b> Замовлення #{order.id}\n"
            f"<b>Ким:</b> {html.quote(actor_info)}\n"
            f"<b>Статус:</b> `{html.quote(old_status_name)}` → `{html.quote(new_status.name)}`"
        )
        try:
            await admin_bot.send_message(settings.admin_chat_id, log_message)
        except Exception as e:
            logger.error(f"Не вдалося відправити лог про зміну статусу в адмін-чат {settings.admin_chat_id}: {e}")

    # 2. Сповіщення призначеному КУР'ЄРУ (якщо він є і статус для нього видимий)
    if order.courier and order.courier.telegram_user_id and "Оператор" in actor_info:
        courier_text = f"❗️ Статус вашого замовлення #{order.id} було змінено оператором на: <b>{new_status.name}</b>"
        try:
            await admin_bot.send_message(order.courier.telegram_user_id, courier_text)
        except Exception as e:
            logger.error(f"Не вдалося сповістити кур'єра {order.courier.telegram_user_id}: {e}")

    # 3. Сповіщення КЛІЄНТУ (якщо потрібно)
    if new_status.notify_customer and order.user_id and client_bot:
        client_text = f"Статус вашого замовлення #{order.id} змінено на: <b>{new_status.name}</b>"
        try:
            await client_bot.send_message(order.user_id, client_text)
        except Exception as e:
            logger.error(f"Не вдалося сповістити клієнта {order.user_id}: {e}")