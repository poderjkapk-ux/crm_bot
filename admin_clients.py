# admin_clients.py

import html
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload

from models import Order, OrderStatusHistory, Employee
from templates import ADMIN_HTML_TEMPLATE, ADMIN_CLIENTS_LIST_BODY, ADMIN_CLIENT_DETAIL_BODY
from dependencies import get_db_session, check_credentials

router = APIRouter()

@router.get("/admin/clients", response_class=HTMLResponse)
async def admin_clients_list(
    page: int = Query(1, ge=1),
    q: str = Query(None, alias="search"),
    session: AsyncSession = Depends(get_db_session),
    username: str = Depends(check_credentials)
):
    """Displays a paginated and searchable list of clients."""
    per_page = 20
    offset = (page - 1) * per_page

    # Subquery to get the latest customer name for each phone number
    latest_name_subquery = (
        select(
            Order.phone_number,
            Order.customer_name,
            func.row_number().over(
                partition_by=Order.phone_number,
                order_by=Order.id.desc()
            ).label("rn")
        )
        .where(Order.phone_number.isnot(None))
        .subquery()
    )

    # Main query to aggregate client data
    client_query = (
        select(
            Order.phone_number,
            func.count(Order.id).label("order_count"),
            func.sum(Order.total_price).label("total_spent"),
            latest_name_subquery.c.customer_name.label("customer_name")
        )
        .join(latest_name_subquery, Order.phone_number == latest_name_subquery.c.phone_number)
        .where(latest_name_subquery.c.rn == 1)
        .group_by(Order.phone_number, latest_name_subquery.c.customer_name)
        .order_by(func.count(Order.id).desc())
    )

    if q:
        client_query = client_query.where(
            or_(
                latest_name_subquery.c.customer_name.ilike(f"%{q}%"),
                Order.phone_number.ilike(f"%{q}%")
            )
        )

    total_res = await session.execute(select(func.count()).select_from(client_query.subquery()))
    total = total_res.scalar_one()
    pages = (total // per_page) + (1 if total % per_page > 0 else 0)

    clients_res = await session.execute(client_query.limit(per_page).offset(offset))
    clients = clients_res.mappings().all()

    rows = "".join([f"""
    <tr>
        <td><a href="/admin/client/{c['phone_number']}">{html.escape(c['customer_name'])}</a></td>
        <td>{html.escape(c['phone_number'])}</td>
        <td>{c['order_count']}</td>
        <td>{c['total_spent']} грн</td>
        <td class="actions">
            <a href="/admin/client/{c['phone_number']}" class="button-sm">Смотреть</a>
        </td>
    </tr>""" for c in clients])

    pagination = f"<div class='pagination'>{''.join([f'<a href=\"/admin/clients?page={i}{f'&search={q}' if q else ''}\" class=\"{'active' if i == page else ''}\">{i}</a>' for i in range(1, pages + 1)])}</div>"

    body = ADMIN_CLIENTS_LIST_BODY.format(
        search_query=q or '',
        rows=rows or "<tr><td colspan='5'>Клиентов не найдено</td></tr>",
        pagination=pagination if pages > 1 else ""
    )

    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title="Клиенты", body=body, clients_active="active", **{k: "" for k in ["main_active", "products_active", "categories_active", "orders_active", "statuses_active", "employees_active", "settings_active", "reports_active", "menu_active"]}))


@router.get("/admin/client/{phone_number}", response_class=HTMLResponse)
async def admin_client_detail(
    phone_number: str,
    session: AsyncSession = Depends(get_db_session),
    username: str = Depends(check_credentials)
):
    """Displays a detailed view of a single client and their order history."""
    orders_res = await session.execute(
        select(Order)
        .where(Order.phone_number == phone_number)
        .options(
            joinedload(Order.status),
            joinedload(Order.completed_by_courier),
            joinedload(Order.history).joinedload(OrderStatusHistory.status)
        )
        .order_by(Order.id.desc())
    )
    
    # ИЗМЕНЕНО: Добавлен .unique() для устранения ошибки дублирования
    orders = orders_res.unique().scalars().all()

    if not orders:
        raise HTTPException(status_code=404, detail="Клиент с таким номером не найден")

    # Client details from the most recent order
    latest_order = orders[0]
    client_name = latest_order.customer_name
    client_address = latest_order.address

    # Summary stats
    total_orders = len(orders)
    total_spent = sum(o.total_price for o in orders)

    order_rows = []
    for o in orders:
        completed_by = o.completed_by_courier.full_name if o.completed_by_courier else "<i>Не завершено курьером</i>"
        
        history_log = "<ul class='status-history'>"
        # Сортируем историю по времени, так как eager loading не гарантирует порядок
        for h in sorted(o.history, key=lambda x: x.timestamp):
            timestamp = h.timestamp.strftime('%d.%m.%Y %H:%M')
            history_log += f"<li><b>{h.status.name}</b> ({html.escape(h.actor_info)}) - {timestamp}</li>"
        history_log += "</ul>"
        
        order_rows.append(f"""
        <tr class="order-summary-row" onclick="toggleDetails(this)">
            <td>#{o.id}</td>
            <td>{o.created_at.strftime('%d.%m.%Y %H:%M')}</td>
            <td><span class='status'>{o.status.name}</span></td>
            <td>{o.total_price} грн</td>
            <td>{completed_by}</td>
            <td><i class="fa-solid fa-chevron-down"></i></td>
        </tr>
        <tr class="order-details-row">
            <td colspan="6">
                <div class="details-content">
                    <h4>Детали Заказа:</h4>
                    <p><b>Состав:</b> {html.escape(o.products)}</p>
                    <p><b>Адрес:</b> {html.escape(o.address or 'Самовывоз')}</p>
                    <h4>История Статусов:</h4>
                    {history_log}
                </div>
            </td>
        </tr>
        """)

    body = ADMIN_CLIENT_DETAIL_BODY.format(
        client_name=html.escape(client_name),
        phone_number=html.escape(phone_number),
        address=html.escape(client_address or "Не указан"),
        total_orders=total_orders,
        total_spent=total_spent,
        order_rows="".join(order_rows)
    )

    return HTMLResponse(ADMIN_HTML_TEMPLATE.format(title=f"Клиент: {html.escape(client_name)}", body=body, clients_active="active", **{k: "" for k in ["main_active", "products_active", "categories_active", "orders_active", "statuses_active", "employees_active", "settings_active", "reports_active", "menu_active"]}))

