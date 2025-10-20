# r_keeper.py
import logging
import httpx
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# FIX: Змінено імпорт з 'main' на 'models' для кращої структури та уникнення циклічних імпортів.
from models import Order, Settings

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RKeeperAPI:
    """
    Класс для взаимодействия с API R-Keeper.
    """
    def __init__(self, settings: Settings):
        self.api_url = settings.r_keeper_api_url
        self.user = settings.r_keeper_user
        self.password = settings.r_keeper_password
        self.station_code = settings.r_keeper_station_code
        self.payment_type = settings.r_keeper_payment_type
        self.enabled = settings.r_keeper_enabled
        self.token = None

    async def _get_auth_token(self, client: httpx.AsyncClient) -> str | None:
        """
        Получает токен аутентификации.
        Примечание: Этот метод является примером. Реальная аутентификация может отличаться.
        """
        if not self.user or not self.password:
            logger.warning("R-Keeper user/password not set. Cannot authenticate.")
            return None
            
        auth_url = f"{self.api_url}/login"
        try:
            response = await client.post(auth_url, json={"user": self.user, "password": self.password})
            response.raise_for_status()
            # ПРЕДПОЛОЖЕНИЕ: API возвращает токен в формате {"access_token": "..."}
            self.token = response.json().get("access_token")
            logger.info("Successfully authenticated with R-Keeper API.")
            return self.token
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to R-Keeper for authentication: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Authentication failed for R-Keeper. Status: {e.response.status_code}, Body: {e.response.text}")
            return None

    async def send_order(self, order: Order, items: List[Dict[str, Any]]):
        """
        Отправляет заказ в R-Keeper.

        :param order: Объект заказа из нашей БД.
        :param items: Список словарей с деталями товаров в заказе. 
                      Каждый словарь должен содержать 'r_keeper_id', 'quantity', 'price'.
        """
        if not self.enabled:
            logger.info("R-Keeper integration is disabled. Skipping order sending.")
            return

        if not all([self.api_url, self.station_code, self.payment_type]):
            logger.error("R-Keeper API URL, station code, or payment type not configured. Cannot send order.")
            return

        async with httpx.AsyncClient() as client:
            # ПРЕДПОЛОЖЕНИЕ: Для каждого запроса нужен свежий токен. 
            # Если токен долгоживущий, можно оптимизировать.
            if not await self._get_auth_token(client):
                return

            headers = {"Authorization": f"Bearer {self.token}"}

            # --- ВАЖНО: Адаптируйте эту структуру под ваше API R-Keeper ---
            # Это примерная структура тела запроса на создание заказа.
            order_data = {
                "stationCode": self.station_code,
                "orderNumber": f"TG-{order.id}", # Уникальный номер заказа
                "comment": f"Клиент: {order.customer_name}, Телефон: {order.phone_number}",
                "customer": {
                    "name": order.customer_name,
                    "phone": order.phone_number,
                    "address": order.address if order.is_delivery else "Самовивіз"
                },
                "items": [
                    {
                        "id": item['r_keeper_id'], # Идентификатор блюда в R-Keeper
                        "quantity": item['quantity'],
                        "price": item['price'] # Цена за единицу
                    }
                    for item in items if item.get('r_keeper_id')
                ],
                "payment": {
                    "type": self.payment_type,
                    "amount": order.total_price
                },
                "deliveryInfo": {
                    "type": "delivery" if order.is_delivery else "pickup",
                    "time": order.delivery_time
                }
            }
            # --- Конец блока для адаптации ---

            # Проверяем, есть ли что отправлять (вдруг ни у одного товара не было r_keeper_id)
            if not order_data["items"]:
                logger.warning(f"Order #{order.id} has no items with R-Keeper IDs. Skipping sending to R-Keeper.")
                return

            try:
                order_url = f"{self.api_url}/orders"
                response = await client.post(order_url, json=order_data, headers=headers)
                response.raise_for_status()
                logger.info(f"Order #{order.id} successfully sent to R-Keeper. Response: {response.json()}")
            except httpx.RequestError as e:
                logger.error(f"Failed to connect to R-Keeper to send order #{order.id}: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to send order #{order.id} to R-Keeper. Status: {e.response.status_code}, Body: {e.response.text}")

# REMOVED: Видалено невикористовувану функцію send_order_to_rkeeper
# Вона дублювала логіку, яка вже є в main.py, і ніколи не викликалася.
