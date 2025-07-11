from flet import *
import os
import shutil
import sqlite3
from telegram import Bot
import asyncio
import sqlite3
import threading
from PIL import Image as PILImage
from datetime import datetime
from flet import (
    AlertDialog, Column, Container, Divider, Row, SnackBar, 
    SnackBarBehavior, Text, TextButton, Colors, FontWeight,
    RoundedRectangleBorder, ScrollMode, TextAlign, alignment
)
# === إعدادات البرنامج ===
DB_PATH = 'products.db'
SETTINGS_DB_PATH = 'bot_settings.db'
IMAGES_FOLDER = os.path.join(os.path.dirname(__file__), 'product_images')
IMAGE_SIZE = (300, 300)

# إضافة هنا: متغيرات إدارة البوت
telegram_bot_app = None  # سيحتوي على تطبيق البوت
telegram_bot_loop = None  # سيحتوي على event loop الخاص بالبوت
telegram_bot_thread = None  # ثيل تشغيل البوت
# === إنشاء المجلدات والجداول ===
os.makedirs(IMAGES_FOLDER, exist_ok=True)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            sold INTEGER DEFAULT 0,
            image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            quantity INTEGER,
            sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )''')

def init_settings_db():
    with sqlite3.connect(SETTINGS_DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS telegram_bot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

init_db()
init_settings_db()

# === أدوات مساعدة ===
def resize_image(input_path, output_path, size):
    with PILImage.open(input_path) as img:
        img.thumbnail(size, PILImage.LANCZOS)
        img.save(output_path)

def send_telegram_notification(message: str):
    try:
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            settings = conn.execute(
                "SELECT bot_token, chat_id FROM telegram_bot ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if not settings or not settings[0] or not settings[1]:
            return

        bot_token, chat_id = settings

        async def _send():
            try:
                bot = Bot(token=bot_token)
                await bot.send_message(
                    chat_id=chat_id, 
                    text=message,
                    parse_mode="Markdown"  # لتمييز النصوص المهمة
                )
            except Exception as e:
                pass

        if telegram_bot_loop and telegram_bot_loop.is_running():
            asyncio.run_coroutine_threadsafe(_send(), telegram_bot_loop)
        else:
            asyncio.run(_send())

    except Exception as e:
        pass


async def send_telegram_message(bot_token, chat_id, message):
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        pass

async def send_telegram_photo(bot_token, chat_id, photo_path, caption=None):
    try:
        bot = Bot(token=bot_token)
        with open(photo_path, 'rb') as photo:
            await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
    except Exception as e:
        pass

def is_admin(user_id):
    with sqlite3.connect(SETTINGS_DB_PATH) as conn:
        admin = conn.execute(
            "SELECT 1 FROM admin_users WHERE user_id=?",
            (str(user_id),)
        ).fetchone()
    return admin is not None

def add_admin(user_id, username=None):
    try:
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO admin_users (user_id, username) VALUES (?, ?)",
                (str(user_id), username)
            )
        return True
    except Exception as e:
        return False

def remove_admin(user_id):
    try:
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            conn.execute(
                "DELETE FROM admin_users WHERE user_id=?",
                (str(user_id),))
        return True
    except Exception as e:
        return False

def list_admins():
    with sqlite3.connect(SETTINGS_DB_PATH) as conn:
        admins = conn.execute(
            "SELECT user_id, username, created_at FROM admin_users ORDER BY created_at DESC"
        ).fetchall()
    return admins

# === واجهة المستخدم الرئيسية ===
def main(page: Page):
    page.title = "نظام إدارة المنتجات"
    page.theme_mode = ThemeMode.LIGHT
    page.vertical_alignment = MainAxisAlignment.START
    page.horizontal_alignment = CrossAxisAlignment.CENTER
    page.window.full_screen = True
    
    # حالة التطبيق
    selected_products = {}
    current_view = "products"
    edit_product_id = None
    telegram_bot_thread = None
    telegram_bot_event = None
    
    # تعريف أنماط الأزرار
    button_style = ButtonStyle(
        shape=RoundedRectangleBorder(radius=8),
        padding=20,
        elevation=5,
    )

    # شريط التنقل
    def create_nav_rail(selected_index):
        return NavigationRail(
            selected_index=selected_index,
            label_type=NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=150,
            destinations=[
                NavigationRailDestination(
                    icon=Icons.SHOPPING_BAG_OUTLINED,
                    selected_icon=Icons.SHOPPING_BAG,
                    label="المنتجات"
                ),
                NavigationRailDestination(
                    icon=Icons.ADD_CIRCLE_OUTLINE,
                    selected_icon=Icons.ADD_CIRCLE,
                    label="إضافة منتج"
                ),
                NavigationRailDestination(
                    icon=Icons.EDIT_OUTLINED,
                    selected_icon=Icons.EDIT,
                    label="تعديل المنتجات"
                ),
                NavigationRailDestination(
                    icon=Icons.SETTINGS_OUTLINED,
                    selected_icon=Icons.SETTINGS,
                    label="إعدادات البوت"
                ),
                NavigationRailDestination(
                    icon=Icons.ADMIN_PANEL_SETTINGS_OUTLINED,
                    selected_icon=Icons.ADMIN_PANEL_SETTINGS,
                    label="إدارة المسؤولين"
                )
            ],
            on_change=lambda e: navigate_to(e.control.selected_index)
        )
    
    # === صفحة المنتجات ===
    search_field = TextField(
        label="بحث عن منتج",
        prefix_icon=Icons.SEARCH,
        width=300,
        on_change=lambda e: refresh_products()
    )
    
    products_grid = GridView(
        runs_count=3,
        max_extent=350,
        child_aspect_ratio=0.9,
        spacing=10,
        run_spacing=10,
        expand=True,
    )

    total_price_banner = Container(
        content=Row([
            Text("المجموع:", size=18, weight=FontWeight.BOLD),
            Text("0", size=18, weight=FontWeight.BOLD, color=Colors.BLUE_700),
            Text("درهم", size=18, weight=FontWeight.BOLD)
        ], spacing=5),
        bgcolor=Colors.BLUE_50,
        padding=15,
        border_radius=10,
        visible=False,
        width=300,
        alignment=alignment.center
    )
    def show_total(e=None):  # أضفت e=None لجعلها تعمل مع الأحداث
        if not selected_products:
            page.snack_bar = SnackBar(
                content=Text("⚠️ لم يتم اختيار أي منتجات", color=Colors.WHITE),
                bgcolor=Colors.RED_700,
                behavior=SnackBarBehavior.FLOATING,
                elevation=10,
                shape=RoundedRectangleBorder(radius=10),
                show_close_icon=True
            )
            page.snack_bar.open = True
            page.update()
            return
        
        # حساب المجموع
        total = sum(price * qty for price, qty in selected_products.values())
        
        # إنشاء محتوى الفاتورة
        items_list = Column([], spacing=5, scroll=ScrollMode.AUTO)
        
        with sqlite3.connect(DB_PATH) as conn:
            for product_id, (price, qty) in selected_products.items():
                product = conn.execute(
                    "SELECT name FROM products WHERE id=?",
                    (product_id,)
                ).fetchone()
                
                if product:
                    items_list.controls.append(
                        Container(
                            content=Row([
                                Text(product[0], width=200, size=14),
                                Text(f"{qty} × {price} درهم", width=100, size=14),
                                Text(f"{qty * price} درهم", width=100, 
                                    size=14, weight=FontWeight.BOLD)
                            ], 
                            alignment=MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=CrossAxisAlignment.CENTER),
                            padding=5
                        ))
        
        # إضافة المجموع الكلي
        items_list.controls.append(Divider())
        items_list.controls.append(
            Container(
                content=Row([
                    Text("المجموع الكلي:", size=16, weight=FontWeight.BOLD),
                    Text(f"{total} درهم", size=16, weight=FontWeight.BOLD,
                        color=Colors.BLUE_700)
                ], 
                alignment=MainAxisAlignment.SPACE_BETWEEN),
                padding=10
            )
        )
        
        # إنشاء النافذة المنبثقة
        dlg = AlertDialog(
            modal=True,
            title=Container(
                content=Text("تفاصيل الفاتورة", 
                        size=20, 
                        weight=FontWeight.BOLD,
                        text_align=TextAlign.CENTER),
                padding=10
            ),
            content=Container(
                content=Column([
                    Text("المنتجات المختارة:", 
                        weight=FontWeight.BOLD,
                        size=16),
                    Container(height=10),
                    items_list
                ]),
                width=500,
                height=300,
                padding=10
            ),
            actions=[
                TextButton("إغلاق", 
                        on_click=lambda e: close_dialog(),
                        style=ButtonStyle(color=Colors.BLUE)),
                TextButton(
                    "تأكيد الشراء",
                    on_click=lambda e: [buy_selected_products(), close_dialog()],
                    style=ButtonStyle(
                        color=Colors.WHITE,
                        bgcolor=Colors.GREEN_600,
                        padding=20
                    )
                )
            ],
            actions_alignment=MainAxisAlignment.END,
            shape=RoundedRectangleBorder(radius=15)
        )
        
        def close_dialog():
            page.close(dlg)

        
        page.dialog = dlg
        page.open(dlg)

    products_page = Column([
        Row([
            search_field,
            ElevatedButton(
                "حساب المجموع",
                icon=Icons.CALCULATE,
                on_click= show_total
            )
        ], wrap=False, alignment=MainAxisAlignment.SPACE_BETWEEN),
        total_price_banner,
        products_grid
    ], expand=True)

    # === صفحة إضافة منتج ===
    product_name = TextField(
        label="اسم المنتج",
        width=600,
        height=70,
        border_radius=15,
        border_color=Colors.BLUE_400,
        focused_border_color=Colors.BLUE_700,
        text_size=16,
        content_padding=20,
        filled=True,
        bgcolor=Colors.GREY_50
    )

    product_price = TextField(
        label="السعر (درهم)",
        keyboard_type=KeyboardType.NUMBER,
        width=280,
        height=70,
        border_radius=15,
        border_color=Colors.BLUE_400,
        focused_border_color=Colors.BLUE_700,
        text_size=16,
        content_padding=20,
        prefix_text="د.م",
        filled=True,
        bgcolor=Colors.GREY_50
    )

    product_quantity = TextField(
        label="الكمية المتاحة",
        keyboard_type=KeyboardType.NUMBER,
        width=280,
        height=70,
        border_radius=15,
        border_color=Colors.BLUE_400,
        focused_border_color=Colors.BLUE_700,
        text_size=16,
        content_padding=20,
        filled=True,
        bgcolor=Colors.GREY_50
    )

    product_image_path = Text(
        size=14,
        color=Colors.GREY_600,
        weight=FontWeight.BOLD
    )

    product_preview = Container(
        width=300,
        height=300,
        border_radius=15,
        bgcolor=Colors.GREY_100,
        alignment=alignment.center,
        content=Column(
            [
                Icon(Icons.IMAGE_OUTLINED, size=80, color=Colors.GREY_400),
                Text("صورة المنتج", size=16, color=Colors.GREY_500)
            ],
            alignment=MainAxisAlignment.CENTER,
            horizontal_alignment=CrossAxisAlignment.CENTER
        )
    )

    def update_preview(e):
        if file_picker.result and file_picker.result.files:
            file = file_picker.result.files[0]
            product_preview.content = Image(
                src=file.path,
                width=300,
                height=300,
                fit=ImageFit.COVER,
                border_radius=15
            )
            product_image_path.value = file.name
        else:
            product_preview.content = Column(
                [
                    Icon(Icons.IMAGE_OUTLINED, size=80, color=Colors.GREY_400),
                    Text("صورة المنتج", size=16, color=Colors.GREY_500)
                ],
                alignment=MainAxisAlignment.CENTER,
                horizontal_alignment=CrossAxisAlignment.CENTER
            )
            product_image_path.value = "لم يتم اختيار ملف"
        page.update()

    file_picker = FilePicker(on_result=update_preview)
    page.overlay.append(file_picker)

    def save_product(e):
        if not all([product_name.value, product_price.value, product_quantity.value]):
            show_snackbar("الرجاء ملء جميع الحقول المطلوبة")
            return
        
        try:
            price = float(product_price.value)
            quantity = int(product_quantity.value)
        except ValueError:
            show_snackbar("القيم المدخلة غير صالحة")
            return
        
        image_path = None
        if file_picker.result and file_picker.result.files:
            try:
                file = file_picker.result.files[0]
                filename = f"{datetime.now().timestamp()}.jpg"
                dst = os.path.join(IMAGES_FOLDER, filename)
                
                shutil.copy(file.path, dst)
                resize_image(dst, dst, IMAGE_SIZE)
                image_path = dst
            except Exception as e:
            
                show_snackbar("حدث خطأ أثناء حفظ الصورة")
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO products (name, price, quantity, image) VALUES (?, ?, ?, ?)",
                (product_name.value, price, quantity, image_path)
            )
        
        message = f"تمت إضافة منتج جديد:\n{product_name.value}\nالسعر: {price} درهم\nالكمية: {quantity}"
        send_telegram_notification(message)
        
        product_name.value = ""
        product_price.value = ""
        product_quantity.value = ""
        product_image_path.value = ""
        
        file_picker._result = None
        file_picker.update()
        
        show_snackbar("تم حفظ المنتج بنجاح")
        navigate_to(0)
        page.update()

    add_product_page = Container(
        padding=40,
        content=Column(
            [
                Container(
                    content=Text("إضافة منتج جديد", size=28, weight=FontWeight.BOLD, color=Colors.BLUE_700),
                    padding=padding.only(bottom=30)
                ),
                
                Card(
                    elevation=15,
                    shape=RoundedRectangleBorder(radius=20),
                    content=Container(
                        padding=40,
                        bgcolor=Colors.WHITE,
                        content=Column(
                            [
                                Row(
                                    [
                                        product_preview,
                                        Container(width=40),
                                        Column(
                                            [
                                                product_name,
                                                Container(height=20),
                                                Row(
                                                    [
                                                        product_price,
                                                        Container(width=20),
                                                        product_quantity,
                                                    ],
                                                    alignment=MainAxisAlignment.START
                                                ),
                                                Container(height=20),
                                                Row(
                                                    [
                                                        ElevatedButton(
                                                            content=Row(
                                                                [
                                                                    Icon(Icons.IMAGE, color=Colors.WHITE),
                                                                    Text("اختر صورة المنتج", color=Colors.WHITE)
                                                                ],
                                                                spacing=10
                                                            ),
                                                            style=ButtonStyle(
                                                                shape=RoundedRectangleBorder(radius=10),
                                                                padding={"left": 30, "right": 30, "top": 15, "bottom": 15},
                                                                bgcolor=Colors.BLUE_400,
                                                            ),
                                                            on_click=lambda _: file_picker.pick_files()
                                                        ),
                                                        Container(width=20),
                                                        product_image_path
                                                    ],
                                                    alignment=MainAxisAlignment.START
                                                )
                                            ],
                                            alignment=MainAxisAlignment.CENTER,
                                            expand=True
                                        )
                                    ],
                                    spacing=20
                                ),
                                Container(height=40),
                                Row(
                                    [
                                        ElevatedButton(
                                            content=Row(
                                                [
                                                    Icon(Icons.SAVE, color=Colors.WHITE),
                                                    Text("حفظ المنتج", color=Colors.WHITE)
                                                ],
                                                spacing=15
                                            ),
                                            style=ButtonStyle(
                                                shape=RoundedRectangleBorder(radius=10),
                                                padding={"left": 50, "right": 50, "top": 20, "bottom": 20},
                                                bgcolor=Colors.GREEN_600,
                                            ),
                                            on_click=save_product
                                        ),
                                        Container(width=30),
                                        ElevatedButton(
                                            content=Row(
                                                [
                                                    Icon(Icons.CANCEL, color=Colors.WHITE),
                                                    Text("إلغاء", color=Colors.WHITE)
                                                ],
                                                spacing=15
                                            ),
                                            style=ButtonStyle(
                                                shape=RoundedRectangleBorder(radius=10),
                                                padding={"left": 50, "right": 50, "top": 20, "bottom": 20},
                                                bgcolor=Colors.RED_600,
                                            ),
                                            on_click=lambda e: navigate_to(0)
                                        )
                                    ],
                                    alignment=MainAxisAlignment.CENTER
                                )
                            ],
                            horizontal_alignment=CrossAxisAlignment.CENTER
                        )
                    )
                )
            ],
            scroll=ScrollMode.AUTO,
            expand=True
        )
    )
    
    # === صفحة تعديل المنتجات ===
    edit_search_field = TextField(
        label="بحث عن منتج للتعديل",
        prefix_icon=Icons.SEARCH,
        width=300,
        on_change=lambda e: refresh_edit_products()
    )
    
    edit_products_grid = GridView(
        runs_count=3,
        max_extent=350,
        child_aspect_ratio=0.9,
        spacing=10,
        run_spacing=10,
        expand=True
    )
    
    edit_page = Column([
        edit_search_field,
        Container(edit_products_grid, expand=True)
    ], expand=True)

    # === صفحة تعديل منتج فردي ===
    edit_name = TextField(label="اسم المنتج", width=400)
    edit_price = TextField(label="السعر", keyboard_type=KeyboardType.NUMBER, width=200)
    edit_quantity = TextField(label="الكمية المتاحة", keyboard_type=KeyboardType.NUMBER, width=200)
    edit_sold = TextField(label="عدد المبيعات", keyboard_type=KeyboardType.NUMBER, width=200, read_only=True)
    edit_image_path = Text()
    
    edit_file_picker = FilePicker()
    page.overlay.append(edit_file_picker)
    
    def update_product(e):
        if not edit_product_id or not all([edit_name.value, edit_price.value, edit_quantity.value]):
            show_snackbar("الرجاء ملء جميع الحقول المطلوبة")
            return
        
        try:
            price = float(edit_price.value)
            quantity = int(edit_quantity.value)
        except ValueError:
            show_snackbar("القيم المدخلة غير صالحة")
            return
        
        with sqlite3.connect(DB_PATH) as conn:
            old_image = conn.execute(
                "SELECT image FROM products WHERE id=?",
                (edit_product_id,)
            ).fetchone()[0]
            
            new_image = old_image
            if edit_file_picker.result and edit_file_picker.result.files:
                try:
                    file = edit_file_picker.result.files[0]
                    filename = f"{datetime.now().timestamp()}.jpg"
                    dst = os.path.join(IMAGES_FOLDER, filename)
                    shutil.copy(file.path, dst)
                    resize_image(dst, dst, IMAGE_SIZE)
                    new_image = dst
                    
                    if old_image and os.path.exists(old_image):
                        os.remove(old_image)
                except Exception as e:
                    
                    show_snackbar("حدث خطأ أثناء حفظ الصورة الجديدة")
            
            conn.execute(
                "UPDATE products SET name=?, price=?, quantity=?, image=? WHERE id=?",
                (edit_name.value, price, quantity, new_image, edit_product_id)
            )
        
        message = f"تم تحديث المنتج:\n{edit_name.value}\nالسعر الجديد: {price} درهم\nالكمية الجديدة: {quantity}"
        send_telegram_notification(message)
        
        show_snackbar("تم تحديث المنتج بنجاح")
        navigate_to(2)
    
    edit_product_page = Container(
    padding=20,
    content=Column(
        [
            Container(
                content=Row(
                    [
                        Icon(Icons.EDIT, color=Colors.BLUE_700, size=28),
                        Text("تعديل المنتج", size=28, weight=FontWeight.BOLD, color=Colors.BLUE_700),
                    ],
                    alignment=MainAxisAlignment.CENTER,
                    spacing=10
                ),
                padding=padding.only(bottom=30)
            ),
            
            Card(
                elevation=15,
                shape=RoundedRectangleBorder(radius=20),
                content=Container(
                    padding=30,
                    content=Column(
                        [
                            # صورة المنتج مع زر التغيير
                            Container(
                                content=Stack(
                                    [
                                        Container(
                                            content=ElevatedButton(
                                                "تغيير الصورة",
                                                icon=Icons.CAMERA_ALT,
                                                style=ButtonStyle(
                                                    shape=RoundedRectangleBorder(radius=10),
                                                    bgcolor=Colors.BLUE_600,
                                                    color=Colors.WHITE,
                                                    padding=15
                                                ),
                                                on_click=lambda _: edit_file_picker.pick_files(),
                                            ),
                                            bottom=10,
                                            right=10,
                                            alignment=alignment.bottom_right
                                        )
                                    ],
                                    width=300,
                                    height=200
                                ),
                                alignment=alignment.center,
                                padding=padding.only(bottom=20)
                            ),
                            
                            # رسالة حالة الصورة
                            Container(
                                content=Text(
                                    edit_image_path.value if edit_image_path.value else "لم يتم اختيار صورة",
                                    size=12,
                                    color=Colors.GREY_600,
                                    text_align=TextAlign.CENTER
                                ),
                                padding=padding.only(bottom=20),
                                visible=edit_image_path.value != ""
                            ),
                            
                            # حقول التعديل
                            Container(
                                content=Column(
                                    [
                                        TextField(
                                            label="اسم المنتج",
                                            value=edit_name.value,
                                            on_change=lambda e: edit_name.__setattr__('value', e.control.value),
                                            border_radius=10,
                                            border_color=Colors.BLUE_400,
                                            filled=True,
                                            bgcolor=Colors.GREY_50,
                                            content_padding=15
                                        ),
                                        Container(height=15),
                                        Row(
                                            [
                                                TextField(
                                                    label="السعر (درهم)",
                                                    value=edit_price.value,
                                                    on_change=lambda e: edit_price.__setattr__('value', e.control.value),
                                                    width=180,
                                                    border_radius=10,
                                                    border_color=Colors.BLUE_400,
                                                    filled=True,
                                                    bgcolor=Colors.GREY_50,
                                                    content_padding=15,
                                                    prefix_text="د.م"
                                                ),
                                                TextField(
                                                    label="الكمية المتاحة",
                                                    value=edit_quantity.value,
                                                    on_change=lambda e: edit_quantity.__setattr__('value', e.control.value),
                                                    width=180,
                                                    border_radius=10,
                                                    border_color=Colors.BLUE_400,
                                                    filled=True,
                                                    bgcolor=Colors.GREY_50,
                                                    content_padding=15
                                                ),
                                                TextField(
                                                    label="عدد المبيعات",
                                                    value=edit_sold.value,
                                                    read_only=True,
                                                    width=180,
                                                    border_radius=10,
                                                    border_color=Colors.GREY_400,
                                                    filled=True,
                                                    bgcolor=Colors.GREY_200,
                                                    content_padding=15
                                                )
                                            ],
                                            spacing=20,
                                            alignment=MainAxisAlignment.CENTER
                                        )
                                    ]
                                )
                            ),
                            
                            # أزرار التحكم
                            Container(
                                content=Row(
                                    [
                                        ElevatedButton(
                                            content=Row(
                                                [
                                                    Icon(Icons.SAVE, color=Colors.WHITE),
                                                    Text("حفظ التعديلات", color=Colors.WHITE)
                                                ],
                                                spacing=10
                                            ),
                                            style=ButtonStyle(
                                                shape=RoundedRectangleBorder(radius=10),
                                                padding={"left": 30, "right": 30, "top": 15, "bottom": 15},
                                                bgcolor=Colors.GREEN_600,
                                                elevation=5
                                            ),
                                            on_click=update_product
                                        ),
                                        Container(width=20),
                                        ElevatedButton(
                                            content=Row(
                                                [
                                                    Icon(Icons.ARROW_BACK, color=Colors.WHITE),
                                                    Text("العودة للقائمة", color=Colors.WHITE)
                                                ],
                                                spacing=10
                                            ),
                                            style=ButtonStyle(
                                                shape=RoundedRectangleBorder(radius=10),
                                                padding={"left": 30, "right": 30, "top": 15, "bottom": 15},
                                                bgcolor=Colors.BLUE_600,
                                                elevation=5
                                            ),
                                            on_click=lambda e: navigate_to(2)
                                        )
                                    ],
                                    alignment=MainAxisAlignment.CENTER,
                                    spacing=20
                                ),
                                padding=padding.only(top=30)
                            )
                        ],
                        horizontal_alignment=CrossAxisAlignment.CENTER
                    )
                )
            )
        ],
        spacing=0,
        scroll=ScrollMode.AUTO,
        expand=True
    )
)
    
    # === صفحة إعدادات البوت ===
    def create_bot_settings_page():
        bot_token_field = TextField(
            label="توكن البوت",
            width=600,
            height=70,
            border_radius=15,
            border_color=Colors.BLUE_400,
            focused_border_color=Colors.BLUE_700,
            text_size=16,
            content_padding=20,
            filled=True,
            bgcolor=Colors.GREY_50,
            password=True,
            can_reveal_password=True
        )

        chat_id_field = TextField(
            label="معرف المحادثة (Chat ID)",
            width=600,
            height=70,
            border_radius=15,
            border_color=Colors.BLUE_400,
            focused_border_color=Colors.BLUE_700,
            text_size=16,
            content_padding=20,
            filled=True,
            bgcolor=Colors.GREY_50
        )

        def load_bot_settings():
            with sqlite3.connect(SETTINGS_DB_PATH) as conn:
                settings = conn.execute(
                    "SELECT bot_token, chat_id FROM telegram_bot ORDER BY id DESC LIMIT 1"
                ).fetchone()
                
                if settings:
                    bot_token_field.value = settings[0]
                    chat_id_field.value = settings[1]
                    page.update()

        load_bot_settings()

        def save_settings(e):
            if not bot_token_field.value or not chat_id_field.value:
                show_snackbar("الرجاء إدخال التوكن ورقم الشات")
                return
            
            try:
                with sqlite3.connect(SETTINGS_DB_PATH) as conn:
                    conn.execute("DELETE FROM telegram_bot")
                    conn.execute(
                        "INSERT INTO telegram_bot (bot_token, chat_id) VALUES (?, ?)",
                        (bot_token_field.value, chat_id_field.value)
                    )
                show_snackbar("تم حفظ الإعدادات بنجاح")
                restart_telegram_bot()
            except Exception as e:
                show_snackbar(f"خطأ في الحفظ: {str(e)}")

        def test_connection(e):
            if not bot_token_field.value or not chat_id_field.value:
                show_snackbar("الرجاء إدخال التوكن ورقم الشات أولاً")
                return
            
            try:
                bot = Bot(token=bot_token_field.value)
                asyncio.run(bot.send_message(
                    chat_id=chat_id_field.value,
                    text="✅ تم الاتصال بنجاح من نظام إدارة المنتجات"
                ))
                show_snackbar("تم اختبار الاتصال بنجاح")
            except Exception as e:
                show_snackbar(f"فشل الاتصال: {str(e)}")

        def delete_settings(e):
            def confirm_delete(e):
                try:
                    with sqlite3.connect(SETTINGS_DB_PATH) as conn:
                        conn.execute("DELETE FROM telegram_bot")
                    bot_token_field.value = ""
                    chat_id_field.value = ""
                    page.update()
                    show_snackbar("تم حذف الإعدادات")
                    stop_telegram_bot()
                    page.close(dlg)
                except Exception as e:
                    show_snackbar(f"خطأ في الحذف: {str(e)}")
            
            dlg = AlertDialog(
                title=Text("تأكيد الحذف"),
                content=Text("هل أنت متأكد من حذف إعدادات البوت؟"),
                actions=[
                    TextButton("نعم", on_click=confirm_delete),
                    TextButton("لا", on_click=lambda e: page.close(dlg)),
                ]
            )
            page.dialog = dlg
            dlg.open = True
            page.update()

        return Container(
            padding=40,
            content=Column(
                [
                    Text("إعدادات بوت Telegram", size=28, weight=FontWeight.BOLD, color=Colors.BLUE_700),
                    Card(
                        elevation=15,
                        content=Container(
                            padding=30,
                            content=Column(
                                [
                                    bot_token_field,
                                    chat_id_field,
                                    Row(
                                        [
                                            ElevatedButton(
                                                "حفظ الإعدادات",
                                                icon=Icons.SAVE,
                                                on_click=save_settings,
                                                style=ButtonStyle(
                                                    bgcolor=Colors.GREEN_600,
                                                    color=Colors.WHITE,
                                                    padding=20
                                                )
                                            ),
                                            ElevatedButton(
                                                "اختبار الاتصال",
                                                icon=Icons.GRID_ON,
                                                on_click=test_connection,
                                                style=ButtonStyle(
                                                    bgcolor=Colors.BLUE_600,
                                                    color=Colors.WHITE,
                                                    padding=20
                                                )
                                            ),
                                            ElevatedButton(
                                                "حذف الإعدادات",
                                                icon=Icons.DELETE,
                                                on_click=delete_settings,
                                                style=ButtonStyle(
                                                    bgcolor=Colors.RED_600,
                                                    color=Colors.WHITE,
                                                    padding=20
                                                )
                                            )
                                        ],
                                        spacing=20,
                                        alignment=MainAxisAlignment.CENTER
                                    ),
                                    Container(height=20),
                                    Divider(),
                                    Container(
                                        Text("تعليمات:", size=18, weight=FontWeight.BOLD),
                                        padding=padding.only(bottom=10)
                                    ),
                                    Text("1. احصل على توكن البوت من @BotFather", size=14),
                                    Text("2. احصل على Chat ID من @userinfobot", size=14)
                                ],
                                spacing=20,
                                horizontal_alignment=CrossAxisAlignment.CENTER
                            )
                        )
                    )
                ],
                spacing=30,
                horizontal_alignment=CrossAxisAlignment.CENTER,
                scroll=ScrollMode.AUTO
            )
        )

    # === صفحة إدارة المسؤولين المحدثة ===
    def create_admin_management_page():
        # حقول الإدخال
        admin_user_id = TextField(
            label="معرف المستخدم (User ID)",
            width=400,
            height=70,
            border_radius=15,
            border_color=Colors.BLUE_400,
            focused_border_color=Colors.BLUE_700,
            text_size=16,
            content_padding=20,
            filled=True,
            bgcolor=Colors.GREY_50,
            hint_text="مثال: 123456789"
        )

        admin_username = TextField(
            label="اسم المستخدم (اختياري)",
            width=400,
            height=70,
            border_radius=15,
            border_color=Colors.BLUE_400,
            focused_border_color=Colors.BLUE_700,
            text_size=16,
            content_padding=20,
            filled=True,
            bgcolor=Colors.GREY_50,
            hint_text="مثال: @username"
        )

        # عناصر واجهة المستخدم
        admins_list = ListView(expand=True)
        search_field = TextField(
            label="بحث عن مسؤول",
            prefix_icon=Icons.SEARCH,
            width=400,
            on_change=lambda e: refresh_admins_list(),
            hint_text="ابحث بالاسم أو المعرف"
        )

        # إحصائيات المسؤولين
        stats_row = Row([
            Text("عدد المسؤولين: 0", size=16, weight=FontWeight.BOLD),
            Container(width=20),
            Text("آخر إضافة: -", size=16, weight=FontWeight.BOLD)
        ], alignment=MainAxisAlignment.CENTER)

        def refresh_admins_list(search_term=None):
            admins_list.controls.clear()
            admins = list_admins()
            
            # تحديث الإحصائيات
            stats_row.controls[0].value = f"عدد المسؤولين: {len(admins)}"
            if admins:
                last_added = admins[0]  # أول عنصر هو الأحدث بسبب الترتيب في SQL
                stats_row.controls[2].value = f"آخر إضافة: {last_added[1] if last_added[1] else last_added[0]}"
            
            if not admins:
                admins_list.controls.append(
                    ListTile(
                        title=Text("لا يوجد مسؤولين مسجلين", 
                                color=Colors.GREY_500,
                                text_align=TextAlign.CENTER),
                        leading=Icon(Icons.WARNING, color=Colors.ORANGE)
                    )
                )
            else:
                for user_id, username, created_at in admins:
                    # فلترة البحث إذا وجد
                    if search_term and (search_term.lower() not in (username or "").lower() and 
                                    search_term not in user_id):
                        continue
                        
                    admins_list.controls.append(
                        Card(
                            elevation=2,
                            content=Container(
                                padding=10,
                                content=Column([
                                    ListTile(
                                        leading=CircleAvatar(
                                            content=Text(username[0].upper() if username else "?", 
                                                    color=Colors.WHITE),
                                            bgcolor=Colors.BLUE_400
                                        ),
                                        title=Text(username if username else f"المسؤول {user_id}"),
                                        subtitle=Column([
                                            Text(f"معرف المستخدم: {user_id}"),
                                            Text(f"تمت الإضافة: {created_at}", 
                                                size=12, 
                                                color=Colors.GREY)
                                        ], spacing=0),
                                        trailing=PopupMenuButton(
                                            icon=Icon(Icons.MORE_VERT),
                                            items=[
                                                PopupMenuItem(
                                                    content=Text("حذف المسؤول"),
                                                    on_click=lambda e, uid=user_id: remove_admin_action(uid),
                                                ),
                                                PopupMenuItem(
                                                    content=Text("نسخ المعرف"),
                                                    on_click=lambda e, uid=user_id: copy_to_clipboard(uid),
                                                )
                                            ]
                                        )
                                    ),
                                    Divider(height=1)
                                ], spacing=0)
                            )
                        )
                    )
            page.update()

        def copy_to_clipboard(text):
            page.set_clipboard(text)
            show_snackbar(f"تم نسخ المعرف: {text}")

        def add_admin_action(e):
            if not admin_user_id.value:
                show_snackbar("الرجاء إدخال معرف المستخدم")
                return
            
            if not admin_user_id.value.isdigit():
                show_snackbar("معرف المستخدم يجب أن يكون رقماً")
                return
            
            try:
                success = add_admin(admin_user_id.value, admin_username.value)
                if success:
                    show_snackbar("تمت إضافة المسؤول بنجاح")
                    admin_user_id.value = ""
                    admin_username.value = ""
                    refresh_admins_list()
                else:
                    show_snackbar("حدث خطأ أثناء إضافة المسؤول")
            except Exception as ex:
                show_snackbar(f"حدث خطأ: {str(ex)}")

        def remove_admin_action(user_id):
            def confirm_remove(e):
                try:
                    success = remove_admin(user_id)
                    if success:
                        show_snackbar("تمت إزالة المسؤول بنجاح")
                        refresh_admins_list()
                    else:
                        show_snackbar("حدث خطأ أثناء إزالة المسؤول")
                    page.close(dlg)
                except Exception as ex:
                    show_snackbar(f"حدث خطأ: {str(ex)}")
                    page.close(dlg)
            
            dlg = AlertDialog(
                modal=True,
                title=Row([
                    Icon(Icons.WARNING, color=Colors.ORANGE),
                    Container(width=10),
                    Text("تأكيد الإزالة")
                ]),
                content=Column([
                    Text(f"هل أنت متأكد من إزالة صلاحيات المسؤول؟", size=16),
                    Container(height=10),
                    Text(f"معرف المستخدم: {user_id}", 
                        size=14, 
                        weight=FontWeight.BOLD,
                        color=Colors.BLUE_700)
                ], tight=True),
                actions=[
                    TextButton("إلغاء", on_click=lambda e: page.close(dlg)),
                    TextButton(
                        "تأكيد الحذف",
                        on_click=confirm_remove,
                        style=ButtonStyle(color=Colors.RED)
                    ),
                ],
                actions_alignment=MainAxisAlignment.END,
            )
            page.dialog = dlg
            page.open(dlg)


        # تحميل البيانات الأولية
        refresh_admins_list()

        return Container(
            expand=True,
            padding=20,
            alignment=alignment.center,
            content=Column(
                [
                    # العنوان والبحث
                    Row([
                        Text("إدارة المسؤولين", 
                            size=28, 
                            weight=FontWeight.BOLD, 
                            color=Colors.BLUE_700),
                        Container(width=20),
                        search_field
                    ], alignment=MainAxisAlignment.START),
                    
                    Container(height=20),
                    
                    # إحصائيات
                    stats_row,
                    
                    Container(height=20),
                    Divider(),
                    Container(height=10),
                    
                    # نموذج إضافة مسؤول
                    Card(
                        elevation=5,
                        content=Container(
                            padding=20,
                            content=Column([
                                Text("إضافة مسؤول جديد", 
                                    size=20, 
                                    weight=FontWeight.BOLD),
                                Container(height=10),
                                Row([
                                    admin_user_id,
                                    Container(width=20),
                                    admin_username
                                ]),
                                Container(height=20),
                                ElevatedButton(
                                    "إضافة مسؤول",
                                    icon=Icons.PERSON_ADD,
                                    on_click=add_admin_action,
                                    style=ButtonStyle(
                                        bgcolor=Colors.GREEN_600,
                                        color=Colors.WHITE,
                                        padding=20
                                    )
                                )
                            ], horizontal_alignment=CrossAxisAlignment.CENTER)
                        )
                    ),
                    
                    Container(height=20),
                    
                    # قائمة المسؤولين
                    Text("قائمة المسؤولين الحاليين", 
                        size=20, 
                        weight=FontWeight.BOLD),
                    Container(height=10),
                    
                    Container(
                        content=admins_list,
                        height=400,
                        border=border.all(1, Colors.GREY_300),
                        border_radius=10,
                        padding=10
                    ),
                    
                    # تعليمات
                    ExpansionTile(
                        title=Text("تعليمات", weight=FontWeight.BOLD),
                        controls=[
                            ListTile(title=Text("- يمكن للمسؤولين إدارة المنتجات عبر التطبيق والبوت")),
                            ListTile(title=Text("- للحصول على User ID، أرسل /id للبوت")),
                            ListTile(title=Text("- يمكن البحث عن مسؤول بالاسم أو المعرف")),
                            ListTile(title=Text("- انقر على أيقونة ⋮ بجوار المسؤول لمزيد من الخيارات"))
                        ]
                    )
                ],
                scroll=ScrollMode.AUTO,
                horizontal_alignment=CrossAxisAlignment.CENTER,
                alignment=MainAxisAlignment.START,
                spacing=20
            )
        )


    # === الوظائف الرئيسية ===
    def refresh_products():
        products_grid.controls.clear()
        search_term = search_field.value.lower()
        with sqlite3.connect(DB_PATH) as conn:
            products = conn.execute(
                "SELECT id, name, price, quantity, sold, image FROM products"
            ).fetchall()
            
            for product in products:
                pid, name, price, quantity, sold, image = product
                
                if search_term and search_term not in name.lower():
                    continue
                
                # إضافة تحذير إذا كانت الكمية منخفضة
                quantity_warning = None
                if quantity <= 0:
                    quantity_warning = Row([
                        Icon(Icons.WARNING, color=Colors.RED, size=16),
                        Text("إنتهى المنتج", color=Colors.RED, size=12)
                    ], spacing=5)
                elif quantity <= 5:
                    quantity_warning = Row([
                        Icon(Icons.WARNING, color=Colors.ORANGE, size=16),
                        Text(f"كمية قليلة ({quantity})", color=Colors.ORANGE, size=12)
                    ], spacing=5)
                
                quantity_field = TextField(
                    value="1",
                    width=60,
                    keyboard_type=KeyboardType.NUMBER,
                    on_change=lambda e, pid=pid: update_quantity(pid, e.control.value)
                )
                
                def create_buy_callback(product_id, product_name):
                    def callback(e):
                        buy_product(product_id, product_name)
                    return callback
                
                def create_select_callback(product_id, product_price):
                    def callback(e):
                        try:
                            qty = int(quantity_field.value) if quantity_field.value.isdigit() else 1
                            if e.control.value:
                                selected_products[product_id] = (product_price, qty)
                            else:
                                selected_products.pop(product_id, None)
                            update_total_banner()
                        except Exception as ex:
                            pass
                    return callback
                
                product_card = Card(
                    content=Container(
                        content=Column([
                            Image(
                                src=image if image else "default_product.png",
                                width=200,
                                height=150,
                                fit=ImageFit.CONTAIN
                            ),
                            Text(name, size=16, weight=FontWeight.BOLD),
                            Text(f"السعر: {price} درهم", size=14),
                            Text(f"المتاح: {quantity} | المباع: {sold}", size=14),
                            Container(
                                content=Row([
                                    Container(
                                        content=quantity_field,
                                        width=80,
                                        padding=padding.only(right=10),
                                        border_radius=5,
                                        bgcolor=Colors.GREY_100,
                                    ),
                                    ElevatedButton(
                                        "شراء",
                                        icon=Icons.SHOPPING_CART,
                                        on_click=create_buy_callback(pid, name),
                                        style=ButtonStyle(
                                            shape=RoundedRectangleBorder(radius=5),
                                            padding=20,
                                            bgcolor=Colors.BLUE_400,
                                            color=Colors.WHITE
                                        ),
                                        height=40
                                    ),
                                    Container(
                                        content=Checkbox(
                                            label="اختر",
                                            on_change=create_select_callback(pid, price),
                                            fill_color=Colors.BLUE_400
                                        ),
                                        padding=padding.only(left=10)
                                    )
                                ], 
                                alignment=MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=CrossAxisAlignment.CENTER),
                                padding=padding.symmetric(vertical=5),
                                bgcolor=Colors.GREY_50,
                                border_radius=5,
                                width=280
                            )
                        ], 
                        spacing=10, 
                        horizontal_alignment=CrossAxisAlignment.CENTER),
                        padding=15,
                        width=320,
                        height=350
                    ),
                    elevation=5,
                    width=320,
                    height=350,
                    shape=RoundedRectangleBorder(radius=10)
                )
                
                products_grid.controls.append(product_card)
        
        page.update()
    
    def update_quantity(product_id, value):
        try:
            quantity = int(value) if value else 1
            if product_id in selected_products:
                price = selected_products[product_id][0]
                selected_products[product_id] = (price, quantity)
                update_total_banner()
        except ValueError:
            pass
    
    def refresh_edit_products():
        edit_products_grid.controls.clear()
        search_term = edit_search_field.value.lower()
        
        with sqlite3.connect(DB_PATH) as conn:
            products = conn.execute(
                "SELECT id, name, price, quantity, sold, image FROM products"
            ).fetchall()
            
            for product in products:
                pid, name, price, quantity, sold, image = product
                
                if search_term and search_term not in name.lower():
                    continue
                
                def create_edit_callback(product_id):
                    def callback(e):
                        load_product_for_edit(product_id)
                    return callback
                
                def create_delete_callback(product_id, product_name):
                    def callback(e):
                        delete_product(product_id, product_name)
                    return callback
                
                product_card = Card(
                    content=Container(
                        content=Column([
                            Image(
                                src=image if image else "default_product.png",
                                width=200,
                                height=150,
                                fit=ImageFit.CONTAIN
                            ),
                            Text(name, size=16, weight=FontWeight.BOLD),
                            Text(f"السعر: {price} درهم", size=14),
                            Text(f"المتاح: {quantity} | المباع: {sold}", size=14),
                            Container(
                                content=Row([
                                    ElevatedButton(
                                        "تعديل",
                                        icon=Icons.EDIT,
                                        on_click=create_edit_callback(pid),
                                        style=ButtonStyle(
                                            shape=RoundedRectangleBorder(radius=5),
                                            padding=20,
                                            bgcolor=Colors.BLUE_400,
                                            color=Colors.WHITE
                                        ),
                                        height=40
                                    ),
                                    ElevatedButton(
                                        "حذف",
                                        icon=Icons.DELETE,
                                        on_click=create_delete_callback(pid, name),
                                        style=ButtonStyle(
                                            shape=RoundedRectangleBorder(radius=5),
                                            padding=20,
                                            bgcolor=Colors.RED_400,
                                            color=Colors.WHITE
                                        ),
                                        height=40
                                    )
                                ],
                                alignment=MainAxisAlignment.SPACE_EVENLY,
                                spacing=10),
                                padding=padding.symmetric(vertical=10),
                                width=280
                            )
                        ],
                        spacing=10,
                        horizontal_alignment=CrossAxisAlignment.CENTER),
                        padding=15,
                        width=320,
                        height=350
                    ),
                    elevation=5,
                    width=320,
                    height=350,
                    shape=RoundedRectangleBorder(radius=10))
                
                edit_products_grid.controls.append(product_card)
        
        page.update()
    
    def load_product_for_edit(product_id):
        nonlocal edit_product_id, current_view
        edit_product_id = product_id
        
        with sqlite3.connect(DB_PATH) as conn:
            product = conn.execute(
                "SELECT name, price, quantity, sold, image FROM products WHERE id=?",
                (product_id,)
            ).fetchone()
            
            if product:
                name, price, quantity, sold, image = product
                edit_name.value = name
                edit_price.value = str(price)
                edit_quantity.value = str(quantity)
                edit_sold.value = str(sold)
                edit_image_path.value = image if image else "لا توجد صورة"
                
                if image:
                    edit_preview = Image(
                        src=image,
                        width=300,
                        height=300,
                        fit=ImageFit.COVER,
                        border_radius=15
                    )
                else:
                    edit_preview = Column(
                        [
                            Icon(Icons.IMAGE_OUTLINED, size=80, color=Colors.GREY_400),
                            Text("صورة المنتج", size=16, color=Colors.GREY_500)
                        ],
                        alignment=MainAxisAlignment.CENTER,
                        horizontal_alignment=CrossAxisAlignment.CENTER
                    )
                
                current_view = "edit_product"
                page.clean()
                page.add(
                    Row(
                        [
                            create_nav_rail(2),
                            VerticalDivider(width=1),
                            Container(
                                content=edit_product_page,
                                expand=True,
                                padding=20
                            )
                        ],
                        expand=True
                    )
                )
                page.update()

    def delete_product(product_id, product_name):
        def confirm_delete(e):
            try:
                # 1. الحصول على معلومات الصورة أولاً
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT image FROM products WHERE id=?", (product_id,))
                    image_data = cursor.fetchone()
                    
                    if not image_data:
                        show_snackbar("المنتج غير موجود!")
                        page.close(dlg)
                        return

                    image_path = image_data[0]
                    
                    # 2. حذف المنتج من قاعدة البيانات
                    cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
                    rows_deleted = cursor.rowcount
                    conn.commit()  # التأكيد على حفظ التغييرات
                    
                    if rows_deleted == 0:
                        show_snackbar("لم يتم حذف أي منتج!")
                        page.close(dlg)
                        return
                    
                    # 3. حذف الصورة المرتبطة إذا وجدت
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                            # حذف الصورة المصغرة إذا كانت موجودة
                            thumbnail_path = os.path.join(IMAGES_FOLDER, "thumb_" + os.path.basename(image_path))
                            if os.path.exists(thumbnail_path):
                                os.remove(thumbnail_path)
                        except Exception as img_err:
                            pass

                # 4. إرسال إشعار
                message = f"تم حذف المنتج:\n{product_name}"
                threading.Thread(
                    target=lambda: send_telegram_notification(message),
                    daemon=True
                ).start()

                # 5. تحديث الواجهة
                show_snackbar(f"تم حذف {product_name} بنجاح")
                refresh_edit_products()
                
                # 6. إغلاق الحوار
                page.close(dlg)

            except sqlite3.Error as db_err:
                
                show_snackbar(f"خطأ في قاعدة البيانات: {db_err}")
            except Exception as ex:
                
                show_snackbar(f"خطأ غير متوقع: {ex}")
            finally:
                page.update()

        # إنشاء حوار التأكيد
        dlg = AlertDialog(
            modal=True,
            title=Text("تأكيد الحذف", weight=FontWeight.BOLD),
            content=Column([
                Text("سيتم حذف المنتج التالي نهائياً:", size=16),
                Text(product_name, size=18, weight=FontWeight.BOLD, color=Colors.RED_700),
                Text("لا يمكن التراجع عن هذه العملية!", size=14, color=Colors.RED)
            ], tight=True),
            actions=[
                TextButton("إلغاء", on_click=lambda e: page.close(dlg)),
                TextButton(
                    "تأكيد الحذف",
                    on_click=confirm_delete,
                    style=ButtonStyle(color=Colors.RED)
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )

        # فتح الحوار
        page.dialog = dlg
        page.open(dlg)

    def buy_product(product_id, product_name):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                quantity = conn.execute(
                    "SELECT quantity FROM products WHERE id=?",
                    (product_id,)
                ).fetchone()[0]
                
                if quantity <= 0:
                    show_snackbar("الكمية غير متاحة")
                    return
                
                conn.execute(
                    "UPDATE products SET quantity=quantity-1, sold=sold+1 WHERE id=?",
                    (product_id,)
                )
                
                conn.execute(
                    "INSERT INTO sales (product_id, quantity) VALUES (?, 1)",
                    (product_id,)
                )
            
            message = f"تم بيع منتج:\n{product_name}\nالكمية المتبقية: {quantity-1}"
            send_telegram_notification(message)
            
            show_snackbar(f"تم بيع {product_name} بنجاح")
            refresh_products()
        except Exception as e:
            show_snackbar(f"خطأ في تسجيل البيع: {str(e)}")

    def buy_selected_products():
        if not selected_products:
            show_snackbar("لم يتم اختيار أي منتجات")
            return
        
        try:
            sold_out_products = []  # لتخزين المنتجات التي انتهت
            with sqlite3.connect(DB_PATH) as conn:
                # التحقق أولاً من توفر جميع الكميات
                for product_id, (price, quantity) in selected_products.items():
                    available = conn.execute(
                        "SELECT name, quantity FROM products WHERE id=?",
                        (product_id,)
                    ).fetchone()
                    
                    if available[1] < quantity:
                        show_snackbar(f"الكمية غير كافية للمنتج {available[0]}")
                        return
                
                # تنفيذ عمليات البيع
                for product_id, (price, quantity) in selected_products.items():
                    conn.execute(
                        "UPDATE products SET quantity=quantity-?, sold=sold+? WHERE id=?",
                        (quantity, quantity, product_id)
                    )
                    
                    conn.execute(
                        "INSERT INTO sales (product_id, quantity) VALUES (?, ?)",
                        (product_id, quantity)
                    )
                    
                    # التحقق إذا انتهت الكمية
                    remaining = conn.execute(
                        "SELECT name, quantity FROM products WHERE id=?",
                        (product_id,)
                    ).fetchone()
                    
                    if remaining[1] <= 0:
                        sold_out_products.append(remaining[0])
            
            # إرسال إشعارات
            total = sum(price * qty for price, qty in selected_products.values())
            message = f"تم بيع {len(selected_products)} منتجات\nالمجموع: {total} درهم"
            
            if sold_out_products:
                message += "\n\n⚠️ المنتجات التالية انتهت:\n" + "\n".join(sold_out_products)
            
            send_telegram_notification(message)
            
            # تحديث الواجهة
            selected_products.clear()
            update_total_banner()
            show_snackbar("تم تسجيل المبيعات بنجاح")
            refresh_products()
            
        except Exception as e:
            show_snackbar(f"خطأ في تسجيل المبيعات: {str(e)}")

    

    def update_total_banner():
        if selected_products:
            total = sum(price * qty for price, qty in selected_products.values())
            total_price_banner.content.controls[1].value = str(total)
            total_price_banner.visible = True
        else:
            total_price_banner.visible = False
        page.update()

    def show_snackbar(message, is_error=False):
        page.snack_bar = SnackBar(
            content=Text(message, color=Colors.WHITE),
            bgcolor=Colors.RED_700 if is_error else Colors.GREEN_700,
            behavior=SnackBarBehavior.FLOATING,
            elevation=10,
            shape=RoundedRectangleBorder(radius=10),
            show_close_icon=True,
            duration=4000  # 4 ثواني
        )
        page.snack_bar.open = True
        page.update()

    def navigate_to(index):
        nonlocal current_view
        
        # تأكد من أن الصفحة موجودة
        if not page:
            return
            
        # قم بمسح الصفحة الحالية أولاً
        page.clean()
        
        # تهيئة العناصر حسب الفهرس المحدد
        if index == 0:  # المنتجات
            current_view = "products"
            refresh_products()  # تأكد من تهيئة products_page أولاً
            content = products_page
        elif index == 1:  # إضافة منتج
            current_view = "add_product"
            content = add_product_page
        elif index == 2:  # تعديل المنتجات
            current_view = "edit_products"
            refresh_edit_products()  # تأكد من تهيئة edit_page أولاً
            content = edit_page
        elif index == 3:  # إعدادات البوت
            current_view = "bot_settings"
            content = create_bot_settings_page()
        elif index == 4:  # إدارة المسؤولين
            current_view = "admin_management"
            content = create_admin_management_page()
        else:
            return
            
        # تأكد من أن المحتوى ليس None قبل إضافته
        if content is not None:
            page.add(
                Row(
                    [
                        create_nav_rail(index),
                        VerticalDivider(width=1),
                        Container(
                            content=content,
                            expand=True,
                            padding=20
                        )
                    ],
                    expand=True
                )
            )
        else:
            pass

    def start_telegram_bot():
        from telegram import BotCommand
        from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            MessageHandler,
            ContextTypes,
            filters,
            ConversationHandler
        )
        from telegram import Update
        import sqlite3
        import os
        import asyncio
        import threading

        global telegram_bot_thread, telegram_bot_app, telegram_bot_loop

        # حالات المحادثة
        PRODUCT_NAME, PRODUCT_PRICE, PRODUCT_QUANTITY, PRODUCT_IMAGE = range(4)
        EDIT_PRODUCT_ID, EDIT_PRODUCT_DATA = range(4, 6)
        DELETE_PRODUCT_ID = 6

        # تأكد من عدم تشغيل البوت مسبقاً
        if telegram_bot_thread and telegram_bot_thread.is_alive():
            pass
            return
        
        # تحقق من وجود إعدادات البوت
        with sqlite3.connect(SETTINGS_DB_PATH) as conn:
            settings = conn.execute(
                "SELECT bot_token, chat_id FROM telegram_bot ORDER BY id DESC LIMIT 1"
            ).fetchone()
        
        if not settings or not settings[0]:
            pass
            return

        async def download_image(bot, file_id, product_id):
            try:
                os.makedirs(IMAGES_FOLDER, exist_ok=True)
                filename = f"{product_id}.jpg"
                destination = os.path.join(IMAGES_FOLDER, filename)
                
                # الحصول على كائن الملف من file_id
                file = await bot.get_file(file_id)
                await file.download_to_drive(destination)
                
                return destination
            except Exception as e:
                
                return None

        async def run_bot():
            global telegram_bot_app, telegram_bot_loop
            try:
                telegram_bot_loop = asyncio.get_running_loop()
                bot_token = settings[0]

                # متغيرات حالة المنتج المؤقت
                temp_product = {}

                async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    user_id = str(update.effective_user.id)
                    if is_admin(user_id):
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"مرحباً بك في نظام إدارة المنتجات!\nمعرفك: {user_id}\nاستخدم /help لرؤية الأوامر المتاحة"
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text="ليس لديك صلاحية الوصول لهذا البوت. الرجاء التواصل مع المسؤول."
                        )

                async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text="ليس لديك صلاحية الوصول لهذا البوت"
                        )
                        return

                    help_text = """
                    🛍️ أوامر إدارة المتجر:
                    
                    /start - بدء استخدام البوت
                    /help - عرض هذه الرسالة
                    /id - عرض معرفك
                    
                    📦 أوامر المنتجات:
                    /add - إضافة منتج جديد (مع صورة)
                    /quickadd - إضافة منتج سريع (بدون صورة)
                    /list - عرض جميع المنتجات
                    /edit - تعديل منتج
                    /delete - حذف منتج
                    /sales - عرض المبيعات
                    """
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, 
                        text=help_text,
                        parse_mode="Markdown"
                    )

                async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    user_id = update.effective_user.id
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"🔑 معرفك هو:\n`{user_id}`\n\nشارك هذا المعرف مع المسؤول لإضافتك كمسؤول في النظام.",
                        parse_mode="Markdown"
                    )

                async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا الأمر")
                        return ConversationHandler.END
                    
                    await update.message.reply_text("📝 الرجاء إرسال اسم المنتج:")
                    return PRODUCT_NAME

                async def product_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    temp_product['name'] = update.message.text
                    await update.message.reply_text("💰 الرجاء إرسال سعر المنتج:")
                    return PRODUCT_PRICE

                async def product_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    try:
                        temp_product['price'] = float(update.message.text)
                        await update.message.reply_text("🛒 الرجاء إرسال كمية المنتج المتاحة:")
                        return PRODUCT_QUANTITY
                    except ValueError:
                        await update.message.reply_text("❌ السعر يجب أن يكون رقماً! الرجاء إعادة المحاولة:")
                        return PRODUCT_PRICE

                async def product_quantity_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    try:
                        temp_product['quantity'] = int(update.message.text)
                        await update.message.reply_text("📸 الرجاء إرسال صورة المنتج (أو /skip لتخطي إضافة صورة):")
                        return PRODUCT_IMAGE
                    except ValueError:
                        await update.message.reply_text("❌ الكمية يجب أن تكون رقماً صحيحاً! الرجاء إعادة المحاولة:")
                        return PRODUCT_QUANTITY

                async def product_image_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if update.message.photo:
                        try:
                            with sqlite3.connect(DB_PATH) as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)",
                                    (temp_product['name'], temp_product['price'], temp_product['quantity'])
                                )
                                product_id = cursor.lastrowid
                                
                                # الحصول على أعلى دقة صورة متاحة (آخر عنصر في القائمة)
                                photo = update.message.photo[-1]
                                image_path = await download_image(context.bot, photo.file_id, product_id)
                                
                                if image_path:
                                    conn.execute(
                                        "UPDATE products SET image = ? WHERE id = ?",
                                        (image_path, product_id)
                                    )
                            
                            await update.message.reply_text(
                                f"✅ تمت إضافة المنتج بنجاح:\n\n"
                                f"📌 الاسم: {temp_product['name']}\n"
                                f"💰 السعر: {temp_product['price']} درهم\n"
                                f"🛒 الكمية: {temp_product['quantity']}\n"
                                f"🖼️ تم حفظ الصورة"
                            )
                            
                        except Exception as e:
                            await update.message.reply_text(f"❌ حدث خطأ أثناء حفظ المنتج: {str(e)}")
                    else:
                        await update.message.reply_text("❌ لم يتم إرسال صورة صالحة")
                    
                    temp_product.clear()
                    return ConversationHandler.END

                async def skip_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute(
                                "INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)",
                                (temp_product['name'], temp_product['price'], temp_product['quantity'])
                            )
                        
                        await update.message.reply_text(
                            f"✅ تمت إضافة المنتج بنجاح (بدون صورة):\n\n"
                            f"📌 الاسم: {temp_product['name']}\n"
                            f"💰 السعر: {temp_product['price']} درهم\n"
                            f"🛒 الكمية: {temp_product['quantity']}"
                        )
                    
                    except Exception as e:
                        await update.message.reply_text(f"❌ حدث خطأ أثناء حفظ المنتج: {str(e)}")
                    
                    finally:
                        temp_product.clear()
                        return ConversationHandler.END

                async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    temp_product.clear()
                    await update.message.reply_text("❌ تم إلغاء العملية")
                    return ConversationHandler.END

                async def quick_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا الأمر")
                        return

                    await update.message.reply_text(
                        "📝 أرسل بيانات المنتج بالشكل التالي:\n\n`اسم المنتج|السعر|الكمية`\n\nمثال:\n`حذاء رياضي|120.5|15`",
                        parse_mode="Markdown"
                    )

                async def handle_quick_product_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        return

                    try:
                        parts = update.message.text.split('|')
                        if len(parts) != 3:
                            await update.message.reply_text(
                                "❌ صيغة غير صحيحة. استخدم:\n`اسم المنتج|السعر|الكمية`",
                                parse_mode="Markdown"
                            )
                            return

                        name, price, quantity = parts
                        price = float(price.strip())
                        quantity = int(quantity.strip())

                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute(
                                "INSERT INTO products (name, price, quantity) VALUES (?, ?, ?)",
                                (name.strip(), price, quantity)
                            )

                        await update.message.reply_text(
                            f"""✅ تمت إضافة المنتج بنجاح:
                            
    📌 الاسم: {name}
    💰 السعر: {price} درهم
    🛒 الكمية: {quantity}"""
                        )
                        
                        if settings and settings[1]:
                            try:
                                bot = Bot(token=settings[0])
                                await bot.send_message(
                                    chat_id=settings[1],
                                    text=f"تمت إضافة منتج جديد:\n{name}\nالسعر: {price} درهم\nالكمية: {quantity}"
                                )
                            except Exception as e:
                                pass

                    except ValueError:
                        await update.message.reply_text("❌ خطأ في القيم المدخلة! تأكد أن السعر رقم والكمية عدد صحيح")
                    except Exception as e:
                        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")

                async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    with sqlite3.connect(DB_PATH) as conn:
                        products = conn.execute(
                            "SELECT id, name, price, quantity FROM products ORDER BY name"
                        ).fetchall()

                    if not products:
                        await update.message.reply_text("⚠️ لا توجد منتجات مسجلة بعد")
                        return

                    response = "📦 قائمة المنتجات:\n\n"
                    for product in products:
                        response += f"🆔 {product[0]}\n📌 {product[1]}\n💰 {product[2]} درهم\n🛒 المتاح: {product[3]}\n------------------------\n"

                    await update.message.reply_text(response)

                async def edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا الأمر")
                        return ConversationHandler.END
                    
                    await update.message.reply_text(
                        "🆔 الرجاء إرسال ID المنتج الذي تريد تعديله:\n\n"
                        "استخدم /list لرؤية قائمة المنتجات وأرقامها\n"
                        "أو /cancel للإلغاء"
                    )
                    return EDIT_PRODUCT_ID

                async def edit_product_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    try:
                        product_id = int(update.message.text)
                        context.user_data['edit_product_id'] = product_id
                        
                        with sqlite3.connect(DB_PATH) as conn:
                            product = conn.execute(
                                "SELECT name, price, quantity FROM products WHERE id = ?",
                                (product_id,)
                            ).fetchone()
                        
                        if not product:
                            await update.message.reply_text("⚠️ لا يوجد منتج بهذا الرقم")
                            return ConversationHandler.END
                            
                        context.user_data['current_product'] = product
                        await update.message.reply_text(
                            f"📝 المنتج الحالي:\n"
                            f"الاسم: {product[0]}\n"
                            f"السعر: {product[1]}\n"
                            f"الكمية: {product[2]}\n\n"
                            "أرسل البيانات الجديدة بالشكل التالي:\n"
                            "`اسم المنتج|السعر|الكمية`\n\n"
                            "أو /cancel للإلغاء",
                            parse_mode="Markdown"
                        )
                        return EDIT_PRODUCT_DATA

                    except ValueError:
                        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
                        return EDIT_PRODUCT_ID
                    except Exception as e:
                        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
                        return ConversationHandler.END

                async def edit_product_data_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    try:
                        parts = update.message.text.split('|')
                        if len(parts) != 3:
                            await update.message.reply_text(
                                "❌ صيغة غير صحيحة. استخدم:\n`اسم المنتج|السعر|الكمية`",
                                parse_mode="Markdown"
                            )
                            return EDIT_PRODUCT_DATA

                        name, price, quantity = parts
                        product_id = context.user_data['edit_product_id']
                        
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute(
                                "UPDATE products SET name=?, price=?, quantity=? WHERE id=?",
                                (name.strip(), float(price.strip()), int(quantity.strip()), product_id)
                            )
                        
                        await update.message.reply_text(
                            f"✅ تم تحديث المنتج بنجاح:\n\n"
                            f"🆔 الرقم: {product_id}\n"
                            f"📌 الاسم: {name}\n"
                            f"💰 السعر: {price} درهم\n"
                            f"🛒 الكمية: {quantity}"
                        )
                        
                    except ValueError:
                        await update.message.reply_text("❌ خطأ في القيم المدخلة! تأكد أن السعر رقم والكمية عدد صحيح")
                        return EDIT_PRODUCT_DATA
                    except Exception as e:
                        await update.message.reply_text(f"❌ حدث خطأ أثناء التعديل: {str(e)}")
                    finally:
                        context.user_data.clear()
                        return ConversationHandler.END

                async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا الأمر")
                        return ConversationHandler.END
                    
                    await update.message.reply_text(
                        "🗑️ الرجاء إرسال ID المنتج الذي تريد حذفه:\n\n"
                        "استخدم /list لرؤية قائمة المنتجات وأرقامها\n"
                        "أو /cancel للإلغاء"
                    )
                    return DELETE_PRODUCT_ID

                async def delete_product_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    try:
                        product_id = int(update.message.text)
                        
                        with sqlite3.connect(DB_PATH) as conn:
                            product = conn.execute(
                                "SELECT name, image FROM products WHERE id = ?",
                                (product_id,)
                            ).fetchone()
                            
                            if not product:
                                await update.message.reply_text("⚠️ لا يوجد منتج بهذا الرقم")
                                return ConversationHandler.END
                                
                            conn.execute(
                                "DELETE FROM products WHERE id = ?",
                                (product_id,)
                            )
                            
                            if product[1] and os.path.exists(product[1]):
                                try:
                                    os.remove(product[1])
                                except Exception as e:
                                    pass
                        
                        await update.message.reply_text(
                            f"✅ تم حذف المنتج بنجاح:\n{product[0]}"
                        )
                        
                    except ValueError:
                        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
                        return DELETE_PRODUCT_ID
                    except Exception as e:
                        await update.message.reply_text(f"❌ حدث خطأ أثناء الحذف: {str(e)}")
                    finally:
                        return ConversationHandler.END

                async def show_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
                    if not is_admin(str(update.effective_user.id)):
                        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا الأمر")
                        return

                    with sqlite3.connect(DB_PATH) as conn:
                        total_sales = conn.execute(
                            "SELECT COUNT(*) FROM sales"
                        ).fetchone()[0]
                        
                        total_revenue = conn.execute(
                            "SELECT SUM(p.price * s.quantity) FROM sales s JOIN products p ON s.product_id = p.id"
                        ).fetchone()[0] or 0
                        
                        top_products = conn.execute(
                            """SELECT p.name, SUM(s.quantity) as sold 
                            FROM sales s JOIN products p ON s.product_id = p.id 
                            GROUP BY p.name 
                            ORDER BY sold DESC 
                            LIMIT 5"""
                        ).fetchall()

                    response = f"💰 إحصائيات المبيعات:\n\n"
                    response += f"🛒 إجمالي المبيعات: {total_sales}\n"
                    response += f"💵 إجمالي الإيرادات: {total_revenue:.2f} درهم\n\n"
                    response += "🏆 أفضل المنتجات مبيعاً:\n"
                    
                    for i, (name, sold) in enumerate(top_products, 1):
                        response += f"{i}. {name} - {sold} وحدة\n"

                    await update.message.reply_text(response)

                # إعداد معالجات المحادثة
                add_conv_handler = ConversationHandler(
                    entry_points=[CommandHandler('add', add_product_start)],
                    states={
                        PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_name_received)],
                        PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_price_received)],
                        PRODUCT_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_quantity_received)],
                        PRODUCT_IMAGE: [
                            MessageHandler(filters.PHOTO, product_image_received),
                            CommandHandler('skip', skip_image)
                        ],
                    },
                    fallbacks=[CommandHandler('cancel', cancel)],
                )

                edit_conv_handler = ConversationHandler(
                    entry_points=[CommandHandler('edit', edit_product)],
                    states={
                        EDIT_PRODUCT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_id_received)],
                        EDIT_PRODUCT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_data_received)],
                    },
                    fallbacks=[CommandHandler('cancel', cancel)],
                )

                delete_conv_handler = ConversationHandler(
                    entry_points=[CommandHandler('delete', delete_product)],
                    states={
                        DELETE_PRODUCT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_product_id_received)],
                    },
                    fallbacks=[CommandHandler('cancel', cancel)],
                )

                # إعداد التطبيق
                telegram_bot_app = ApplicationBuilder().token(bot_token).build()

                # إضافة المعالجات
                handlers = [
                    add_conv_handler,
                    edit_conv_handler,
                    delete_conv_handler,
                    CommandHandler("start", start),
                    CommandHandler("help", help_command),
                    CommandHandler("id", id_command),
                    CommandHandler("quickadd", quick_add_product),
                    CommandHandler("list", list_products),
                    CommandHandler("sales", show_sales),
                    MessageHandler(filters.TEXT & (~filters.COMMAND), handle_quick_product_input),
                ]
                
                for handler in handlers:
                    telegram_bot_app.add_handler(handler)

                # إعداد قائمة الأوامر
                await telegram_bot_app.bot.set_my_commands([
                    BotCommand("start", "بدء الاستخدام"),
                    BotCommand("help", "عرض الأوامر"),
                    BotCommand("add", "إضافة منتج (مع صورة)"),
                    BotCommand("quickadd", "إضافة منتج سريع"),
                    BotCommand("list", "عرض المنتجات"),
                    BotCommand("delete", "حذف منتج"),
                    BotCommand("edit", "تعديل منتج"),
                    BotCommand("sales", "عرض المبيعات"),
                    BotCommand("id", "عرض معرفك")
                ])

                # تشغيل البوت
                await telegram_bot_app.initialize()
                await telegram_bot_app.start()
                
                
                if settings and settings[1]:
                    try:
                        await telegram_bot_app.bot.send_message(
                            chat_id=settings[1],
                            text="🤖 تم تشغيل بوت إدارة المتجر بنجاح"
                        )
                    except Exception as e:
                        pass
                
                await telegram_bot_app.updater.start_polling()
                await asyncio.Event().wait()

            except Exception as e:
                
                if settings and settings[1]:
                    try:
                        bot = Bot(token=settings[0])
                        await bot.send_message(
                            chat_id=settings[1],
                            text=f"❌ حدث خطأ في تشغيل البوت:\n{str(e)}"
                        )
                    except:
                        pass
            finally:
                telegram_bot_app = None
                telegram_bot_loop = None

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_bot())
            loop.close()

        telegram_bot_thread = threading.Thread(target=run_async, daemon=True)
        telegram_bot_thread.start()
        

    def stop_telegram_bot():
        global telegram_bot_app, telegram_bot_thread, telegram_bot_loop
        
        if telegram_bot_app:
            try:
                asyncio.run_coroutine_threadsafe(telegram_bot_app.stop(), telegram_bot_loop)
                telegram_bot_thread.join(timeout=5)
                telegram_bot_app = None
                telegram_bot_thread = None
                telegram_bot_loop = None
                
                
                with sqlite3.connect(SETTINGS_DB_PATH) as conn:
                    settings = conn.execute(
                        "SELECT bot_token, chat_id FROM telegram_bot ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    
                if settings and settings[0] and settings[1]:
                    try:
                        bot = Bot(token=settings[0])
                        asyncio.run(bot.send_message(
                            chat_id=settings[1],
                            text="🛑 تم إيقاف بوت إدارة المتجر"
                        ))
                    except Exception as e:
                        pass
                        
            except Exception as e:
                pass

    def restart_telegram_bot():
        stop_telegram_bot()
        start_telegram_bot()
    start_telegram_bot()
    navigate_to(0)

app(target=main,assets_dir='assets')
