import requests
from flask import Flask, render_template, request, redirect, url_for, session
from config import API_BASE_URL
import qrcode
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your-secret-key-change-this"

# Добавь этот маршрут для проверки соединения
@app.route("/check-api")
def check_api():
    """Проверка, доступен ли API напарницы"""
    try:
        response = requests.get(f"{API_BASE_URL}/auth/token/", timeout=3)
        return f"API доступен! Статус: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return f"❌ API НЕ ДОСТУПЕН по адресу {API_BASE_URL}"
    except Exception as e:
        return f"Ошибка: {e}"



# Разрешенные расширения для фото
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- ГЛАВНАЯ ----------
@app.route("/")
def home():
    return render_template("home.html")

# ---------- ВХОД ----------
@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    
    try:
        response = requests.post(f"{API_BASE_URL}/auth/token/", json={
            "username": username,
            "password": password
        }, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            session["access_token"] = data["access"]
            session["refresh_token"] = data["refresh"]
            
            headers = {"Authorization": f"Bearer {data['access']}"}
            user_response = requests.get(f"{API_BASE_URL}/auth/me/", headers=headers, timeout=5)
            
            if user_response.status_code == 200:
                user = user_response.json()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                session["username"] = user["username"]
                
                if user["role"] == "admin":
                    return redirect(url_for("admin_events"))
                elif user["role"] == "teacher":
                    return redirect(url_for("teacher_events"))
                elif user["role"] == "student":
                    return redirect(url_for("student_events"))
        
        return render_template("home.html", error="Неверные логин или пароль")
    
    except requests.exceptions.ConnectionError:
        return render_template("home.html", error="Ошибка: бэкенд не запущен")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---------- ПРЕПОДАВАТЕЛЬ ----------
@app.route("/teacher/events")
def teacher_events():
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.get(f"{API_BASE_URL}/events/", headers=headers, timeout=5)
        
        if response.status_code == 200:
            all_events = response.json().get("results", [])
            user_id = session.get("user_id")
            
            # Отладка
            print(f"👤 Текущий преподаватель ID: {user_id}")
            print(f"📋 Всего мероприятий в API: {len(all_events)}")
            for e in all_events:
                teacher_id = e.get("created_by", {}).get("id") if e.get("created_by") else None
                print(f"  - {e.get('title')}: создатель ID={teacher_id}")
            
            # Фильтруем
            events = [e for e in all_events if e.get("created_by", {}).get("id") == user_id]
            print(f"✅ Отфильтровано мероприятий: {len(events)}")
        else:
            events = []
    except Exception as e:
        print(f"Ошибка: {e}")
        events = []
    
    return render_template("teacher_events.html", events=events)

@app.route("/teacher/create", methods=["GET", "POST"])
def teacher_create():
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    if request.method == "POST":
        headers = {
            "Authorization": f"Bearer {session['access_token']}",
            "Content-Type": "application/json"
        }
        
        # Даты
        start_at = request.form.get("start_at")
        registration_deadline = request.form.get("registration_deadline")
        
        if start_at and len(start_at) == 16:
            start_at = start_at + ":00"
        if registration_deadline and len(registration_deadline) == 16:
            registration_deadline = registration_deadline + ":00"
        
        # ========== СОБИРАЕМ ОБЯЗАТЕЛЬНЫХ СТУДЕНТОВ ==========
        # Получаем все поля full_name из динамических полей
        full_names = request.form.getlist("full_name")
        # Фильтруем пустые
        mandatory_students_list = [name.strip() for name in full_names if name and name.strip()]
        
        # Превращаем в текст с переносами строк
        mandatory_students_lines = "\n".join(mandatory_students_list)
        # ====================================================
        
        data = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "location": request.form.get("location"),
            "start_at": start_at,
            "registration_deadline": registration_deadline,
            "max_participants": int(request.form.get("max_participants", 50)),
            "status": "registration_open"
        }
        
        # Добавляем обязательных студентов, если они есть
        if mandatory_students_lines:
            data["mandatory_students_lines"] = mandatory_students_lines
            print(f"📋 Отправляем обязательных студентов: {mandatory_students_lines}")
        
        try:
            # Получаем список существующих мероприятий для проверки дубликатов
            events_response = requests.get(f"{API_BASE_URL}/events/", headers=headers, timeout=5)
            events_list = []
            if events_response.status_code == 200:
                events_data = events_response.json()
                if isinstance(events_data, dict):
                    events_list = events_data.get("results", [])
                elif isinstance(events_data, list):
                    events_list = events_data
            
            # Проверка на дубликат по названию
            existing_titles = [e.get("title", "").lower() for e in events_list]
            if data["title"].lower() in existing_titles:
                return render_template("teacher_create.html", error="Мероприятие с таким названием уже существует")
            
            # Отправляем запрос на создание
            response = requests.post(f"{API_BASE_URL}/events/", json=data, headers=headers, timeout=5)
            
            print(f"📤 Статус создания: {response.status_code}")
            print(f"📤 Ответ: {response.text}")
            
            if response.status_code == 201:
                return redirect(url_for("teacher_events"))
            else:
                return render_template("teacher_create.html", error=f"Ошибка: {response.text}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return render_template("teacher_create.html", error=f"Ошибка: {e}")
    
    return render_template("teacher_create.html")

@app.route("/teacher/event/<int:event_id>")
def teacher_event(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем мероприятие
        event_response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        if event_response.status_code != 200:
            return redirect(url_for("teacher_events"))
        event = event_response.json()
        
        if event.get("created_by", {}).get("id") != session.get("user_id"):
            return redirect(url_for("teacher_events"))
        
        # Получаем обязательных студентов
        mandatory_response = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
        mandatory_students = []
        if mandatory_response.status_code == 200:
            data = mandatory_response.json()
            mandatory_students = data.get("results", []) if isinstance(data, dict) else data
        
        # Получаем регистрации по QR
        registrations_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        registrations = []
        if registrations_response.status_code == 200:
            data = registrations_response.json()
            all_regs = data.get("results", []) if isinstance(data, dict) else data
            registrations = [r for r in all_regs if r.get("event") == event_id]
        
        # ========== СИНХРОНИЗАЦИЯ ==========
        # Создаём словарь обязательных студентов по ФИО
        mandatory_by_name = {s.get("full_name", "").strip().lower(): s for s in mandatory_students}
        
        # Проходим по всем регистрациям
        for reg in registrations:
            reg_name = reg.get("full_name", "").strip().lower()
            if reg_name in mandatory_by_name:
                mandatory_student = mandatory_by_name[reg_name]
                # Если обязательный студент ещё не отмечен как пришедший
                if not mandatory_student.get("attended"):
                    print(f"🔄 Синхронизация: {reg_name} -> отмечаем как пришедшего")
                    # Отмечаем присутствие
                    requests.patch(
                        f"{API_BASE_URL}/events/{event_id}/mandatory-students/{mandatory_student['id']}/mark-attendance/",
                        json={"attended": True},
                        headers=headers,
                        timeout=5
                    )
                    # Если есть фото в регистрации, копируем в mandatory
                    if reg.get("selfie"):
                        # Скачиваем фото из регистрации
                        selfie_url = reg.get("selfie")
                        if selfie_url:
                            # Загружаем фото в mandatory (через upload-selfie)
                            with requests.get(selfie_url, stream=True) as r:
                                if r.status_code == 200:
                                    files = {'selfie': (selfie_url.split('/')[-1], r.raw, 'image/jpeg')}
                                    requests.patch(
                                        f"{API_BASE_URL}/events/{event_id}/mandatory-students/{mandatory_student['id']}/upload-selfie/",
                                        files=files,
                                        headers=headers,
                                        timeout=10
                                    )
        
        # Обновляем список обязательных студентов после синхронизации
        mandatory_response = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
        mandatory_students = []
        if mandatory_response.status_code == 200:
            data = mandatory_response.json()
            mandatory_students = data.get("results", []) if isinstance(data, dict) else data
        
        # Разделяем регистрации: обязательные (уже есть в mandatory) и остальные
        mandatory_names = {s.get("full_name", "").strip().lower() for s in mandatory_students}
        qr_only_registrations = []
        mandatory_registrations = []
        
        for reg in registrations:
            reg_name = reg.get("full_name", "").strip().lower()
            if reg_name in mandatory_names:
                mandatory_registrations.append(reg)
            else:
                qr_only_registrations.append(reg)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        event = None
        mandatory_students = []
        qr_only_registrations = []
        mandatory_registrations = []
    
    return render_template("teacher_event.html", 
                          event=event, 
                          mandatory_students=mandatory_students,
                          registrations=qr_only_registrations,
                          mandatory_registrations=mandatory_registrations)

@app.route("/teacher/qr/<int:event_id>")
def teacher_qr(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        event = response.json() if response.status_code == 200 else None
        
        if event:
            # Проверяем, что мероприятие принадлежит преподавателю
            if event.get("created_by", {}).get("id") != session.get("user_id"):
                return redirect(url_for("teacher_events"))
            
            qr_token = event.get("qr_token")
            # Ссылка для студента
            qr_url = f"http://127.0.0.1:5000/attend/{event_id}"
            
            # Проверяем, есть ли уже сгенерированное изображение
            qr_image_path = f"qrcodes/event_{event_id}.png"
            full_path = os.path.join("static", qr_image_path)
            
            if os.path.exists(full_path):
                qr_image = qr_image_path
            else:
                qr_image = None
        else:
            event = None
            qr_url = None
            qr_image = None
            
    except Exception as e:
        print(f"Ошибка: {e}")
        event = None
        qr_url = None
        qr_image = None
    
    return render_template("teacher_qr.html", event=event, qr_url=qr_url, qr_image=qr_image)

@app.route("/teacher/generate_qr_ajax/<int:event_id>", methods=["POST"])
def teacher_generate_qr_ajax(event_id):
    """Генерация QR-кода через AJAX"""
    if "access_token" not in session or session.get("role") != "teacher":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем мероприятие
        response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        
        if response.status_code == 200:
            event = response.json()
            
            # Проверяем, что мероприятие принадлежит преподавателю
            if event.get("created_by", {}).get("id") != session.get("user_id"):
                return {"success": False, "error": "Нет доступа к мероприятию"}, 403
            
            # Получаем IP для QR-ссылки
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                s.close()
            except:
                local_ip = "127.0.0.1"
            
            # Ссылка для студента
            qr_data = f"http://{local_ip}:5000/attend/{event_id}"
            
            # Генерируем QR-код
            import qrcode
            import os
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем изображение
            qr_filename = f"event_{event_id}.png"
            qr_folder = os.path.join("static", "qrcodes")
            os.makedirs(qr_folder, exist_ok=True)
            qr_path = os.path.join(qr_folder, qr_filename)
            img.save(qr_path)
            
            # Обновляем путь в event (опционально)
            # Можно сохранить в event.qr_code_path, если нужно
            
            return {"success": True, "qr_path": f"qrcodes/{qr_filename}"}
        else:
            return {"success": False, "error": "Мероприятие не найдено"}
            
    except Exception as e:
        print(f"Ошибка генерации QR: {e}")
        return {"success": False, "error": str(e)}, 500

@app.route("/teacher/mark_mandatory_attendance/<int:event_id>/<int:mandatory_id>", methods=["POST"])
def mark_mandatory_attendance(event_id, mandatory_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.patch(
            f"{API_BASE_URL}/events/{event_id}/mandatory-students/{mandatory_id}/mark-attendance/",
            json={"attended": True},
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500    
    
@app.route("/teacher/generate_qr/<int:event_id>", methods=["POST"])
def teacher_generate_qr(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем мероприятие, чтобы взять qr_token
        response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        
        if response.status_code == 200:
            event = response.json()
            
            # Проверяем, что мероприятие принадлежит преподавателю
            if event.get("created_by", {}).get("id") != session.get("user_id"):
                return redirect(url_for("teacher_events"))
            
            qr_token = event.get("qr_token")
            # Ссылка для студента
            qr_data = f"http://192.168.10.102:5000/attend/{event_id}"
            
            # Генерируем QR-код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохраняем изображение
            qr_filename = f"event_{event_id}.png"
            qr_path = os.path.join("static", "qrcodes", qr_filename)
            img.save(qr_path)
            
            print(f"✅ QR-код сохранён: {qr_path}")
            
    except Exception as e:
        print(f"Ошибка генерации QR: {e}")
    
    return redirect(url_for("teacher_qr", event_id=event_id))

# Подтверждение/отклонение регистрации (преподаватель)
@app.route("/teacher/confirm-registration/<int:registration_id>", methods=["POST"])
def teacher_confirm_registration(registration_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return {"success": False, "error": "Нет доступа"}, 403
    
    data = request.get_json()
    status = data.get("status")
    
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }
    
    payload = {"attendance_status": status}
    
    try:
        response = requests.patch(
            f"{API_BASE_URL}/registrations/{registration_id}/confirm/",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


# Отметка присутствия (преподаватель)
@app.route("/teacher/mark-attendance/<int:registration_id>", methods=["POST"])
def teacher_mark_attendance(registration_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.patch(
            f"{API_BASE_URL}/registrations/{registration_id}/mark-attendance/",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ========== РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ (ПРЕПОДАВАТЕЛЬ) ==========

@app.route("/teacher/edit/<int:event_id>", methods=["GET", "POST"])
def teacher_edit_event(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    # GET: получаем данные мероприятия для формы
    if request.method == "GET":
        try:
            response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
            if response.status_code == 200:
                event = response.json()
                # Проверяем, что мероприятие принадлежит преподавателю
                if event.get("created_by", {}).get("id") != session.get("user_id"):
                    return redirect(url_for("teacher_events"))
                return render_template("edit_event.html", event=event)
            else:
                return redirect(url_for("teacher_events"))
        except Exception as e:
            print(f"Ошибка: {e}")
            return redirect(url_for("teacher_events"))
    
    # POST: сохраняем изменения
    if request.method == "POST":
        start_at = request.form.get("start_at")
        registration_deadline = request.form.get("registration_deadline")
        
        if start_at and len(start_at) == 16:
            start_at = start_at + ":00"
        if registration_deadline and len(registration_deadline) == 16:
            registration_deadline = registration_deadline + ":00"
        
        data = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "location": request.form.get("location"),
            "start_at": start_at,
            "registration_deadline": registration_deadline,
            "max_participants": int(request.form.get("max_participants")),
            "status": request.form.get("status")
        }
        
        try:
            response = requests.put(
                f"{API_BASE_URL}/events/{event_id}/",
                json=data,
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                return redirect(url_for("teacher_event", event_id=event_id))
            else:
                event = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers).json()
                return render_template("edit_event.html", event=event, error=f"Ошибка: {response.text}")
                
        except Exception as e:
            event = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers).json()
            return render_template("edit_event.html", event=event, error=f"Ошибка: {e}")

@app.route("/teacher/delete/<int:event_id>", methods=["POST"])
def teacher_delete_event(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.delete(
            f"{API_BASE_URL}/events/{event_id}/",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 204:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


# ========== РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ (АДМИН) ==========

@app.route("/admin/edit/<int:event_id>", methods=["GET", "POST"])
def admin_edit_event(event_id):
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    if request.method == "GET":
        try:
            response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
            if response.status_code == 200:
                event = response.json()
                return render_template("edit_event.html", event=event)
            else:
                return redirect(url_for("admin_events"))
        except Exception as e:
            print(f"Ошибка: {e}")
            return redirect(url_for("admin_events"))
    
    if request.method == "POST":
        start_at = request.form.get("start_at")
        registration_deadline = request.form.get("registration_deadline")
        
        if start_at and len(start_at) == 16:
            start_at = start_at + ":00"
        if registration_deadline and len(registration_deadline) == 16:
            registration_deadline = registration_deadline + ":00"
        
        data = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "location": request.form.get("location"),
            "start_at": start_at,
            "registration_deadline": registration_deadline,
            "max_participants": int(request.form.get("max_participants")),
            "status": request.form.get("status")
        }
        
        try:
            response = requests.put(
                f"{API_BASE_URL}/events/{event_id}/",
                json=data,
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                return redirect(url_for("admin_event", event_id=event_id))
            else:
                event = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers).json()
                return render_template("edit_event.html", event=event, error=f"Ошибка: {response.text}")
                
        except Exception as e:
            event = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers).json()
            return render_template("edit_event.html", event=event, error=f"Ошибка: {e}")
        

@app.route("/admin/delete/<int:event_id>", methods=["POST"])
def admin_delete_event(event_id):
    if "access_token" not in session or session.get("role") != "admin":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.delete(
            f"{API_BASE_URL}/events/{event_id}/",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 204:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


# ========== СТАТИСТИКА (РЕЙТИНГ СТУДЕНТОВ) ==========

@app.route("/admin/rating")
def admin_rating():
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.get(f"{API_BASE_URL}/stats/rating/", headers=headers, timeout=5)
        
        if response.status_code == 200:
            rating = response.json()
        else:
            rating = []
            
    except Exception as e:
        print(f"Ошибка: {e}")
        rating = []
    
    return render_template("admin_rating.html", rating=rating)


# ========== ПОИСК И ПАГИНАЦИЯ ==========

def fetch_with_pagination(url, headers, page=1, page_size=10):
    """Вспомогательная функция для пагинации"""
    params = {"page": page, "page_size": page_size}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "results": data.get("results", []),
                "count": data.get("count", 0),
                "next": data.get("next"),
                "previous": data.get("previous")
            }
    except Exception as e:
        print(f"Ошибка: {e}")
    return {"results": [], "count": 0, "next": None, "previous": None}
# ========== СТУДЕНТ ==========

# Страница регистрации студента
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    redirect_url = request.args.get("redirect", "/student/events")
    
    if request.method == "POST":
        data = {
            "username": request.form.get("username"),
            "password": request.form.get("password"),
            "first_name": request.form.get("first_name"),
            "last_name": request.form.get("last_name")
        }
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/auth/register/",
                json=data,
                timeout=5
            )
            
            if response.status_code == 201:
                # После регистрации сразу входим
                login_response = requests.post(
                    f"{API_BASE_URL}/auth/token/",
                    json={
                        "username": data["username"],
                        "password": data["password"]
                    },
                    timeout=5
                )
                
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    session["access_token"] = token_data["access"]
                    session["refresh_token"] = token_data["refresh"]
                    session["user_id"] = response.json().get("id")
                    session["role"] = "student"
                    session["username"] = data["username"]
                    
                    # 🔥 Редирект на сохранённый URL или на страницу отметки
                    return redirect(redirect_url)
                else:
                    return render_template("student_register.html", error="Аккаунт создан, но не удалось войти")
            else:
                error_text = response.text
                try:
                    error_json = response.json()
                    if isinstance(error_json, dict):
                        error_messages = []
                        for field, errors in error_json.items():
                            error_messages.append(f"{field}: {', '.join(errors)}")
                        error_text = "\n".join(error_messages)
                except:
                    pass
                return render_template("student_register.html", error=error_text)
                
        except requests.exceptions.ConnectionError:
            return render_template("student_register.html", error="Ошибка подключения к серверу")
        except Exception as e:
            return render_template("student_register.html", error=f"Ошибка: {e}")
    
    return render_template("student_register.html")


# Список доступных мероприятий (для студента)
@app.route("/student/events")
def student_events():
    if "access_token" not in session or session.get("role") != "student":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем все мероприятия
        events_response = requests.get(f"{API_BASE_URL}/events/", headers=headers, timeout=5)
        events = events_response.json().get("results", []) if events_response.status_code == 200 else []
        
        # Получаем свои регистрации
        registrations_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        my_registrations = registrations_response.json().get("results", []) if registrations_response.status_code == 200 else []
        
    except Exception as e:
        print(f"Ошибка: {e}")
        events = []
        my_registrations = []
    
    return render_template("student_events.html", events=events, my_registrations=my_registrations)


# Регистрация на мероприятие по QR
@app.route("/student/register-by-qr/<int:event_id>", methods=["POST"])
def student_register_by_qr(event_id):
    if "access_token" not in session or session.get("role") != "student":
        return redirect(url_for("home"))
    
    qr_token = request.form.get("qr_token")
    
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }
    
    payload = {"qr_token": qr_token}
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/events/{event_id}/register-by-qr/",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 201:
            return redirect(url_for("student_events"))
        elif response.status_code == 400:
            return render_template("student_events.html", events=[], my_registrations=[], error="Неверный QR-код")
        elif response.status_code == 409:
            return render_template("student_events.html", events=[], my_registrations=[], error="Вы уже зарегистрированы на это мероприятие")
        else:
            return render_template("student_events.html", events=[], my_registrations=[], error=f"Ошибка: {response.text}")
            
    except Exception as e:
        return render_template("student_events.html", events=[], my_registrations=[], error=f"Ошибка: {e}")


# Мои регистрации
@app.route("/student/my-registrations")
def student_my_registrations():
    if "access_token" not in session or session.get("role") != "student":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        
        if response.status_code == 200:
            registrations = response.json().get("results", [])
            
            # Для каждого регистрации получаем данные о мероприятии
            for reg in registrations:
                event_response = requests.get(f"{API_BASE_URL}/events/{reg['event']}/", headers=headers, timeout=5)
                if event_response.status_code == 200:
                    event_data = event_response.json()
                    reg["event_title"] = event_data.get("title")
                    reg["event_start_at"] = event_data.get("start_at")
        else:
            registrations = []
            
    except Exception as e:
        print(f"Ошибка: {e}")
        registrations = []
    
    return render_template("student_my_registrations.html", registrations=registrations)

@app.route("/attend/<int:event_id>", methods=["GET", "POST"])
def attend_event(event_id):
    """Страница отметки студента по QR с синхронизацией обязательных"""

    # Проверяем, не зарегистрирован ли уже этот студент на это мероприятие
    reg_check_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
    already_exists = False
    if reg_check_response.status_code == 200:
        reg_data = reg_check_response.json()
        all_regs = reg_data.get("results", []) if isinstance(reg_data, dict) else reg_data
        for reg in all_regs:
            if reg.get("event") == event_id and reg.get("full_name") == student_name:
                already_exists = True
                break

    if already_exists:
        return render_template("attend.html", event=event, error="Вы уже зарегистрированы на это мероприятие!")

    # Если студент не авторизован — сохраняем редирект и показываем вход
    if "access_token" not in session or session.get("role") != "student":
        session["redirect_after_login"] = f"/attend/{event_id}"
        return render_template("attend_login.html", event_id=event_id)
    

    headers = {"Authorization": f"Bearer {session['access_token']}"}

    # Запрет для преподавателей и админов регистрироваться на мероприятия
    if session.get("role") in ["admin", "teacher"]:
        return render_template("home.html", error="Преподаватели и администраторы не могут регистрироваться на мероприятия как студенты")

    try:
        # Получаем мероприятие
        event_resp = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        if event_resp.status_code != 200:
            return render_template("home.html", error="Мероприятие не найдено")
        event = event_resp.json()

        # Проверяем, не истекло ли мероприятие
        if event.get("start_at"):
            event_date_str = event.get("start_at")
            # Убираем Z и парсим
            event_date_str = event_date_str.replace('Z', '+00:00')
            event_date = datetime.fromisoformat(event_date_str)
            
            if event_date < datetime.now(event_date.tzinfo):
                return render_template("event_expired.html", event=event)

    
        # Получаем список обязательных студентов
        mand_resp = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
        mandatory_students = []
        if mand_resp.status_code == 200:
            data = mand_resp.json()
            if isinstance(data, dict):
                mandatory_students = data.get("results", [])
            elif isinstance(data, list):
                mandatory_students = data

        if request.method == "POST":
            student_name = request.form.get("student_name", "").strip()
            student_group = request.form.get("student_group", "").strip()
            qr_token = event.get("qr_token")

            # Обработка фото
            selfie_path = None
            if 'selfie' in request.files:
                file = request.files['selfie']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{student_name}_{student_group}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                    folder = os.path.join("static", "selfies")
                    os.makedirs(folder, exist_ok=True)
                    file_path = os.path.join(folder, filename)
                    file.save(file_path)
                    selfie_path = f"selfies/{filename}"

            # === ПОИСК СОВПАДЕНИЯ В ОБЯЗАТЕЛЬНОМ СПИСКЕ ===
            matched = None
            for s in mandatory_students:
                if s.get("full_name", "").strip().lower() == student_name.lower():
                    matched = s
                    break

            if matched:
                # === СТУДЕНТ ИЗ ОБЯЗАТЕЛЬНОГО СПИСКА ===
                mandatory_id = matched["id"]

                # 1. Отмечаем присутствие в mandatory-students
                requests.patch(
                    f"{API_BASE_URL}/events/{event_id}/mandatory-students/{mandatory_id}/mark-attendance/",
                    json={"attended": True},
                    headers=headers,
                    timeout=5
                )

                # 2. Загружаем фото в mandatory-students
                if selfie_path:
                    with open(os.path.join("static", selfie_path), "rb") as f:
                        requests.patch(
                            f"{API_BASE_URL}/events/{event_id}/mandatory-students/{mandatory_id}/upload-selfie/",
                            files={"selfie": f},
                            headers=headers,
                            timeout=10
                        )

                # 3. Проверяем, есть ли уже запись в registrations
                reg_resp = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
                existing_reg = None
                if reg_resp.status_code == 200:
                    reg_data = reg_resp.json()
                    all_regs = reg_data.get("results", []) if isinstance(reg_data, dict) else reg_data
                    for r in all_regs:
                        if r.get("event") == event_id and r.get("full_name") == student_name:
                            existing_reg = r
                            break

                if existing_reg:
                    # Обновляем фото в существующей регистрации
                    if selfie_path:
                        with open(os.path.join("static", selfie_path), "rb") as f:
                            requests.patch(
                                f"{API_BASE_URL}/registrations/{existing_reg['id']}/upload-selfie/",
                                files={"selfie": f},
                                headers=headers,
                                timeout=10
                            )
                else:
                    # Создаём новую регистрацию с ФИО и группой
                    reg_payload = {
                        "qr_token": qr_token,
                        "full_name": student_name,
                        "group": student_group
                    }
                    reg_resp = requests.post(
                        f"{API_BASE_URL}/events/{event_id}/register-by-qr/",
                        json=reg_payload,
                        headers=headers,
                        timeout=5
                    )
                    
                    # 🔥 ПОДТВЕРЖДАЕМ РЕГИСТРАЦИЮ ДЛЯ ОБЯЗАТЕЛЬНОГО СТУДЕНТА
                    if reg_resp.status_code == 201:
                        reg_id = reg_resp.json().get("id")
                        requests.patch(
                            f"{API_BASE_URL}/registrations/{reg_id}/confirm/",
                            json={"attendance_status": "confirmed"},
                            headers=headers,
                            timeout=5
                        )
                    
                    if reg_resp.status_code == 201 and selfie_path:
                        reg_id = reg_resp.json().get("id")
                        with open(os.path.join("static", selfie_path), "rb") as f:
                            requests.patch(
                                f"{API_BASE_URL}/registrations/{reg_id}/upload-selfie/",
                                files={"selfie": f},
                                headers=headers,
                                timeout=10
                            )

                return render_template("attend_success.html", event=event)

            else:
                # === НОВЫЙ СТУДЕНТ (НЕ ИЗ ОБЯЗАТЕЛЬНОГО СПИСКА) ===
                reg_payload = {
                    "qr_token": qr_token,
                    "full_name": student_name,
                    "group": student_group
                }
                reg_resp = requests.post(
                    f"{API_BASE_URL}/events/{event_id}/register-by-qr/",
                    json=reg_payload,
                    headers=headers,
                    timeout=5
                )
                
                # 🔥 ВОТ ЗДЕСЬ ДОБАВИЛ ПОДТВЕРЖДЕНИЕ ДЛЯ НОВОГО СТУДЕНТА
                if reg_resp.status_code == 201:
                    reg_id = reg_resp.json().get("id")
                    # Сразу подтверждаем регистрацию
                    requests.patch(
                        f"{API_BASE_URL}/registrations/{reg_id}/confirm/",
                        json={"attendance_status": "confirmed"},
                        headers=headers,
                        timeout=5
                    )
                    
                    # Загружаем фото, если есть
                    if selfie_path:
                        with open(os.path.join("static", selfie_path), "rb") as f:
                            requests.patch(
                                f"{API_BASE_URL}/registrations/{reg_id}/upload-selfie/",
                                files={"selfie": f},
                                headers=headers,
                                timeout=10
                            )
                # =============================================

                return render_template("attend_success.html", event=event)

        # GET — проверяем, регистрировался ли уже студент
        already_registered = False
        reg_resp = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        if reg_resp.status_code == 200:
            reg_data = reg_resp.json()
            all_regs = reg_data.get("results", []) if isinstance(reg_data, dict) else reg_data
            for r in all_regs:
                if r.get("event") == event_id:
                    already_registered = True
                    break

        return render_template("attend.html", event=event, already_registered=already_registered)

    except Exception as e:
        print(f"Ошибка в /attend/{event_id}: {e}")
        return render_template("home.html", error="Ошибка при загрузке мероприятия")

@app.route("/attend_login", methods=["POST"])
def attend_login():
    username = request.form.get("username")
    password = request.form.get("password")
    event_id = request.form.get("event_id")
    
    try:
        response = requests.post(f"{API_BASE_URL}/auth/token/", json={
            "username": username,
            "password": password
        }, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            session["access_token"] = data["access"]
            session["refresh_token"] = data["refresh"]
            
            headers = {"Authorization": f"Bearer {data['access']}"}
            user_response = requests.get(f"{API_BASE_URL}/auth/me/", headers=headers, timeout=5)
            
            if user_response.status_code == 200:
                user = user_response.json()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                session["username"] = user["username"]
                
                # 🔥 ВАЖНО: редирект на страницу отметки, а не на список мероприятий
                if event_id:
                    return redirect(f"/attend/{event_id}")
                elif session.get("redirect_after_login"):
                    return redirect(session.pop("redirect_after_login"))
                else:
                    return redirect(url_for("student_events"))
        
        return render_template("attend_login.html", event_id=event_id, error="Неверные логин или пароль")
        
    except Exception as e:
        return render_template("attend_login.html", event_id=event_id, error="Ошибка подключения")

# Отметка присутствия студентом
@app.route("/student/mark-attendance/<int:registration_id>", methods=["POST"])
def student_mark_attendance(registration_id):
    if "access_token" not in session or session.get("role") != "student":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.patch(
            f"{API_BASE_URL}/registrations/{registration_id}/mark-attendance/",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/teacher/edit-mandatory/<int:event_id>", methods=["GET", "POST"])
def teacher_edit_mandatory(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    # Получаем мероприятие
    event_response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
    if event_response.status_code != 200:
        return redirect(url_for("teacher_events"))
    event = event_response.json()
    
    # Проверяем, что мероприятие принадлежит преподавателю
    if event.get("created_by", {}).get("id") != session.get("user_id"):
        return redirect(url_for("teacher_events"))
    
    # ========== POST: Сохранение изменений ==========
    if request.method == "POST":
        mandatory_students_lines = request.form.get("mandatory_students_lines", "").strip()
        
        # Получаем текущий список обязательных студентов
        mand_response = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
        old_students = []
        if mand_response.status_code == 200:
            mand_data = mand_response.json()
            old_students = mand_data.get("results", []) if isinstance(mand_data, dict) else mand_data
        
        # Удаляем каждого обязательного студента
        for student in old_students:
            # Удаляем из обязательных
            delete_response = requests.delete(
                f"{API_BASE_URL}/events/{event_id}/mandatory-students/{student['id']}/",
                headers=headers,
                timeout=5
            )
            print(f"🗑️ Удалён обязательный студент {student.get('full_name')}: {delete_response.status_code}")
            
            # Также удаляем регистрацию этого студента (чтобы не восстановился при синхронизации)
            reg_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
            if reg_response.status_code == 200:
                reg_data = reg_response.json()
                all_regs = reg_data.get("results", []) if isinstance(reg_data, dict) else reg_data
                for reg in all_regs:
                    if reg.get("event") == event_id and reg.get("full_name") == student.get("full_name"):
                        delete_reg_response = requests.delete(
                            f"{API_BASE_URL}/registrations/{reg['id']}/",
                            headers=headers,
                            timeout=5
                        )
                        print(f"🗑️ Удалена регистрация {student.get('full_name')}: {delete_reg_response.status_code}")
        
        # Создаём новых студентов
        if mandatory_students_lines:
            create_response = requests.post(
                f"{API_BASE_URL}/events/{event_id}/mandatory-students/",
                json={"mandatory_students_lines": mandatory_students_lines},
                headers=headers,
                timeout=5
            )
            print(f"📤 Создание обязательных студентов: {create_response.status_code}")
            if create_response.status_code != 200 and create_response.status_code != 201:
                print(f"Ошибка: {create_response.text}")
        
        # Получаем обновлённый список для отображения
        mand_response = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
        mandatory_students_list = []
        if mand_response.status_code == 200:
            mand_data = mand_response.json()
            mandatory_students_list = mand_data.get("results", []) if isinstance(mand_data, dict) else mand_data
        
        # Формируем строки для текстового поля
        mandatory_lines = ""
        for student in mandatory_students_list:
            mandatory_lines += f"{student.get('full_name', '')}\n"
        
        return render_template("edit_mandatory_students.html", 
                              event=event, 
                              mandatory_lines=mandatory_lines,
                              mandatory_students_list=mandatory_students_list,
                              success="Список обязательных студентов обновлён!")
    
    # ========== GET: Показать текущий список ==========
    mand_response = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
    mandatory_lines = ""
    mandatory_students_list = []
    
    if mand_response.status_code == 200:
        mand_data = mand_response.json()
        mandatory_students_list = mand_data.get("results", []) if isinstance(mand_data, dict) else mand_data
        for student in mandatory_students_list:
            mandatory_lines += f"{student.get('full_name', '')}\n"
    
    return render_template("edit_mandatory_students.html", 
                          event=event, 
                          mandatory_lines=mandatory_lines,
                          mandatory_students_list=mandatory_students_list)

@app.route("/teacher/delete-mandatory/<int:event_id>/<int:mandatory_id>", methods=["POST"])
def teacher_delete_mandatory(event_id, mandatory_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return {"success": False, "error": "Нет доступа"}, 403
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.delete(
            f"{API_BASE_URL}/events/{event_id}/mandatory-students/{mandatory_id}/",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 204:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500
                             
# ---------- АДМИН ----------
@app.route("/admin/events")
def admin_events():
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    # Получаем параметры поиска и пагинации
    search_query = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    page_size = 5  # Количество мероприятий на странице
    
    try:
        # Если есть поиск, фильтруем на клиентской стороне (API не поддерживает поиск)
        response = requests.get(f"{API_BASE_URL}/events/", headers=headers, timeout=5)
        
        if response.status_code == 200:
            all_events = response.json().get("results", [])
            
            # Поиск по названию
            if search_query:
                all_events = [e for e in all_events if search_query.lower() in e.get("title", "").lower()]
            
            # Пагинация
            total_count = len(all_events)
            total_pages = (total_count + page_size - 1) // page_size
            start = (page - 1) * page_size
            end = start + page_size
            events = all_events[start:end]
            
        else:
            events = []
            total_pages = 1
            total_count = 0
            
    except Exception as e:
        print(f"Ошибка: {e}")
        events = []
        total_pages = 1
        total_count = 0
    
    return render_template(
        "admin_events.html", 
        events=events,
        search_query=search_query,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count
    )
@app.route("/admin/event/<int:event_id>")
def admin_event(event_id):
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем мероприятие
        event_response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        if event_response.status_code != 200:
            return redirect(url_for("admin_events"))
        event = event_response.json()
        
        # Получаем обязательных студентов
        mandatory_response = requests.get(f"{API_BASE_URL}/events/{event_id}/mandatory-students/", headers=headers, timeout=5)
        mandatory_students = []
        if mandatory_response.status_code == 200:
            data = mandatory_response.json()
            mandatory_students = data.get("results", []) if isinstance(data, dict) else data
        
        # Получаем регистрации по QR
        registrations_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        registrations = []
        if registrations_response.status_code == 200:
            data = registrations_response.json()
            all_regs = data.get("results", []) if isinstance(data, dict) else data
            registrations = [r for r in all_regs if r.get("event") == event_id]
        
        # Имя преподавателя
        teacher_name = event.get("created_by", {}).get("username", "Неизвестен")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        event = None
        mandatory_students = []
        registrations = []
        teacher_name = "Неизвестен"
    
    return render_template("admin_event.html", 
                          event=event, 
                          teacher_name=teacher_name,
                          mandatory_students=mandatory_students,
                          registrations=registrations)



# Подтверждение/отклонение регистрации (админ и преподаватель)
@app.route("/admin/confirm-registration/<int:registration_id>", methods=["POST"])
def admin_confirm_registration(registration_id):
    if "access_token" not in session or session.get("role") not in ["admin", "teacher"]:
        return {"success": False, "error": "Нет доступа"}, 403
    
    data = request.get_json()
    status = data.get("status")
    
    if status not in ["confirmed", "rejected"]:
        return {"success": False, "error": "Неверный статус"}, 400
    
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }
    
    payload = {"attendance_status": status}
    
    try:
        response = requests.patch(
            f"{API_BASE_URL}/registrations/{registration_id}/confirm/",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": response.text}, response.status_code
            
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


# Экспорт регистраций в CSV
@app.route("/admin/export-registrations/<int:event_id>")
def admin_export_registrations(event_id):
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/exports/event/{event_id}/registrations.csv",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            # Отправляем CSV файл пользователю
            from flask import Response
            return Response(
                response.content,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment;filename=event_{event_id}_registrations.csv"}
            )
        else:
            return f"Ошибка экспорта: {response.text}", response.status_code
            
    except Exception as e:
        return f"Ошибка: {e}", 500

@app.route("/admin/create-teacher", methods=["GET", "POST"])
def admin_create_teacher():
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    if request.method == "POST":
        headers = {
            "Authorization": f"Bearer {session['access_token']}",
            "Content-Type": "application/json"
        }
        
        data = {
            "username": request.form.get("username"),
            "password": request.form.get("password"),
            "first_name": request.form.get("first_name"),
            "last_name": request.form.get("last_name"),
            "is_active": True
        }
        
        email = request.form.get("email")
        if email:
            data["email"] = email
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/users/teachers/", 
                json=data, 
                headers=headers,
                timeout=5
            )
            
            print(f"📤 Статус создания преподавателя: {response.status_code}")
            print(f"📤 Ответ: {response.text}")
            
            if response.status_code == 201:
                return render_template(
                    "admin_create_teacher.html", 
                    success=f"✅ Преподаватель {data['username']} успешно создан!"
                )
            else:
                error_text = response.text
                try:
                    error_json = response.json()
                    if isinstance(error_json, dict):
                        error_messages = []
                        for field, errors in error_json.items():
                            error_messages.append(f"{field}: {', '.join(errors)}")
                        error_text = "\n".join(error_messages)
                except:
                    pass
                
                return render_template(
                    "admin_create_teacher.html", 
                    error=f"Ошибка: {error_text}"
                )
                
        except requests.exceptions.ConnectionError:
            return render_template(
                "admin_create_teacher.html", 
                error="Ошибка подключения к бэкенду. Убедись, что сервер запущен."
            )
        except Exception as e:
            return render_template(
                "admin_create_teacher.html", 
                error=f"Неизвестная ошибка: {e}"
            )
    
    return render_template("admin_create_teacher.html")


@app.route("/admin/registrations")
def admin_registrations():
    if "access_token" not in session or session.get("role") != "admin":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        registrations = response.json().get("results", []) if response.status_code == 200 else []
    except:
        registrations = []
    
    return render_template("admin_registrations.html", registrations=registrations)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)