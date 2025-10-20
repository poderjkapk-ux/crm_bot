# templates.py

ADMIN_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Адмін-панель DAYBERG</title>
    
    <link rel="apple-touch-icon" sizes="180x180" href="/static/favicons/apple-touch-icon.png">
    <link rel="icon" type="image/png" sizes="32x32" href="/static/favicons/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/static/favicons/favicon-16x16.png">
    <link rel="manifest" href="/static/favicons/site.webmanifest">
    <link rel="shortcut icon" href="/static/favicons/favicon.ico">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/modal_styles.css">
    <style>
        :root {{
            --primary-color: #2563eb;
            --primary-hover-color: #1d4ed8;
            --text-color-light: #111827;
            --text-color-dark: #f9fafb;
            --bg-light: #f9fafb;
            --bg-dark: #111827;
            --sidebar-bg-light: #ffffff;
            --sidebar-bg-dark: #1f2937;
            --card-bg-light: #ffffff;
            --card-bg-dark: #1f2937;
            --border-light: #e5e7eb;
            --border-dark: #374151;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
            --font-sans: 'Inter', sans-serif;
            --status-green: #10b981;
            --status-yellow: #f59e0b;
            --status-red: #ef4444;
            --status-blue: #3b82f6;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: var(--font-sans);
            background-color: var(--bg-light);
            color: var(--text-color-light);
            display: flex;
            min-height: 100vh;
            transition: background-color 0.3s, color 0.3s;
        }}
        body.dark-mode {{
            --bg-light: var(--bg-dark);
            --text-color-light: var(--text-color-dark);
            --sidebar-bg-light: var(--sidebar-bg-dark);
            --card-bg-light: var(--card-bg-dark);
            --border-light: var(--border-dark);
        }}
        
        /* --- Sidebar Styles --- */
        .sidebar {{
            width: 260px;
            background-color: var(--sidebar-bg-light);
            border-right: 1px solid var(--border-light);
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            position: fixed;
            height: 100%;
            transition: background-color 0.3s, border-color 0.3s, transform 0.3s ease-in-out;
            z-index: 1000;
        }}
        .sidebar-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 2.5rem;
        }}
        .sidebar-header .logo {{ display: flex; align-items: center; gap: 0.75rem; }}
        .sidebar-header .logo h2 {{ font-size: 1.5rem; font-weight: 700; color: var(--primary-color); }}
        .sidebar nav a {{
            display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem;
            color: #6b7280; text-decoration: none; font-weight: 500;
            border-radius: 0.5rem; transition: all 0.2s ease; margin-bottom: 0.5rem;
        }}
        body.dark-mode .sidebar nav a {{ color: #9ca3af; }}
        .sidebar nav a:hover {{ background-color: #f3f4f6; color: var(--primary-color); }}
        body.dark-mode .sidebar nav a:hover {{ background-color: #374151; }}
        .sidebar nav a.active {{ background-color: var(--primary-color); color: white; box-shadow: var(--shadow); }}
        .sidebar nav a i {{ width: 20px; text-align: center; }}
        .sidebar-footer {{ margin-top: auto; }}
        .sidebar-close {{
            display: none; background: none; border: none; font-size: 2rem;
            color: #6b7280; cursor: pointer;
        }}

        /* --- Main Content & Header --- */
        main {{
            flex-grow: 1;
            padding: 2rem;
            transition: margin-left 0.3s ease-in-out;
            margin-left: 260px;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }}
        .header-left {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        header h1 {{ font-size: 2rem; font-weight: 700; }}
        .menu-toggle {{
            display: none; background: none; border: 1px solid var(--border-light);
            width: 40px; height: 40px; border-radius: 0.5rem;
            align-items: center; justify-content: center;
            font-size: 1.25rem; color: #6b7280; cursor: pointer;
        }}
        .theme-toggle {{ cursor: pointer; font-size: 1.25rem; color: #6b7280; }}

        /* --- Overlay for Mobile Menu --- */
        .content-overlay {{
            display: none; position: fixed; top: 0; left: 0;
            width: 100%; height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 999;
        }}
        .content-overlay.active {{ display: block; }}

        /* --- Responsive Styles (Mobile) --- */
        @media (max-width: 992px) {{
            .sidebar {{
                transform: translateX(-100%);
                box-shadow: var(--shadow);
            }}
            .sidebar.open {{
                transform: translateX(0);
            }}
            .sidebar-close {{
                display: block;
            }}
            main {{
                margin-left: 0;
            }}
            .menu-toggle {{
                display: inline-flex;
            }}
            header h1 {{ font-size: 1.5rem; }}
        }}

        /* --- General Component Styles (Cards, Tables, etc.) --- */
        .card {{
            background-color: var(--card-bg-light); border-radius: 0.75rem;
            padding: 1.5rem; box-shadow: var(--shadow);
            border: 1px solid var(--border-light); margin-bottom: 2rem;
        }}
        .card h2 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 1.5rem; }}
        .card h3 {{
             font-size: 1.1rem; font-weight: 600; margin-top: 1.5rem;
             margin-bottom: 1rem; padding-bottom: 0.5rem;
             border-bottom: 1px solid var(--border-light);
        }}
        .button, button[type="submit"] {{
            padding: 0.6rem 1.2rem; background-color: var(--primary-color);
            color: white !important; border: none; border-radius: 0.5rem;
            cursor: pointer; font-size: 0.9rem; font-weight: 600;
            transition: background-color 0.2s ease; text-decoration: none;
            display: inline-flex; align-items: center; gap: 0.5rem;
        }}
        button:hover, .button:hover {{ background-color: var(--primary-hover-color); }}
        .button.secondary {{ background-color: #6b7280; }}
        .button.secondary:hover {{ background-color: #4b5563; }}
        .button-sm {{
            display: inline-block; padding: 0.4rem 0.6rem; 
            border-radius: 0.3rem; text-decoration: none; color: white !important;
            background-color: #6b7280;
        }}
        .button-sm.danger {{ background-color: var(--status-red); }}
        .button-sm:hover {{ opacity: 0.8; }}
        .table-wrapper {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 1rem; text-align: left; border-bottom: 1px solid var(--border-light); vertical-align: middle; }}
        th {{ font-weight: 600; font-size: 0.85rem; text-transform: uppercase; color: #6b7280; }}
        body.dark-mode th {{ color: #9ca3af; }}
        td .table-img {{ width: 40px; height: 40px; border-radius: 0.5rem; object-fit: cover; vertical-align: middle; margin-right: 10px; }}
        .status {{
            padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600;
            background-color: #e5e7eb; color: #374151;
        }}
        .actions {{ text-align: right; }}
        .actions a {{ color: #6b7280; margin-left: 0.75rem; font-size: 1.1rem; text-decoration: none; }}
        .actions a:hover {{ color: var(--primary-color); }}
        label {{ font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.9rem; }}
        input, textarea, select {{
            width: 100%; padding: 0.75rem 1rem; border: 1px solid var(--border-light);
            border-radius: 0.5rem; font-family: var(--font-sans); font-size: 1rem;
            background-color: var(--bg-light); color: var(--text-color-light);
            margin-bottom: 1rem;
        }}
        input:focus, textarea:focus, select:focus {{
            outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px #bfdbfe;
        }}
        .checkbox-group {{ display: flex; align-items: center; gap: 10px; margin-bottom: 1rem;}}
        .checkbox-group input[type="checkbox"] {{ width: auto; margin-bottom: 0; }}
        .checkbox-group label {{ margin-bottom: 0; }}
        .search-form, .inline-form {{ display: flex; gap: 10px; margin-bottom: 1rem; align-items: center; }}
        .inline-form input {{ margin-bottom: 0; }}
        .pagination {{ margin-top: 1rem; display: flex; gap: 5px; }}
        .pagination a {{ padding: 5px 10px; border: 1px solid var(--border-light); text-decoration: none; color: var(--text-color-light); border-radius: 5px; }}
        .pagination a.active {{ background-color: var(--primary-color); color: white; border-color: var(--primary-color);}}
        
        .nav-tabs {{ display: flex; gap: 10px; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border-light); padding-bottom: 5px; }}
        .nav-tabs a {{ padding: 8px 15px; border-radius: 5px 5px 0 0; text-decoration: none; color: #6b7280; transition: color 0.2s; }}
        .nav-tabs a:hover {{ color: var(--primary-color); }}
        .nav-tabs a.active {{ background-color: var(--primary-color); color: white !important; }}
        
        .modal-overlay {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); z-index: 2000;
            display: none; justify-content: center; align-items: center;
        }}
        .modal-overlay.active {{ display: flex; }}
        .modal {{
            background: var(--card-bg-light); border-radius: 0.75rem; padding: 2rem;
            width: 90%; max-width: 700px; max-height: 80vh;
            display: flex; flex-direction: column;
        }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .modal-header h4 {{ font-size: 1.25rem; }}
        .modal-header .close-button {{ background: none; border: none; font-size: 2rem; cursor: pointer; }}
        .modal-body {{ flex-grow: 1; overflow-y: auto; }}
    </style>
</head>
<body class="">
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <div class="logo">
                <i class="fa-solid fa-utensils"></i>
                <h2>Dayberg</h2>
            </div>
            <button class="sidebar-close" id="sidebar-close">&times;</button>
        </div>
        <nav>
            <a href="/admin" class="{main_active}"><i class="fa-solid fa-chart-line"></i> Головна</a>
            <a href="/admin/orders" class="{orders_active}"><i class="fa-solid fa-box-archive"></i> Замовлення</a>
            <a href="/admin/clients" class="{clients_active}"><i class="fa-solid fa-users-line"></i> Клієнти</a>
            <a href="/admin/products" class="{products_active}"><i class="fa-solid fa-burger"></i> Страви</a>
            <a href="/admin/categories" class="{categories_active}"><i class="fa-solid fa-folder-open"></i> Категорії</a>
            <a href="/admin/menu" class="{menu_active}"><i class="fa-solid fa-file-lines"></i> Сторінки меню</a>
            <a href="/admin/employees" class="{employees_active}"><i class="fa-solid fa-users"></i> Співробітники</a>
            <a href="/admin/statuses" class="{statuses_active}"><i class="fa-solid fa-clipboard-list"></i> Статуси</a>
            <a href="/admin/reports" class="{reports_active}"><i class="fa-solid fa-chart-pie"></i> Звіти</a>
            <a href="/admin/settings" class="{settings_active}"><i class="fa-solid fa-gear"></i> Налаштування</a>
        </nav>
        <div class="sidebar-footer">
            <a href="#"><i class="fa-solid fa-right-from-bracket"></i> Вийти</a>
        </div>
    </div>

    <main>
        <header>
            <div class="header-left">
                <button class="menu-toggle" id="menu-toggle">
                    <i class="fa-solid fa-bars"></i>
                </button>
                <h1>{title}</h1>
            </div>
            <i id="theme-toggle" class="fa-solid fa-sun theme-toggle"></i>
        </header>
        {body}
    </main>

    <div class="content-overlay" id="content-overlay"></div>

    <script>
      // --- Theme Toggler ---
      const themeToggle = document.getElementById('theme-toggle');
      const body = document.body;

      if (localStorage.getItem('theme') === 'light') {{
        body.classList.remove('dark-mode');
        themeToggle.classList.add('fa-moon');
        themeToggle.classList.remove('fa-sun');
      }} else {{
        body.classList.add('dark-mode');
        themeToggle.classList.add('fa-sun');
        themeToggle.classList.remove('fa-moon');
      }}

      themeToggle.addEventListener('click', () => {{
        body.classList.toggle('dark-mode');
        themeToggle.classList.toggle('fa-sun');
        themeToggle.classList.toggle('fa-moon');
        if(body.classList.contains('dark-mode')){{
          localStorage.setItem('theme', 'dark');
        }} else {{
          localStorage.setItem('theme', 'light');
        }}
      }});

      // --- Mobile Sidebar Logic ---
      const sidebar = document.getElementById('sidebar');
      const menuToggle = document.getElementById('menu-toggle');
      const sidebarClose = document.getElementById('sidebar-close');
      const contentOverlay = document.getElementById('content-overlay');

      const openSidebar = () => {{
        sidebar.classList.add('open');
        contentOverlay.classList.add('active');
      }};

      const closeSidebar = () => {{
        sidebar.classList.remove('open');
        contentOverlay.classList.remove('active');
      }};

      menuToggle.addEventListener('click', openSidebar);
      sidebarClose.addEventListener('click', closeSidebar);
      contentOverlay.addEventListener('click', closeSidebar);

    </script>
</body>
</html>
"""

ADMIN_ORDER_FORM_BODY = """
<style>
    .form-grid {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 1.5rem;
    }}
    @media (min-width: 768px) {{
        .form-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    .order-items-table .quantity-input {{
        width: 70px;
        text-align: center;
        padding: 0.5rem;
    }}
    .order-items-table .actions button {{
        background: none; border: none; color: var(--status-red);
        cursor: pointer; font-size: 1.2rem;
    }}
    .totals-summary {{
        text-align: right;
        font-size: 1.1rem;
        font-weight: 600;
    }}
    .totals-summary div {{ margin-bottom: 0.5rem; }}
    .totals-summary .total {{ font-size: 1.4rem; color: var(--primary-color); }}
    
    /* Product Search Modal Styles */
    #product-list {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 1rem;
    }}
    .product-list-item {{
        border: 1px solid var(--border-light);
        border-radius: 0.5rem;
        padding: 1rem;
        cursor: pointer;
        transition: border-color 0.2s, box-shadow 0.2s;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }}
    .product-list-item:hover {{
        border-color: var(--primary-color);
        box-shadow: 0 0 0 2px #bfdbfe;
    }}
    .product-list-item h5 {{ font-size: 1rem; font-weight: 600; margin-bottom: 0.25rem;}}
    .product-list-item p {{ font-size: 0.9rem; color: #6b7280; }}
    body.dark-mode .product-list-item p {{ color: #9ca3af; }}
</style>

<div class="card">
    <form id="order-form" method="POST">
        <h3>Інформація про клієнта</h3>
        <div class="form-grid">
            <div class="form-group">
                <label for="phone_number">Номер телефону</label>
                <input type="tel" id="phone_number" placeholder="+380 (XX) XXX-XX-XX" required>
            </div>
            <div class="form-group">
                <label for="customer_name">Ім'я клієнта</label>
                <input type="text" id="customer_name" required>
            </div>
        </div>
        <div class="form-group">
            <label>Тип замовлення</label>
            <select id="delivery_type">
                <option value="delivery">Доставка</option>
                <option value="pickup">Самовивіз</option>
            </select>
        </div>
        <div class="form-group" id="address-group">
            <label for="address">Адреса доставки</label>
            <textarea id="address" rows="2"></textarea>
        </div>

        <h3>Склад замовлення</h3>
        <div class="table-wrapper">
            <table class="order-items-table">
                <thead>
                    <tr>
                        <th>Страва</th>
                        <th>Ціна</th>
                        <th>Кількість</th>
                        <th>Сума</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="order-items-body">
                    </tbody>
            </table>
        </div>
        <div style="margin-top: 1.5rem; display: flex; justify-content: space-between; align-items: start; flex-wrap: wrap; gap: 1rem;">
            <button type="button" class="button" id="add-product-btn">
                <i class="fa-solid fa-plus"></i> Додати страву
            </button>
            <div class="totals-summary">
                <div class="total">До сплати: <span id="grand-total">0.00</span> грн</div>
            </div>
        </div>

        <div style="border-top: 1px solid var(--border-light); margin-top: 2rem; padding-top: 1.5rem; display: flex; justify-content: flex-end; gap: 1rem;">
             <a href="/admin/orders" class="button secondary">Скасувати</a>
             <button type="submit" class="button">Зберегти замовлення</button>
        </div>
    </form>
</div>

<div class="modal-overlay" id="product-modal">
    <div class="modal">
        <div class="modal-header">
            <h4>Вибір страви</h4>
            <button type="button" class="close-button" id="close-modal-btn">&times;</button>
        </div>
        <div class="modal-body">
            <div class="form-group">
                <input type="text" id="product-search-input" placeholder="Пошук страви за назвою...">
            </div>
            <div id="product-list">
                </div>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {{
    // State
    let orderItems = {{}}; // {{ productId: {{ name, price, quantity }} }}
    let allProducts = [];

    // Element References
    const orderForm = document.getElementById('order-form');
    const orderItemsBody = document.getElementById('order-items-body');
    const grandTotalEl = document.getElementById('grand-total');
    const deliveryTypeSelect = document.getElementById('delivery_type');
    const addressGroup = document.getElementById('address-group');
    
    // Modal References
    const productModal = document.getElementById('product-modal');
    const addProductBtn = document.getElementById('add-product-btn');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const productListContainer = document.getElementById('product-list');
    const productSearchInput = document.getElementById('product-search-input');
    
    // ИСПРАВЛЕНО: Глобальная функция для установки начальных данных
    window.setInitialOrderItems = (initialItems) => {{
        orderItems = initialItems || {{}};
    }};

    // --- API Functions ---
    const fetchAllProducts = async () => {{
        try {{
            const response = await fetch('/api/admin/products');
            if (!response.ok) {{
                alert('Не вдалося завантажити список страв.');
                return [];
            }}
            return await response.json();
        }} catch (error) {{
            console.error("Fetch products error:", error);
            alert('Помилка мережі при завантаженні страв.');
            return [];
        }}
    }};
    
    // --- Core Logic ---
    const calculateTotals = () => {{
        let currentTotal = 0;
        for (const id in orderItems) {{
            currentTotal += orderItems[id].price * orderItems[id].quantity;
        }}
        grandTotalEl.textContent = currentTotal.toFixed(2);
    }};

    const renderOrderItems = () => {{
        orderItemsBody.innerHTML = '';
        if (Object.keys(orderItems).length === 0) {{
            orderItemsBody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Додайте страви до замовлення</td></tr>';
        }} else {{
            for (const id in orderItems) {{
                const item = orderItems[id];
                const row = document.createElement('tr');
                row.dataset.id = id;
                row.innerHTML = `
                    <td>${{item.name}}</td>
                    <td>${{item.price.toFixed(2)}} грн</td>
                    <td><input type="number" class="quantity-input" value="${{item.quantity}}" min="1" data-id="${{id}}"></td>
                    <td>${{(item.price * item.quantity).toFixed(2)}} грн</td>
                    <td class="actions"><button type="button" class="remove-item-btn" data-id="${{id}}">&times;</button></td>
                `;
                orderItemsBody.appendChild(row);
            }}
        }}
        calculateTotals();
    }};

    const addProductToOrder = (product) => {{
        if (orderItems[product.id]) {{
            orderItems[product.id].quantity++;
        }} else {{
            orderItems[product.id] = {{
                name: product.name,
                price: product.price,
                quantity: 1,
            }};
        }}
        renderOrderItems();
    }};

    // --- Modal Logic ---
    const renderProductsInModal = (products) => {{
        productListContainer.innerHTML = '';
        products.forEach(p => {{
            const itemEl = document.createElement('div');
            itemEl.className = 'product-list-item';
            itemEl.dataset.id = p.id;
            itemEl.innerHTML = `
                <div>
                    <h5>${{p.name}}</h5>
                    <p>${{p.category}}</p>
                </div>
                <p><strong>${{p.price.toFixed(2)}} грн</strong></p>
            `;
            productListContainer.appendChild(itemEl);
        }});
    }};

    const openProductModal = async () => {{
        productListContainer.innerHTML = '<p>Завантаження страв...</p>';
        productModal.classList.add('active');
        if (allProducts.length === 0) {{
             allProducts = await fetchAllProducts();
        }}
        renderProductsInModal(allProducts);
    }};

    const closeProductModal = () => {{
        productModal.classList.remove('active');
        productSearchInput.value = '';
    }};

    // --- ИСПРАВЛЕНО: Функция инициализации формы ---
    const initializeForm = () => {{
        if (!window.initialOrderData) {{
            console.error("Initial order data is not defined!");
            return;
        }}
        
        const data = window.initialOrderData;
        orderForm.action = data.action;
        orderForm.querySelector('button[type="submit"]').textContent = data.submit_text;

        if (data.form_values) {{
            document.getElementById('phone_number').value = data.form_values.phone_number || '';
            document.getElementById('customer_name').value = data.form_values.customer_name || '';
            document.getElementById('delivery_type').value = data.form_values.is_delivery ? "delivery" : "pickup";
            document.getElementById('address').value = data.form_values.address || '';
            deliveryTypeSelect.dispatchEvent(new Event('change'));
        }}
        
        setInitialOrderItems(data.items);
    }};


    // --- Event Listeners ---
    deliveryTypeSelect.addEventListener('change', (e) => {{
        addressGroup.style.display = e.target.value === 'delivery' ? 'block' : 'none';
    }});

    addProductBtn.addEventListener('click', openProductModal);
    closeModalBtn.addEventListener('click', closeProductModal);
    productModal.addEventListener('click', (e) => {{
        if (e.target === productModal) closeProductModal();
    }});

    productSearchInput.addEventListener('input', (e) => {{
        const searchTerm = e.target.value.toLowerCase();
        const filteredProducts = allProducts.filter(p => p.name.toLowerCase().includes(searchTerm));
        renderProductsInModal(filteredProducts);
    }});
    
    productListContainer.addEventListener('click', (e) => {{
        const productEl = e.target.closest('.product-list-item');
        if (productEl) {{
            const productId = productEl.dataset.id;
            const product = allProducts.find(p => p.id == productId);
            if (product) {{
                addProductToOrder(product);
            }}
            closeProductModal();
        }}
    }});
    
    orderItemsBody.addEventListener('change', (e) => {{
        if (e.target.classList.contains('quantity-input')) {{
            const id = e.target.dataset.id;
            const newQuantity = parseInt(e.target.value, 10);
            if (newQuantity > 0) {{
                orderItems[id].quantity = newQuantity;
            }} else {{
                delete orderItems[id];
            }}
            renderOrderItems();
        }}
    }});

    orderItemsBody.addEventListener('click', (e) => {{
        if (e.target.classList.contains('remove-item-btn')) {{
            const id = e.target.dataset.id;
            delete orderItems[id];
            renderOrderItems();
        }}
    }});

    orderForm.addEventListener('submit', async (e) => {{
        e.preventDefault();
        const saveButton = orderForm.querySelector('button[type="submit"]');
        saveButton.textContent = 'Збереження...';
        saveButton.disabled = true;

        const payload = {{
            customer_name: document.getElementById('customer_name').value,
            phone_number: document.getElementById('phone_number').value,
            delivery_type: document.getElementById('delivery_type').value,
            address: document.getElementById('address').value,
            items: orderItems
        }};

        try {{
            const response = await fetch(orderForm.action, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json' }},
                body: JSON.stringify(payload)
            }});
            const result = await response.json();
            if (response.ok) {{
                alert(result.message);
                window.location.href = result.redirect_url || '/admin/orders';
            }} else {{
                alert(`Помилка: ${{result.detail || 'Невідома помилка'}}`);
                saveButton.textContent = 'Зберегти замовлення';
                saveButton.disabled = false;
            }}
        }} catch (error) {{
            console.error("Submit error:", error);
            alert('Помилка мережі. Не вдалося зберегти замовлення.');
            saveButton.textContent = 'Зберегти замовлення';
            saveButton.disabled = false;
        }}
    }});

    // --- ИСПРАВЛЕНО: Initial Calls ---
    initializeForm();
    renderOrderItems();
}});
</script>
"""

ADMIN_EMPLOYEE_BODY = """
<div class="card">
    <ul class="nav-tabs">
        <li class="nav-item"><a href="/admin/employees" class="active">Співробітники</a></li>
        <li class="nav-item"><a href="/admin/roles">Ролі</a></li>
    </ul>
    <h2>👤 Додати співробітника</h2>
    <form action="/admin/add_employee" method="post">
        <label for="full_name">Повне ім'я:</label><input type="text" id="full_name" name="full_name" required>
        <label for="phone_number">Номер телефону (для авторизації):</label><input type="text" id="phone_number" name="phone_number" placeholder="+380XX XXX XX XX" required>
        <label for="role_id">Роль:</label><select id="role_id" name="role_id" required>{role_options}</select>
        <button type="submit">Додати співробітника</button>
    </form>
</div>
<div class="card">
    <h2>👥 Список співробітників</h2>
    <p>🟢 - На зміні (авторизований)</p>
    <table><thead><tr><th>ID</th><th>Ім'я</th><th>Телефон</th><th>Роль</th><th>Статус</th><th>Telegram ID</th><th>Дії</th></tr></thead><tbody>
    {rows}
    </tbody></table>
</div>
"""

ADMIN_ROLES_BODY = """
<div class="card">
    <ul class="nav-tabs">
        <li class="nav-item"><a href="/admin/employees">Співробітники</a></li>
        <li class="nav-item"><a href="/admin/roles" class="active">Ролі</a></li>
    </ul>
    <h2>Додати нову роль</h2>
    <form action="/admin/add_role" method="post">
        <label for="name">Назва ролі:</label><input type="text" id="name" name="name" required>
        <div class="checkbox-group">
            <input type="checkbox" id="can_manage_orders" name="can_manage_orders" value="true">
            <label for="can_manage_orders">Може керувати замовленнями (Оператор)</label>
        </div>
        <div class="checkbox-group">
            <input type="checkbox" id="can_be_assigned" name="can_be_assigned" value="true">
            <label for="can_be_assigned">Може бути призначений на замовлення (Кур'єр)</label>
        </div>
        <button type="submit">Додати роль</button>
    </form>
</div>
<div class="card">
    <h2>Список ролей</h2>
    <table><thead><tr><th>ID</th><th>Назва</th><th>Керування замовленнями</th><th>Призначення на доставку</th><th>Дії</th></tr></thead><tbody>
    {rows}
    </tbody></table>
</div>
"""
ADMIN_REPORTS_BODY = """
<div class="card">
    <h2>Фільтр звіту</h2>
    <form action="/admin/reports/couriers" method="get" class="search-form">
        <label for="date_from">Дата з:</label>
        <input type="date" id="date_from" name="date_from" value="{date_from}">
        <label for="date_to">Дата по:</label>
        <input type="date" id="date_to" name="date_to" value="{date_to}">
        <button type="submit">Сформувати звіт</button>
    </form>
</div>
<div class="card">
    <h2>Результати звіту за період з {date_from_formatted} по {date_to_formatted}</h2>
    <table>
        <thead>
            <tr>
                <th>Ім'я кур'єра</th>
                <th>Кількість виконаних замовлень</th>
            </tr>
        </thead>
        <tbody>
            {report_rows}
        </tbody>
    </table>
</div>
"""

ADMIN_SETTINGS_BODY = """
<div class="card">
    <form action="/admin/settings" method="post" enctype="multipart/form-data">
        <h2>⚙️ Основні налаштування</h2>
        
        <h3>Telegram Боти</h3>
        <label>Токен клієнтського бота:</label><input type="text" name="client_bot_token" value="{client_bot_token}">
        <label>Токен адміністративного бота:</label><input type="text" name="admin_bot_token" value="{admin_bot_token}">
        <label>ID загального чату для замовлень:</label><input type="text" name="admin_chat_id" value="{admin_chat_id}" placeholder="Сюди будуть приходити всі замовлення для огляду">
        
        <h3>Зовнішній вигляд</h3>
        <label>Логотип (завантажте новий, щоб замінити):</label>
        <input type="file" name="logo_file" accept="image/*">
        {current_logo_html}

        <h3>Інтеграція з R-Keeper</h3>
        <div class="checkbox-group"><input type="checkbox" name="r_keeper_enabled" id="r_keeper_enabled" {r_keeper_enabled_checked}><label for="r_keeper_enabled">Увімкнути інтеграцію</label></div>
        <label>API URL:</label><input type="text" name="r_keeper_api_url" value="{r_keeper_api_url}">
        <label>Користувач:</label><input type="text" name="r_keeper_user" value="{r_keeper_user}">
        <label>Пароль:</label><input type="password" name="r_keeper_password" value="{r_keeper_password}">
        <label>Код станції:</label><input type="text" name="r_keeper_station_code" value="{r_keeper_station_code}">
        <label>Тип оплати:</label><input type="text" name="r_keeper_payment_type" value="{r_keeper_payment_type}">

        <h3 style="margin-top: 2rem;">Налаштування Favicon</h3>
        <p>Завантажте необхідні файли favicon. Після завантаження оновіть сторінку (Ctrl+F5), щоб побачити зміни.</p>
        <h4>Поточні іконки</h4>
        <div style="display: flex; gap: 20px; align-items: center; flex-wrap: wrap; margin-bottom: 2rem; background: #f0f0f0; padding: 1rem; border-radius: 8px;">
            <div><img src="/static/favicons/favicon-16x16.png?v={cache_buster}" alt="16x16" style="border: 1px solid #ccc;"><br><small>16x16</small></div>
            <div><img src="/static/favicons/favicon-32x32.png?v={cache_buster}" alt="32x32" style="border: 1px solid #ccc;"><br><small>32x32</small></div>
            <div><img src="/static/favicons/apple-touch-icon.png?v={cache_buster}" alt="Apple Touch Icon" style="width: 60px; height: 60px; border: 1px solid #ccc;"><br><small>Apple Icon</small></div>
        </div>

        <h4>Завантажити нові іконки</h4>
        <div class="form-grid" style="grid-template-columns: 1fr;">
            <div class="form-group"><label for="apple_touch_icon">apple-touch-icon.png (180x180)</label><input type="file" id="apple_touch_icon" name="apple_touch_icon" accept="image/png"></div>
            <div class="form-group"><label for="favicon_32x32">favicon-32x32.png</label><input type="file" id="favicon_32x32" name="favicon_32x32" accept="image/png"></div>
            <div class="form-group"><label for="favicon_16x16">favicon-16x16.png</label><input type="file" id="favicon_16x16" name="favicon_16x16" accept="image/png"></div>
            <div class="form-group"><label for="favicon_ico">favicon.ico (всі розміри)</label><input type="file" id="favicon_ico" name="favicon_ico" accept="image/x-icon"></div>
            <div class="form-group"><label for="site_webmanifest">site.webmanifest</label><input type="file" id="site_webmanifest" name=".webmanifest"></div>
        </div>
        
        <div style="margin-top: 2rem;">
            <button type="submit">Зберегти всі налаштування</button>
        </div>
    </form>
</div>
"""

# Template for the Menu Item management page in the admin panel
ADMIN_MENU_BODY = """
<div class="card">
    <h2>{form_title}</h2>
    <form action="{form_action}" method="post">
        <label for="title">Заголовок (текст на кнопці):</label>
        <input type="text" id="title" name="title" value="{item_title}" required>
        
        <label for="content">Зміст сторінки (можна використовувати HTML-теги):</label>
        <textarea id="content" name="content" rows="10" required>{item_content}</textarea>
        
        <label for="sort_order">Порядок сортування (менше = вище):</label>
        <input type="number" id="sort_order" name="sort_order" value="{item_sort_order}" required>
        
        <div class="checkbox-group">
            <input type="checkbox" id="show_on_website" name="show_on_website" value="true" {item_show_on_website_checked}>
            <label for="show_on_website">Показувати на сайті</label>
        </div>
        <div class="checkbox-group">
            <input type="checkbox" id="show_in_telegram" name="show_in_telegram" value="true" {item_show_in_telegram_checked}>
            <label for="show_in_telegram">Показувати в Telegram-боті</label>
        </div>
        
        <button type="submit">{button_text}</button>
        <a href="/admin/menu" class="button secondary">Скасувати</a>
    </form>
</div>
<div class="card">
    <h2>📜 Список сторінок</h2>
    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Заголовок</th>
                    <th>Сортування</th>
                    <th>На сайті</th>
                    <th>В Telegram</th>
                    <th>Дії</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
</div>
"""

ADMIN_ORDER_MANAGE_BODY = """
<style>
    .manage-grid {{
        display: grid;
        grid-template-columns: 2fr 1fr;
        gap: 2rem;
    }}
    .order-details-card .detail-item {{
        display: flex;
        justify-content: space-between;
        padding: 0.75rem 0;
        border-bottom: 1px solid var(--border-light);
    }}
    .order-details-card .detail-item:last-child {{
        border-bottom: none;
    }}
    .order-details-card .detail-item strong {{
        color: #6b7280;
    }}
    body.dark-mode .order-details-card .detail-item strong {{
        color: #9ca3af;
    }}
    .status-history {{
        list-style-type: none;
        padding-left: 1rem;
        border-left: 2px solid var(--border-light);
    }}
    .status-history li {{
        margin-bottom: 0.75rem;
        position: relative;
        font-size: 0.9rem;
    }}
    .status-history li::before {{
        content: '✓';
        position: absolute;
        left: -1.1rem;
        top: 2px;
        color: var(--primary-color);
        font-weight: 900;
    }}
    @media (max-width: 992px) {{
        .manage-grid {{
            grid-template-columns: 1fr;
        }}
    }}
</style>
<div class="manage-grid">
    <div class="left-column">
        <div class="card order-details-card">
            <h2>Деталі замовлення #{order_id}</h2>
            <div class="detail-item">
                <strong>Клієнт:</strong>
                <span>{customer_name}</span>
            </div>
            <div class="detail-item">
                <strong>Телефон:</strong>
                <span>{phone_number}</span>
            </div>
            <div class="detail-item">
                <strong>Адреса:</strong>
                <span>{address}</span>
            </div>
             <div class="detail-item">
                <strong>Сума:</strong>
                <span>{total_price} грн</span>
            </div>
            <div class="detail-item" style="flex-direction: column; align-items: start;">
                <strong style="margin-bottom: 0.5rem;">Склад замовлення:</strong>
                <div>{products_html}</div>
            </div>
        </div>
        <div class="card">
            <h2>Історія статусів</h2>
            {history_html}
        </div>
    </div>
    <div class="right-column">
        <div class="card">
            <h2>Керування статусом</h2>
            <form action="/admin/order/manage/{order_id}/set_status" method="post">
                <label for="status_id">Новий статус:</label>
                <select name="status_id" id="status_id" required>
                    {status_options}
                </select>
                <button type="submit">Змінити статус</button>
            </form>
        </div>
        <div class="card">
            <h2>Призначення кур'єра</h2>
            <form action="/admin/order/manage/{order_id}/assign_courier" method="post">
                <label for="courier_id">Кур'єр (на зміні):</label>
                <select name="courier_id" id="courier_id" required>
                    {courier_options}
                </select>
                <button type="submit">Призначити кур'єра</button>
            </form>
        </div>
    </div>
</div>
"""


# НОВЫЕ ШАБЛОНЫ ДЛЯ РАЗДЕЛА "КЛИЕНТЫ"

ADMIN_CLIENTS_LIST_BODY = """
<div class="card">
    <h2><i class="fa-solid fa-users-line"></i> Список клієнтів</h2>
    <form action="/admin/clients" method="get" class="search-form">
        <input type="text" name="search" placeholder="Пошук за іменем або телефоном..." value="{search_query}">
        <button type="submit">🔍 Знайти</button>
    </form>
    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>Ім'я</th>
                    <th>Телефон</th>
                    <th>Всього замовлень</th>
                    <th>Загальна сума</th>
                    <th>Дії</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    {pagination}
</div>
"""

ADMIN_CLIENT_DETAIL_BODY = """
<style>
    .client-info-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
    }}
    .info-block {{
        background-color: var(--bg-light);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid var(--border-light);
    }}
    .info-block h4 {{
        font-size: 0.9rem;
        color: #6b7280;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }}
    .info-block p {{
        font-size: 1.1rem;
        font-weight: 600;
    }}
    .order-summary-row {{
        cursor: pointer;
    }}
    .order-summary-row:hover {{
        background-color: #f3f4f6;
    }}
    body.dark-mode .order-summary-row:hover {{
        background-color: #374151;
    }}
    .order-details-row {{
        display: none;
    }}
    .details-content {{
        padding: 1.5rem;
        background-color: var(--bg-light);
    }}
    .status-history {{
        list-style-type: none;
        padding-left: 1rem;
        border-left: 2px solid var(--border-light);
    }}
    .status-history li {{
        margin-bottom: 0.5rem;
        position: relative;
    }}
    .status-history li::before {{
        content: '✓';
        position: absolute;
        left: -1.1rem;
        top: 2px;
        color: var(--primary-color);
        font-weight: 900;
    }}
</style>
<div class="card">
    <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 2rem;">
        <i class="fa-solid fa-user-circle" style="font-size: 3rem;"></i>
        <div>
            <h2 style="margin-bottom: 0;">{client_name}</h2>
            <a href="tel:{phone_number}">{phone_number}</a>
        </div>
    </div>
    <div class="client-info-grid">
        <div class="info-block">
            <h4>Остання адреса</h4>
            <p>{address}</p>
        </div>
        <div class="info-block">
            <h4>Всього замовлень</h4>
            <p>{total_orders}</p>
        </div>
        <div class="info-block">
            <h4>Загальна сума</h4>
            <p>{total_spent} грн</p>
        </div>
    </div>
</div>
<div class="card">
    <h3>Історія замовлень</h3>
    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Дата</th>
                    <th>Статус</th>
                    <th>Сума</th>
                    <th>Доставив</th>
                    <th>Деталі</th>
                </tr>
            </thead>
            <tbody>
                {order_rows}
            </tbody>
        </table>
    </div>
</div>
<script>
    function toggleDetails(row) {{
        const detailsRow = row.nextElementSibling;
        const icon = row.querySelector('i');
        if (detailsRow.style.display === 'table-row') {{
            detailsRow.style.display = 'none';
            icon.classList.remove('fa-chevron-up');
            icon.classList.add('fa-chevron-down');
        }} else {{
            detailsRow.style.display = 'table-row';
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-up');
        }}
    }}
</script>
"""
