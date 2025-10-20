# models.py

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import event, text, func, ForeignKey
from typing import Optional
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./shop.db"
engine = create_async_engine(DATABASE_URL)

def enable_foreign_keys_sync(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

sync_engine = engine.sync_engine
event.listens_for(sync_engine, "connect")(enable_foreign_keys_sync)

async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

# Модель для хранения пунктов меню (страниц)
class MenuItem(Base):
    __tablename__ = 'menu_items'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True, comment="Заголовок, который виден на кнопке")
    content: Mapped[str] = mapped_column(sa.Text, nullable=False, comment="Содержимое страницы (можно использовать HTML)")
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=100)
    show_on_website: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    show_in_telegram: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class Role(Base):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False, unique=True)
    can_manage_orders: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    can_be_assigned: Mapped[bool] = mapped_column(sa.Boolean, default=False, comment="Может быть назначен на заказ (курьер)")
    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="role")

class Employee(Base):
    __tablename__ = 'employees'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[Optional[int]] = mapped_column(sa.BigInteger, nullable=True, unique=True, index=True, comment="Telegram ID для авторизации")
    full_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(sa.String(20), nullable=True, unique=True)
    role_id: Mapped[int] = mapped_column(sa.ForeignKey('roles.id'), nullable=False)
    role: Mapped["Role"] = relationship("Role", back_populates="employees", lazy='selectin')
    is_on_shift: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=text("0"), nullable=False)
    current_order_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey('orders.id', ondelete="SET NULL"), nullable=True)
    current_order: Mapped[Optional["Order"]] = relationship("Order", foreign_keys="Employee.current_order_id")

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100))
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=100, server_default=text("100"))
    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(100))
    description: Mapped[str] = mapped_column(sa.String(500), nullable=True)
    image_url: Mapped[str] = mapped_column(sa.String(255), nullable=True)
    price: Mapped[int] = mapped_column()
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, server_default=text("1"))
    category_id: Mapped[int] = mapped_column(sa.ForeignKey('categories.id'))
    category: Mapped["Category"] = relationship("Category", back_populates="products")
    cart_items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="product")
    r_keeper_id: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True, comment="Identifier from R-Keeper")

class OrderStatus(Base):
    __tablename__ = 'order_statuses'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    notify_customer: Mapped[bool] = mapped_column(sa.Boolean, default=True, server_default=text("1"), nullable=False)
    visible_to_operator: Mapped[bool] = mapped_column(sa.Boolean, default=True, server_default=text("1"), nullable=False)
    visible_to_courier: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=text("0"), nullable=False)
    is_completed_status: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=text("0"), nullable=False)
    is_cancelled_status: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=text("0"), nullable=False)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="status")
    history_entries: Mapped[list["OrderStatusHistory"]] = relationship("OrderStatusHistory", back_populates="status")

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(sa.BigInteger, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    products: Mapped[str] = mapped_column()
    total_price: Mapped[int] = mapped_column()
    customer_name: Mapped[str] = mapped_column(sa.String(100), nullable=True)
    phone_number: Mapped[str] = mapped_column(sa.String(20), nullable=True, index=True)
    address: Mapped[str] = mapped_column(sa.String(255), nullable=True)
    status_id: Mapped[int] = mapped_column(sa.ForeignKey('order_statuses.id'), default=1, nullable=False)
    status: Mapped["OrderStatus"] = relationship("OrderStatus", back_populates="orders", lazy='selectin')
    is_delivery: Mapped[bool] = mapped_column(default=True)
    delivery_time: Mapped[str] = mapped_column(sa.String(50), nullable=True, default="Как можно скорее")
    courier_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey('employees.id', ondelete="SET NULL"), nullable=True)
    courier: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys="Order.courier_id")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=func.now(), server_default=func.now())
    completed_by_courier_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey('employees.id'), nullable=True)

    # НОВЫЕ СВЯЗИ
    completed_by_courier: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys="Order.completed_by_courier_id")
    history: Mapped[list["OrderStatusHistory"]] = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan", lazy='selectin')

# НОВАЯ ТАБЛИЦА ДЛЯ ИСТОРИИ СТАТУСОВ
class OrderStatusHistory(Base):
    __tablename__ = 'order_status_history'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete="CASCADE"), nullable=False, index=True)
    status_id: Mapped[int] = mapped_column(ForeignKey('order_statuses.id'), nullable=False)
    actor_info: Mapped[str] = mapped_column(sa.String(255), nullable=False, comment="Информация о том, кто изменил статус")
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime, default=func.now(), server_default=func.now(), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="history")
    status: Mapped["OrderStatus"] = relationship("OrderStatus", back_populates="history_entries", lazy='selectin')


class Customer(Base):
    __tablename__ = 'customers'
    user_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=True)
    phone_number: Mapped[str] = mapped_column(sa.String(20), nullable=True)
    address: Mapped[str] = mapped_column(sa.String(255), nullable=True)

class CartItem(Base):
    __tablename__ = 'cart_items'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey('products.id'))
    quantity: Mapped[int] = mapped_column(default=1)
    product: Mapped["Product"] = relationship("Product", back_populates="cart_items", lazy='selectin')

class Settings(Base):
    __tablename__ = 'settings'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_bot_token: Mapped[str] = mapped_column(sa.String(100), nullable=True)
    admin_bot_token: Mapped[str] = mapped_column(sa.String(100), nullable=True)
    admin_chat_id: Mapped[str] = mapped_column(sa.String(100), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    r_keeper_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=text("0"))
    r_keeper_api_url: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    r_keeper_user: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    r_keeper_password: Mapped[Optional[str]] = mapped_column(sa.String(100), nullable=True)
    r_keeper_station_code: Mapped[Optional[str]] = mapped_column(sa.String(50), nullable=True)
    r_keeper_payment_type: Mapped[Optional[str]] = mapped_column(sa.String(50), nullable=True)

async def create_db_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        result_status = await session.execute(sa.select(OrderStatus).limit(1))
        if not result_status.scalars().first():
            default_statuses = {
                "Новый": {"visible_to_operator": True, "visible_to_courier": False},
                "В обработке": {"visible_to_operator": True, "visible_to_courier": False},
                "Готов": {"visible_to_operator": True, "visible_to_courier": True},
                "Доставлен": {"visible_to_operator": True, "visible_to_courier": True, "is_completed_status": True},
                "Отменен": {"visible_to_operator": True, "visible_to_courier": False, "is_cancelled_status": True}
            }
            for name, props in default_statuses.items():
                session.add(OrderStatus(name=name, **props))

        result_roles = await session.execute(sa.select(Role).limit(1))
        if not result_roles.scalars().first():
            session.add(Role(name="Администратор", can_manage_orders=True, can_be_assigned=False))
            session.add(Role(name="Оператор", can_manage_orders=True, can_be_assigned=False))
            session.add(Role(name="Курьер", can_manage_orders=False, can_be_assigned=True))

        await session.commit()