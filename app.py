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
        
        # Собираем данные
        data = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "location": request.form.get("location"),
            "start_at": request.form.get("start_at"),
            "registration_deadline": request.form.get("registration_deadline"),
            "max_participants": request.form.get("max_participants"),
            "status": "registration_open"
        }
        
        # ПРОВЕРКА: выводим в терминал, что отправляем
        print("=" * 50)
        print("📤 ОТПРАВЛЯЕМЫЕ ДАННЫЕ:")
        for key, value in data.items():
            print(f"  {key}: {value} (тип: {type(value).__name__})")
        print("=" * 50)
        
        # Преобразуем max_participants в int
        if data["max_participants"]:
            data["max_participants"] = int(data["max_participants"])
        
        # Добавляем :00 к датам, если нужно
        if data["start_at"] and len(data["start_at"]) == 16:
            data["start_at"] = data["start_at"] + ":00"
        if data["registration_deadline"] and len(data["registration_deadline"]) == 16:
            data["registration_deadline"] = data["registration_deadline"] + ":00"
        
        try:
            response = requests.post(f"{API_BASE_URL}/events/", json=data, headers=headers, timeout=5)
            print(f"📥 ОТВЕТ: {response.status_code}")
            print(f"📥 ТЕКСТ ОТВЕТА: {response.text}")
            
            if response.status_code == 201:
                return redirect(url_for("teacher_events"))
            else:
                return render_template("teacher_create.html", error=f"Ошибка API: {response.text}")
        except Exception as e:
            return render_template("teacher_create.html", error=f"Ошибка подключения: {e}")
    
    return render_template("teacher_create.html")

@app.route("/teacher/event/<int:event_id>")
def teacher_event(event_id):
    if "access_token" not in session or session.get("role") != "teacher":
        return redirect(url_for("home"))
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем мероприятие
        event_response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        
        if event_response.status_code == 200:
            event = event_response.json()
            
            # Проверяем, что мероприятие принадлежит текущему преподавателю
            user_id = session.get("user_id")
            event_teacher_id = event.get("created_by", {}).get("id") if event.get("created_by") else None
            
            if event_teacher_id != user_id:
                # Если это не его мероприятие — возвращаем на список
                print(f"⚠️ Доступ запрещён: преподаватель {user_id} пытался открыть мероприятие {event_id} (создатель {event_teacher_id})")
                return redirect(url_for("teacher_events"))
            
            # Получаем регистрации
            registrations_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
            all_registrations = registrations_response.json().get("results", []) if registrations_response.status_code == 200 else []
            registrations = [r for r in all_registrations if r.get("event") == event_id]
            
        else:
            event = None
            registrations = []
            
    except Exception as e:
        print(f"Ошибка: {e}")
        event = None
        registrations = []
    
    return render_template("teacher_event.html", event=event, registrations=registrations)
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
        # Добавляем :00 к датам, если нужно
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
                    
                    return redirect(url_for("student_events"))
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
    """Страница отметки студента по QR (упрощённая)"""
    
    # Если студент не авторизован, показываем форму входа
    if "access_token" not in session or session.get("role") != "student":
        session["redirect_after_login"] = f"/attend/{event_id}"
        return render_template("attend_login.html", event_id=event_id)
    
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    
    try:
        # Получаем мероприятие
        response = requests.get(f"{API_BASE_URL}/events/{event_id}/", headers=headers, timeout=5)
        event = response.json() if response.status_code == 200 else None
        
        if not event:
            return render_template("home.html", error="Мероприятие не найдено")
        
        # Проверяем, не зарегистрирован ли уже
        reg_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
        already_registered = False
        if reg_response.status_code == 200:
            registrations = reg_response.json().get("results", [])
            already_registered = any(r.get("event") == event_id for r in registrations)
        
        if request.method == "POST":
            student_name = request.form.get("student_name")
            student_group = request.form.get("student_group")
            
            # Обработка фото
            selfie_path = None
            if 'selfie' in request.files:
                file = request.files['selfie']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{student_name}_{student_group}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                    selfie_folder = os.path.join("static", "selfies")
                    os.makedirs(selfie_folder, exist_ok=True)
                    file_path = os.path.join(selfie_folder, filename)
                    file.save(file_path)
                    selfie_path = f"selfies/{filename}"
            
            # Регистрация через API
            qr_token = event.get("qr_token")
            register_response = requests.post(
                f"{API_BASE_URL}/events/{event_id}/register-by-qr/",
                json={"qr_token": qr_token},
                headers=headers,
                timeout=5
            )
            
            if register_response.status_code == 201:
                registration_data = register_response.json()
                registration_id = registration_data.get("id")
                
                # Сразу подтверждаем регистрацию (меняем статус на confirmed)
                confirm_response = requests.patch(
                    f"{API_BASE_URL}/registrations/{registration_id}/confirm/",
                    json={"attendance_status": "confirmed"},
                    headers=headers,
                    timeout=5
                )
                print(f"Подтверждение регистрации: {confirm_response.status_code}")
                
                # Загрузка фото
                if selfie_path and registration_id:
                    full_path = os.path.join("static", selfie_path)
                    with open(full_path, 'rb') as f:
                        files = {'selfie': f}
                        selfie_response = requests.patch(
                            f"{API_BASE_URL}/registrations/{registration_id}/upload-selfie/",
                            files=files,
                            headers=headers,
                            timeout=10
                        )
                        print(f"Загрузка фото: {selfie_response.status_code}")
                
                return render_template("attend_success.html", event=event)
            else:
                return render_template("attend.html", event=event, already_registered=already_registered, error="Ошибка регистрации")
        
        return render_template("attend.html", event=event, already_registered=already_registered)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return render_template("home.html", error="Ошибка при загрузке мероприятия")

@app.route("/attend_login", methods=["POST"])
def attend_login():
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
                
                # Перенаправляем на страницу отметки
                redirect_url = session.pop("redirect_after_login", "/student/events")
                return redirect(redirect_url)
        
        return render_template("attend_login.html", error="Неверные логин или пароль")
        
    except Exception as e:
        return render_template("attend_login.html", error="Ошибка подключения")


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
        
        if event_response.status_code == 200:
            event = event_response.json()
            
            # Получаем регистрации на это мероприятие
            registrations_response = requests.get(f"{API_BASE_URL}/registrations/", headers=headers, timeout=5)
            all_registrations = registrations_response.json().get("results", []) if registrations_response.status_code == 200 else []
            
            # Фильтруем по event_id
            registrations = [r for r in all_registrations if r.get("event") == event_id]
            
            # Имя преподавателя
            teacher_name = event.get("created_by", {}).get("username", "Неизвестен")
            
        else:
            event = None
            registrations = []
            teacher_name = "Неизвестен"
            
    except Exception as e:
        print(f"Ошибка: {e}")
        event = None
        registrations = []
        teacher_name = "Неизвестен"
    
    return render_template("admin_event.html", event=event, teacher_name=teacher_name, registrations=registrations)

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
        
        # Добавляем email, если он указан
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
            
            if response.status_code == 201:
                return render_template(
                    "admin_create_teacher.html", 
                    success=f"✅ Преподаватель {data['username']} успешно создан!"
                )
            else:
                # Обрабатываем ошибки валидации
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