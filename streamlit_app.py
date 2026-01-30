import streamlit as st
import requests
import urllib.parse
import time
from collections import defaultdict
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from ics import Calendar, Event
from zoneinfo import ZoneInfo

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="РЭУ Расписание", page_icon="📅")

st.title("📅 Генератор календаря РЭУ")
st.write("Введите номер своей группы, и я превращу расписание в формат для iPhone/Android/Outlook.")

# --- КОНСТАНТЫ ---
TZ = ZoneInfo("Europe/Moscow")
TIME_SLOTS = {
    '1': '08:30',
    '2': '10:10',
    '3': '11:50',
    '4': '14:00',
    '5': '15:40',
    '6': '17:20',
    '7': '18:55',
    '8': '20:30' 
}
LESSON_DURATION = timedelta(minutes=90)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def create_event(lesson, date_str):
    """Создает объект события для календаря"""
    slot = lesson['slot']
    if slot not in TIME_SLOTS:
        return None

    start_time_str = TIME_SLOTS[slot]
    full_start_dt_str = f"{date_str} {start_time_str}"
    
    try:
        dt_naive = datetime.strptime(full_start_dt_str, "%d.%m.%Y %H:%M")
        start_dt = dt_naive.replace(tzinfo=TZ)
    except ValueError:
        return None

    end_dt = start_dt + LESSON_DURATION
    
    e = Event()
    e.name = f"{lesson['subject']} ({lesson['type']})"
    e.begin = start_dt
    e.end = end_dt
    e.location = lesson['location']
    e.description = f"👨‍🏫 {lesson['teacher']}\n📍 {lesson['location']}"
    return e

def get_ics_string(calendar):
    """Превращает календарь в текст для скачивания"""
    return "".join(calendar.serialize_iter())

# --- ОСНОВНАЯ ЛОГИКА ---
group_name = st.text_input("Номер группы (как на сайте rasp.rea.ru):", value="15.27д-э01/24б")

if st.button("🚀 Получить расписание"):
    if not group_name:
        st.error("Пожалуйста, введите номер группы!")
    else:
        status_text = st.empty() # Место для текста статуса
        progress_bar = st.progress(0) # Прогресс бар
        
        try:
            # 1. ПАРСИНГ
            status_text.text("Подключаюсь к сайту РЭУ...")
            
            encoded_group = urllib.parse.quote(group_name, safe='')
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest'
            }
            params = {'selection': group_name, 'weekNum': '-1', 'catfilter': '0'}

            # Первый запрос, чтобы узнать текущую неделю
            response = requests.get('https://rasp.rea.ru/Schedule/ScheduleCard', params=params, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            try:
                week_input = soup.find('input', id='weekNum')
                if not week_input:
                    st.error("Группа не найдена или сайт РЭУ изменил структуру. Проверьте номер группы.")
                    st.stop()
                start_week = int(week_input['value'])
            except Exception as e:
                st.error(f"Ошибка при чтении недели: {e}")
                st.stop()

            raw_data = []
            end_week = 46 # Конец семестра (примерно)
            total_weeks = end_week - start_week + 1
            
            # Цикл по неделям
            for i, week in enumerate(range(start_week, end_week)):
                # Обновляем прогресс
                progress = (i + 1) / total_weeks
                progress_bar.progress(min(progress, 1.0))
                status_text.text(f"Сканирую неделю {week} из {end_week}...")
                
                # Запрос расписания на неделю
                params['weekNum'] = week
                if week != start_week: # Первый раз мы уже скачали выше
                    response = requests.get('https://rasp.rea.ru/Schedule/ScheduleCard', params=params, headers=headers)
                    soup = BeautifulSoup(response.text, 'html.parser')

                lessons = soup.find_all("a", class_="task")
                
                for lesson in lessons:
                    try:
                        raw_text = lesson['onclick'].split("'")
                        date = raw_text[1]
                        slot = raw_text[3]
                        
                        # Чистим текст
                        additional_data = " ".join(lesson.get_text(separator="|", strip=True).split())
                        parts = additional_data.split("|")
                        
                        # Иногда бывает меньше элементов, ставим заглушки
                        subj_name = parts[0] if len(parts) > 0 else "Нет названия"
                        subj_type = parts[1] if len(parts) > 1 else ""
                        location = parts[4] if len(parts) > 4 else ""
                        location = location.replace(" , пл. Основная", "")

                        # Запрос имени преподавателя
                        det_params = {'selection': group_name, 'date': date, 'timeSlot': slot}
                        det_resp = requests.get('https://rasp.rea.ru/Schedule/GetDetails', params=det_params, headers=headers)
                        det_soup = BeautifulSoup(det_resp.text, 'html.parser')
                        
                        teacher_div = det_soup.find('div', class_='element-info-body')
                        teacher_name = "Преподаватель не указан"
                        if teacher_div:
                            t_link = teacher_div.find('a')
                            if t_link:
                                teacher_name = t_link.get_text().replace("school ", "")
                        
                        raw_data.append({
                            "date": date,
                            "slot": slot,
                            "subject": subj_name,
                            "type": subj_type,
                            "location": location,
                            "teacher": teacher_name
                        })
                    except Exception:
                        continue # Если одна пара сломалась, идем дальше
                
                # Небольшая пауза, чтобы не дудосить сайт
                time.sleep(0.1)

            # 2. ГЕНЕРАЦИЯ КАЛЕНДАРЕЙ
            status_text.text("Генерирую файлы календаря...")
            
            cal_exams = Calendar()
            cal_lectures = Calendar()
            cal_seminars = Calendar()
            
            count = 0
            for item in raw_data:
                event = create_event(item, item['date'])
                if not event:
                    continue
                
                l_type = item['type'].lower()
                
                if any(x in l_type for x in ["экзамен", "зачет", "консультаци", "диф. зачет"]):
                    cal_exams.events.add(event)
                elif "лекция" in l_type:
                    cal_lectures.events.add(event)
                else:
                    cal_seminars.events.add(event)
                count += 1
            
            progress_bar.progress(100)
            status_text.text("✅ Готово!")
            st.success(f"Обработано пар: {count}")

            # 3. КНОПКИ СКАЧИВАНИЯ
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.download_button(
                    label="🔴 Скачать Экзамены",
                    data=get_ics_string(cal_exams),
                    file_name="reu_exams.ics",
                    mime="text/calendar"
                )
            
            with col2:
                st.download_button(
                    label="🔵 Скачать Лекции",
                    data=get_ics_string(cal_lectures),
                    file_name="reu_lectures.ics",
                    mime="text/calendar"
                )
                
            with col3:
                st.download_button(
                    label="🟢 Скачать Семинары",
                    data=get_ics_string(cal_seminars),
                    file_name="reu_seminars.ics",
                    mime="text/calendar"
                )

        except Exception as e:
            st.error(f"Произошла ошибка: {e}")
