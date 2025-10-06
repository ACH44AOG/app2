#ده برنامج مراقبة صحة اللابتوب
# بيقيس أداء الجهاز وينبهك لو في مشاكل

# استدعاء المكتبات المطلوبة
import time  # للتحكم في التوقيت والانتظار
import threading  # لتشغيل أكثر من مهمة في نفس الوقت
import json  # لقراءة وكتابة ملفات الإعدادات
import os  # للتعامل مع نظام الملفات والمجلدات
import psutil  # لمراقبة أداء النظام (معالج، ذاكرة، بطارية، إلخ)
import flet as ft  # لإنشاء واجهة المستخدم
from datetime import datetime  # للتعامل مع التواريخ والأوقات

# محاولة استدعاء مكتبة كروت الشاشة لو موجودة
try:
    import GPUtil
except:
    GPUtil = None  # لو مش موجودة خليها فاضية

# ملف الإعدادات
CONFIG_FILE = "assets/config_pro.json"

# الإعدادات الأساسية الافتراضية
DEFAULT_CONFIG = {
    "cpu_alert": 85,  # إنذار عند وصول المعالج لـ85%
    "ram_alert": 85,  # إنذار عند وصول الذاكرة لـ85%
    "battery_alert": 15,  # إنذار عند وصول البطارية لـ15%
    "temp_alert": 85,  # إنذار عند وصول درجة الحرارة لـ85
    "poll_interval": 0.5,  # سرعة التحديث (كل نصف ثانية)
    "auto_start": True,  # التشغيل التلقائي مع الويندوز
    "enable_gpu": True,  # تفعيل مراقبة كرت الشاشة
    "enable_wifi": True,  # تفعيل مراقبة الشبكة
    "show_alerts": True,  # عرض التنبيهات
    "system_notifications": True  # الإشعارات في شريط المهام
}

# دالة لتحميل الإعدادات من الملف
def load_config():
    # إنشاء مجلد assets إذا لم يكن موجوداً
    assets_dir = os.path.dirname(CONFIG_FILE)
    if assets_dir and not os.path.exists(assets_dir):
        os.makedirs(assets_dir)
    
    # شوف لو ملف الإعدادات موجود
    if os.path.exists(CONFIG_FILE):
        try:
            # افتح الملف واقرأ الإعدادات
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                # تأكد من وجود كل الإعدادات الأساسية
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value  # أضف الإعداد الناقص
                return config
        except:
            # لو في خطأ ارجع للإعدادات الأساسية
            return DEFAULT_CONFIG.copy()
    # لو الملف مش موجود ارجع للإعدادات الأساسية
    return DEFAULT_CONFIG.copy()

# دالة لحفظ الإعدادات في الملف
def save_config(cfg):
    try:
        # إنشاء مجلد assets إذا لم يكن موجوداً
        assets_dir = os.path.dirname(CONFIG_FILE)
        if assets_dir and not os.path.exists(assets_dir):
            os.makedirs(assets_dir)
            
        # افتح الملف واكتب الإعدادات
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        return True  # نجح الحفظ
    except:
        return False  # فشل الحفظ
# دالة لقياس درجة حرارة الجهاز في الويندوز
def get_temperature_windows():
    """الحصول على درجة الحرارة في Windows بشكل آمن"""
    # الطريقة الأولى: استخدام OpenHardwareMonitor
    try:
        import wmi
        w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        sensors = w.Sensor()
        for sensor in sensors:
            if sensor.SensorType == 'Temperature' and sensor.Value:
                return float(sensor.Value)
    except:
        pass

    # الطريقة الثانية: استخدام PowerShell
    try:
        import subprocess
        # أمر PowerShell لقياس الحرارة
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-WmiObject -Namespace 'root\\WMI' -Class MSAcpi_ThermalZoneTemperature | Select-Object -ExpandProperty CurrentTemperature"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            temp_raw = float(result.stdout.strip())
            # تحويل القراءة لدرجة مئوية
            if temp_raw > 1000:  # لو كانت كبيرة، تحويل من 0.1 كلفن
                return temp_raw / 10.0 - 273.15
            else:  # لو كانت صغيرة، غالبًا بالـ 0.1°C
                return temp_raw / 10.0
    except:
        pass

    # الطريقة الثالثة: استخدام WMIC
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "path", "Win32_PerfFormattedData_Counters_ThermalZoneInformation", "get", "Temperature"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.isdigit():
                    temp_raw = float(line)
                    if temp_raw > 1000:  # كلفن ×10
                        return temp_raw / 10.0 - 273.15
                    else:  # مئوي ×10
                        return temp_raw / 10.0
    except:
        pass

    return None  # لو كل الطرق فشلت

# دالة محسنة لقياس درجة الحرارة باستخدام كل الطرق
def get_reliable_temperature():
    temps = []  # قائمة لتخزين كل القراءات

    # 1️⃣ الطريقة الأولى: OpenHardwareMonitor
    try:
        import wmi
        w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        sensors = w.Sensor()
        for sensor in sensors:
            if sensor.SensorType == 'Temperature' and sensor.Value:
                val = float(sensor.Value)
                if 0 < val < 120:  # شوف لو القيمة منطقية
                    temps.append(val)
    except:
        pass

    # 2️⃣ الطريقة الثانية: PowerShell MSAcpi
    try:
        import subprocess
        cmd = [
            "powershell", "-Command",
            "Get-CimInstance -Namespace root\\WMI -ClassName MSAcpi_ThermalZoneTemperature | Select-Object -ExpandProperty CurrentTemperature"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                raw = float(line.strip())
                if raw > 1000:  # 0.1 K
                    val = raw / 10.0 - 273.15
                else:  # 0.1 °C
                    val = raw / 10.0
                if 0 < val < 120:
                    temps.append(val)
    except:
        pass

    # 3️⃣ الطريقة الثالثة: WMIC (Windows)
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "path", "Win32_PerfFormattedData_Counters_ThermalZoneInformation", "get", "Temperature"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line.isdigit():
                    raw = float(line)
                    val = (raw / 10.0 - 273.15) if raw > 1000 else raw / 10.0
                    if 0 < val < 120:
                        temps.append(val)
    except:
        pass

    # 4️⃣ الطريقة الرابعة: psutil (Linux/Mac + Windows حديث)
    try:
        import psutil
        if hasattr(psutil, 'sensors_temperatures'):
            st = psutil.sensors_temperatures()
            for entries in st.values():
                for entry in entries:
                    if hasattr(entry, 'current') and entry.current and 0 < entry.current < 120:
                        temps.append(entry.current)
    except:
        pass

    # خد أعلى قراءة منطقية
    if temps:
        return max(temps)
    return None  # لو مفيش قراءات

# دالة سريعة لمراقبة كرت الشاشة
def get_fast_gpu_info():
    """نسخة سريعة لـ GPU"""
    try:
        # جرب استخدام مكتبة GPUtil أولاً
        if GPUtil:
            gpus = GPUtil.getGPUs()
            if gpus:
                g = gpus[0]
                return {
                    "name": g.name,  # اسم كرت الشاشة
                    "load": round(g.load * 100, 1) if g.load else 0,  # نسبة الاستخدام
                    "temperature": g.temperature,  # درجة الحرارة
                    "memory": "N/A"  # الذاكرة
                }
        
        # جرب استخدام nvidia-smi لـ NVIDIA
        try:
            import subprocess
            result = subprocess.run([
                "nvidia-smi", 
                "--query-gpu=name,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits"
            ], capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                data = result.stdout.strip().split(', ')
                if len(data) >= 3:
                    return {
                        "name": data[0],
                        "load": float(data[1]) if data[1] else 0,
                        "temperature": float(data[2]) if data[2] else None,
                        "memory": "N/A"
                    }
        except:
            pass
            
    except Exception as e:
        print(f"Fast GPU info error: {e}")
    return {"name": "N/A", "load": None, "temperature": None, "memory": "N/A"}

# متغيرات عالمية لتتبع إحصائيات الشبكة
network_stats = {
    "prev_bytes_sent": 0,  # آخر عدد بايتات مرسلة
    "prev_bytes_recv": 0,  # آخر عدد بايتات مستلمة
    "last_time": time.time(),  # آخر وقت تحديث
    "sent_speed": 0,  # سرعة الإرسال الحالية
    "recv_speed": 0   # سرعة الاستقبال الحالية
}

# دالة لجلب معلومات الشبكة
def get_network_info():
    try:
        addrs = psutil.net_if_addrs()  # عناوين الشبكة
        stats = psutil.net_if_stats()  # إحصائيات الشبكة
        net_io = psutil.net_io_counters()  # إحصائيات الإرسال والاستقبال
        
        # حساب سرعة الشبكة
        current_time = time.time()
        time_diff = current_time - network_stats["last_time"]
        
        if time_diff > 0:
            # حساب الفرق في البايتات المرسلة والمستلمة
            bytes_sent_diff = net_io.bytes_sent - network_stats["prev_bytes_sent"]
            bytes_recv_diff = net_io.bytes_recv - network_stats["prev_bytes_recv"]
            
            # حساب السرعة بالكيلوبايت في الثانية
            network_stats["sent_speed"] = bytes_sent_diff / time_diff / 1024
            network_stats["recv_speed"] = bytes_recv_diff / time_diff / 1024
            
            # تحديث القيم السابقة
            network_stats["prev_bytes_sent"] = net_io.bytes_sent
            network_stats["prev_bytes_recv"] = net_io.bytes_recv
            network_stats["last_time"] = current_time
        
        # البحث عن واجهة الشبكة النشطة
        active_interface = None
        for ifname in addrs:
            s = stats.get(ifname)
            if s and s.isup:  # لو الشبكة شغالة
                for addr in addrs[ifname]:
                    if addr.family == 2 and not addr.address.startswith("127."):
                        active_interface = ifname
                        break
                if active_interface:
                    break
        
        # تجميع معلومات الشبكة
        if active_interface:
            s = stats[active_interface]
            return {
                "interface": active_interface,  # اسم واجهة الشبكة
                "ip": next((addr.address for addr in addrs[active_interface] if addr.family == 2 and not addr.address.startswith("127.")), "N/A"),  # العنوان IP
                "speed": f"{s.speed}Mbps",  # سرعة الشبكة
                "status": "Connected",  # حالة الاتصال
                "upload": network_stats["sent_speed"],  # سرعة الرفع
                "download": network_stats["recv_speed"]  # سرعة التحميل
            }
    except Exception as e:
        print(f"Network info error: {e}")
    
    # لو في خطأ ارجع قيم افتراضية
    return {
        "interface": "N/A", 
        "ip": "N/A", 
        "speed": "N/A", 
        "status": "Disconnected",
        "upload": 0,
        "download": 0
    }

# دالة لتنسيق عرض سرعة الشبكة
def format_speed(speed):
    if speed >= 1024:
        return f"{speed/1024:.1f} MB/s"  # ميغابايت في الثانية
    else:
        return f"{speed:.1f} KB/s"  # كيلوبايت في الثانية

# دالة لعرض إشعارات النظام
def show_system_notification(title, message):
    """إشعارات النظام باستخدام PowerShell فقط"""
    try:
        import subprocess
        # أمر PowerShell لعمل إشعار
        ps_command = f'''
        Add-Type -AssemblyName System.Windows.Forms
        $notification = New-Object System.Windows.Forms.NotifyIcon
        $notification.Icon = [System.Drawing.SystemIcons]::Information
        $notification.BalloonTipIcon = "Warning"
        $notification.BalloonTipTitle = "{title}"
        $notification.BalloonTipText = "{message}"
        $notification.Visible = $true
        $notification.ShowBalloonTip(3000)
        Start-Sleep -Seconds 3
        $notification.Dispose()
        '''
        subprocess.Popen(["powershell", "-Command", ps_command], shell=False)
    except Exception as e:
        print(f"Notification error: {e}")

# كلاس لإدارة الإشعارات في شريط المهام
class SystemTray:
    def __init__(self, page):
        self.page = page  # صفحة البرنامج
        self.alert_history = []  # قائمة لتخزين تاريخ التنبيهات
        self.last_alert_time = {}  # لتتبع وقت آخر تنبيه

    # دالة لعرض التنبيهات
    def show_alert(self, title, message, alert_type="system"):
        key = f"{title}_{message}"  # مفتاح فريد لكل تنبيه
        now = time.time()  # الوقت الحالي
        
        # منع التكرار - لا تعرض نفس التنبيه قبل 30 ثانية
        if key in self.last_alert_time and now - self.last_alert_time[key] < 30:
            return
        
        # حفظ وقت التنبيه
        self.last_alert_time[key] = now
        # إضافة التنبيه للتاريخ
        self.alert_history.append((title, message, datetime.now().strftime("%H:%M:%S")))
        # الحفاظ على آخر 50 تنبيه فقط
        if len(self.alert_history) > 50:
            self.alert_history.pop(0)
        
        # عرض إشعار النظام لو مطلوب
        if alert_type == "system":
            show_system_notification(title, message)


# دالة الرئيسية للبرنامج - كل حاجة بتبدأ من هنا
def main(page: ft.Page):
    # تحميل الإعدادات من الملف
    cfg = load_config()
    # إنشاء كائن للإشعارات في شريط المهام
    tray = SystemTray(page)

    # إعدادات النافذة الرئيسية
    page.title = "System Health Monitor"  # عنوان البرنامج
    page.window.width = 800  # عرض النافذة
    page.window.height = 770  # ارتفاع النافذة
    page.window.resizable = False
    page.padding = 20  # المسافات الداخلية
    page.theme_mode = ft.ThemeMode.LIGHT  # الوضع الفاتح
    page.bgcolor = ft.Colors.GREY_50  # لون خلفية فاتح

    # عناصر الواجهة للنصوص المعروضة
    cpu_text = ft.Text("--", size=20, weight=ft.FontWeight.BOLD)  # نص عرض استخدام المعالج
    ram_text = ft.Text("--", size=20, weight=ft.FontWeight.BOLD)  # نص عرض استخدام الذاكرة
    batt_text = ft.Text("--", size=20, weight=ft.FontWeight.BOLD)  # نص عرض مستوى البطارية
    temp_text = ft.Text("--", size=20, weight=ft.FontWeight.BOLD)  # نص عرض درجة الحرارة
    gpu_text = ft.Text("--", size=16, weight=ft.FontWeight.BOLD)  # نص عرض معلومات كرت الشاشة
    net_text = ft.Text("--", size=16, weight=ft.FontWeight.BOLD)  # نص عرض معلومات الشبكة
    status_text = ft.Text("🟢 Monitoring Active", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN)  # نص حالة المراقبة
    
    # أشرطة التقدم لعرض الاستخدام بشكل مرئي
    cpu_pb = ft.ProgressBar(width=250, height=20, color=ft.Colors.BLUE_700)  # شريط استخدام المعالج
    ram_pb = ft.ProgressBar(width=250, height=20, color=ft.Colors.GREEN_700)  # شريط استخدام الذاكرة
    batt_pb = ft.ProgressBar(width=250, height=20, color=ft.Colors.ORANGE_700)  # شريط مستوى البطارية

    # حالة المراقبة - علشان نقدر نوقفها لما نريد
    monitor_state = {"running": True}

    # نافذة التنبيهات اللي بتظهر لما يكون في مشكلة
    alert_dialog = ft.AlertDialog(
        modal=True,  # لازم تغلقها عشان تكمل
        title=ft.Text("System Alert"),  # عنوان التنبيه
        content=ft.Text(""),  # محتوى التنبيه (بيتحدد حسب المشكلة)
        actions=[ft.TextButton("OK", on_click=lambda e: page.close(alert_dialog))]  # زر الإقرار
    )

    # دالة لعرض نافذة التنبيه
    def show_alert_dialog(title, msg):
        alert_dialog.title = ft.Text(title, weight=ft.FontWeight.BOLD, color=ft.Colors.RED)  # عنوان التنبيه باللون الأحمر
        alert_dialog.content = ft.Text(msg, size=16)  # رسالة التنبيه
        page.open(alert_dialog)  # افتح النافذة

    # دالة لإنشاء كروت العرض (البطاقات اللي فيها المعلومات)
    def create_metric_card(title, value_widget, pb_widget=None, color=ft.Colors.BLUE, icon=ft.Icons.MONITOR):
        # محتوى البطاقة: أيقونة + عنوان + قيمة + شريط تقدم (لو موجود)
        content = [
            ft.Row([ft.Icon(icon, size=24, color=color), ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=color)]),  # الصف العلوي (أيقونة وعنوان)
            value_widget,  # القيمة (النص)
        ]
        if pb_widget:  # لو فيه شريط تقدم أضفه
            content.append(pb_widget)
        return ft.Card(  # إرجاع البطاقة كاملة
            elevation=8,  # ظل للبطاقة
            content=ft.Container(
                ft.Column(content, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),  # محتوى عمودي
                padding=20, width=280, border_radius=12  # إعدادات الحاوية
            )
        )

    # دالة للتحقق من وجود مشاكل وتنبيه المستخدم
    def check_alerts(cpu, ram, batt, temp, gpu_load):
        if not cfg.get("show_alerts", True):  # لو التنبيهات متعطلة اخرج
            return

        # تنبيه استخدام المعالج العالي
        if cpu >= cfg["cpu_alert"]:
            msg = f"CPU usage is high ({cpu:.1f}%)"  # رسالة التنبيه
            if cfg.get("system_notifications", True):  # لو الإشعارات مفعلة
                tray.show_alert("🚨 CPU Alert", msg, "system")  # إشعار في شريط المهام
            show_alert_dialog("CPU Alert", msg)  # نافذة تنبيه

        # تنبيه استخدام الذاكرة العالي
        if ram >= cfg["ram_alert"]:
            msg = f"RAM usage is high ({ram:.1f}%)"
            if cfg.get("system_notifications", True):
                tray.show_alert("🚨 RAM Alert", msg, "system")
            show_alert_dialog("RAM Alert", msg)

        # تنبيه البطارية المنخفضة
        if batt and batt <= cfg["battery_alert"]:
            msg = f"Battery is low ({batt:.0f}%) - Consider charging"  # نصيحة بالشحن
            if cfg.get("system_notifications", True):
                tray.show_alert("🔋 Battery Alert", msg, "system")
            show_alert_dialog("Battery Alert", msg)

        # تنبيه درجة الحرارة العالية
        if temp and temp >= cfg["temp_alert"]:
            msg = f"Temperature is high ({temp:.1f}°C) - System may throttle"  # تحذير من بطء النظام
            if cfg.get("system_notifications", True):
                tray.show_alert("🌡️ Temperature Alert", msg, "system")
            show_alert_dialog("Temperature Alert", msg)

        # تنبيف استخدام كرت الشاشة العالي
        if gpu_load and gpu_load >= 90:  # قيمة ثابتة لكرت الشاشة
            msg = f"GPU load is high ({gpu_load:.1f}%)"
            if cfg.get("system_notifications", True):
                tray.show_alert("🎮 GPU Alert", msg, "system")
            show_alert_dialog("GPU Alert", msg)

    # دالة لتحديث واجهة المستخدم بالبيانات الجديدة
    def update_ui(cpu, ram, batt_percent, temp, gpu, net):
        try:
            # تحديث بيانات المعالج
            cpu_text.value = f"{cpu:.1f}%"  # النص
            cpu_pb.value = cpu / 100  # شريط التقدم (من 0 إلى 1)
            
            # تحديث بيانات الذاكرة
            ram_text.value = f"{ram:.1f}%"
            ram_pb.value = ram / 100
            
            # تحديث بيانات البطارية
            batt_text.value = f"{batt_percent:.0f}%" if batt_percent else "N/A"  # لو مفيش بطارية
            batt_pb.value = (batt_percent or 0) / 100
            
            # تحديث بيانات درجة الحرارة
            if temp:
                temp_text.value = f"{temp:.1f}°C"
                temp_text.color = ft.Colors.RED_700  # لون أحمر للتحذير
            else:
                temp_text.value = "Not Available"  # لو مفيش قياس
                temp_text.color = ft.Colors.GREY_500  # لون رمادي
            
            # تحديث بيانات كرت الشاشة
            gpu_name = gpu.get('name', 'N/A')  # اسم كرت الشاشة
            gpu_load = gpu.get('load')  # نسبة الاستخدام
            gpu_temp = gpu.get('temperature')  # درجة الحرارة
            
            gpu_display = f"{gpu_name}\n"  # بناء النص المعروض
            if gpu_load is not None:
                gpu_display += f"Load: {gpu_load}%\n"
            else:
                gpu_display += "Load: N/A\n"
                
            if gpu_temp:
                gpu_display += f"Temp: {gpu_temp}°C"
            else:
                gpu_display += "Temp: N/A"
                
            gpu_text.value = gpu_display  # تعيين النص النهائي
            
            # تحديث بيانات الشبكة
            if net.get('status') == 'Connected':  # لو متصل بالشبكة
                net_info = f"{net.get('interface', 'N/A')}\n"  # واجهة الشبكة
                net_info += f"IP: {net.get('ip', 'N/A')}\n"  # العنوان
                net_info += f"▲ {format_speed(net.get('upload', 0))}\n"  # سرعة الرفع
                net_info += f"▼ {format_speed(net.get('download', 0))}"  # سرعة التحميل
            else:
                net_info = "Disconnected"  # غير متصل
            net_text.value = net_info
            
            # تحديث حالة المراقبة
            status_text.value = "🟢 Monitoring Active"
            status_text.color = ft.Colors.GREEN
            
            page.update()  # حدث الواجهة
        except Exception as e:
            print(f"UI update error: {e}")  # طباعة الخطأ لو حصل

    # الدالة الرئيسية للمراقبة - بتشتغل في الخلفية
    def monitor_loop():
        while monitor_state["running"]:  # استمر طالما المراقبة شغالة
            try:
                # جمع البيانات من النظام
                cpu = psutil.cpu_percent(interval=0.1)  # استخدام المعالج (أسرع قياس)
                ram = psutil.virtual_memory().percent  # استخدام الذاكرة
                
                battery = psutil.sensors_battery()  # معلومات البطارية
                batt_percent = battery.percent if battery else None  # نسبة الشحن
                
                # الحصول على البيانات الأخرى
                temp = get_reliable_temperature()  # درجة الحرارة
                gpu = get_fast_gpu_info() if cfg.get("enable_gpu", True) else {}  # كرت الشاشة (لو مفعل)
                net = get_network_info() if cfg.get("enable_wifi", True) else {}  # الشبكة (لو مفعلة)

                # تحديث الواجهة بالبيانات الجديدة
                update_ui(cpu, ram, batt_percent, temp, gpu, net)
                # التحقق من المشاكل وإظهار التنبيهات
                check_alerts(cpu, ram, batt_percent, temp, gpu.get("load"))
                
                # الانتظار قبل القياس التالي حسب الإعدادات
                time.sleep(cfg.get("poll_interval", 0.5))
                
            except Exception as e:
                print(f"Monitoring error: {e}")  # طباعة الخطأ
                try:
                    # تحديث حالة المراقبة لخطأ
                    status_text.value = "🔴 Monitoring Error"
                    status_text.color = ft.Colors.RED
                    page.update()
                except:
                    pass
                time.sleep(1)  # انتظر ثانية قبل المحاولة again

    # إنشاء كروت العرض للمقاييس المختلفة
    cpu_card = create_metric_card("CPU Usage", cpu_text, cpu_pb, ft.Colors.BLUE_700, ft.Icons.SPEED)  # بطاقة المعالج
    ram_card = create_metric_card("RAM Usage", ram_text, ram_pb, ft.Colors.GREEN_700, ft.Icons.MEMORY)  # بطاقة الذاكرة
    batt_card = create_metric_card("Battery", batt_text, batt_pb, ft.Colors.ORANGE_700, ft.Icons.BATTERY_CHARGING_FULL)  # بطاقة البطارية
    temp_card = create_metric_card("Temperature", temp_text, None, ft.Colors.RED_700, ft.Icons.THERMOSTAT)  # بطاقة الحرارة
    gpu_card = create_metric_card("GPU", gpu_text, None, ft.Colors.PURPLE_700, ft.Icons.GAMEPAD)  # بطاقة كرت الشاشة
    net_card = create_metric_card("Network", net_text, None, ft.Colors.TEAL_700, ft.Icons.WIFI)  # بطاقة الشبكة

    # تبويب لوحة التحكم الرئيسية
    dashboard_tab = ft.Tab(
        text="Dashboard",  # اسم التبويب
        content=ft.Container(  # محتوى التبويب
            ft.Column([  # ترتيب عمودي
                # الهيدر العلوي
                ft.Container(
                    ft.Row([  # ترتيب أفقي
                        ft.Icon(ft.Icons.MONITOR_HEART, size=35, color=ft.Colors.BLUE_700),  # أيقونة البرنامج
                        ft.Column([  # عمود للنصوص
                            ft.Text("System Health Monitor", size=25, weight=ft.FontWeight.BOLD),  # عنوان
                            ft.Text("Real-time system monitoring", size=10, color=ft.Colors.GREY_600),  # وصف
                        ])
                    ]),
                    padding=15,  # مسافات داخلية
                    bgcolor=ft.Colors.BLUE_50,  # لون خلفية أزرق فاتح
                    border_radius=15  # زوايا دائرية
                ),
                # صف أول: المعالج والذاكرة
                ft.Row([cpu_card, ram_card], alignment=ft.MainAxisAlignment.CENTER),
                # صف ثاني: البطارية ودرجة الحرارة
                ft.Row([batt_card, temp_card], alignment=ft.MainAxisAlignment.CENTER),
                # صف ثالث: كرت الشاشة والشبكة
                ft.Row([gpu_card, net_card], alignment=ft.MainAxisAlignment.CENTER),
                # حالة المراقبة في الأسفل
                ft.Container(status_text, alignment=ft.alignment.center, padding=20)
            ])
        )
    )

    # عناصر الإعدادات للنصوص المعروضة
    cpu_alert_text = ft.Text(f"{cfg.get('cpu_alert', 85)}%", size=16, color=ft.Colors.BLUE_700)  # نص تنبيه المعالج
    ram_alert_text = ft.Text(f"{cfg.get('ram_alert', 85)}%", size=16, color=ft.Colors.GREEN_700)  # نص تنبيه الذاكرة
    batt_alert_text = ft.Text(f"{cfg.get('battery_alert', 15)}%", size=16, color=ft.Colors.ORANGE_700)  # نص تنبيه البطارية
    temp_alert_text = ft.Text(f"{cfg.get('temp_alert', 85)}°C", size=16, color=ft.Colors.RED_700)  # نص تنبيه الحرارة

    # دالة لتحديث الإعدادات
    def update_setting(key, value, text_widget=None):
        cfg[key] = value  # تحديث القيمة في الإعدادات
        if text_widget:  # لو فيه نص معروض يتبعه
            text_widget.value = f"{value}%" if key != 'temp_alert' else f"{value}°C"  # تحديث النص
        page.update()  # حدث الواجهة

    # دالة لحفظ كل الإعدادات
    def save_all_settings(e):
        if save_config(cfg):  # حاول حفظ الإعدادات
            show_system_notification("Settings Saved", "All configuration settings have been saved successfully.")  # إشعار
            show_alert_dialog("Success", "Settings saved successfully!")  # نافذة تأكيد

    # دالة لإنشاء عناصر التحكم في الإعدادات
    def create_setting_slider(label, key, min_v, max_v, color, unit, text_widget):
        return ft.Container(
            ft.Column([
                # صف يحتوي على التسمية والقيمة الحالية
                ft.Row([
                    ft.Text(label, size=16, weight=ft.FontWeight.BOLD, color=color),  # تسمية الإعداد
                    text_widget  # القيمة الحالية
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),  # مسافة بينهم
                # شريط التمرير لتعديل القيمة
                ft.Slider(
                    min=min_v, max=max_v, divisions=int(max_v - min_v),  # الحد الأدنى والأقصى
                    value=cfg.get(key, DEFAULT_CONFIG[key]),  # القيمة الحالية
                    active_color=color,  # لون الشريط
                    on_change=lambda e: update_setting(key, e.control.value, text_widget)  # حدث التغيير
                ),
            ], spacing=5),  # مسافة بين العناصر
            padding=10, border_radius=10, bgcolor=ft.Colors.GREY_100, margin=ft.margin.only(bottom=10)  # إعدادات التنسيق
        )

    # تبويب الإعدادات والتنبيهات
    settings_tab = ft.Tab(
        text="Settings & Alerts",  # اسم التبويب
        content=ft.Container(
            ft.Column([
                ft.Text("Alert Settings", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),  # عنوان القسم
                ft.Divider(),  # خط فاصل
                # شرائط التحكم في حدود التنبيهات
                create_setting_slider("CPU Alert Threshold", "cpu_alert", 50, 100, ft.Colors.BLUE_700, "%", cpu_alert_text),
                create_setting_slider("RAM Alert Threshold", "ram_alert", 50, 100, ft.Colors.GREEN_700, "%", ram_alert_text),
                create_setting_slider("Battery Alert", "battery_alert", 5, 80, ft.Colors.ORANGE_700, "%", batt_alert_text),
                create_setting_slider("Temperature Alert", "temp_alert", 60, 95, ft.Colors.RED_700, "°C", temp_alert_text),
                ft.Divider(),  # خط فاصل
                # مفاتيح تبديل الخيارات
                ft.Row([
                    ft.Switch(label="Enable Alerts", value=cfg.get("show_alerts", True),  # تفعيل/تعطيل التنبيهات
                              on_change=lambda e: update_setting("show_alerts", e.control.value)),
                    ft.Switch(label="System Notifications", value=cfg.get("system_notifications", True),  # إشعارات النظام
                              on_change=lambda e: update_setting("system_notifications", e.control.value)),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Row([
                    ft.Switch(label="Monitor GPU", value=cfg.get("enable_gpu", True),  # مراقبة كرت الشاشة
                              on_change=lambda e: update_setting("enable_gpu", e.control.value)),
                    ft.Switch(label="Monitor Network", value=cfg.get("enable_wifi", True),  # مراقبة الشبكة
                              on_change=lambda e: update_setting("enable_wifi", e.control.value)),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                # زر حفظ الإعدادات
                ft.Container(
                    ft.ElevatedButton(
                        "Save Config",  # نص الزر
                        on_click=save_all_settings,  # حدث الضغط
                        bgcolor=ft.Colors.BLUE_700,  # لون خلفية أزرق
                        color="white",  # لون النص أبيض
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12))  # زوايا دائرية
                    ),
                    alignment=ft.alignment.center,  # توسيط الزر
                    padding=20  # مسافات حول الزر
                )
            ], scroll=ft.ScrollMode.ADAPTIVE)  # إمكانية التمرير لو المحتوى طويل
        )
    )

    # إنشاء التبويبات وإضافتها للصفحة
    tabs = ft.Tabs(selected_index=0, tabs=[dashboard_tab, settings_tab], expand=True)
    page.add(tabs)

    # بدء المراقبة في خيط منفصل علشان ما توقف الواجهة
    threading.Thread(target=monitor_loop, daemon=True).start()

# تشغيل البرنامج لما ننفذ الملف مباشر
if __name__ == "__main__":
    ft.app(target=main)
