import requests
import urllib.parse
import time
import json
from collections import defaultdict
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from ics import Calendar, Event
from zoneinfo import ZoneInfo

group_name = input("Введите номер группы (например, 15.27д-э01/24б): ")
group_name.lower()
print(f"Выбрана группа: {group_name}")
#group_name = "15.27д-э01/24б"

TZ = ZoneInfo("Europe/Moscow")
#Теперь создаем календарь
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

LESSON_DURATION = timedelta(minutes=90) #длительность пары равна 90 минут

count = 0


def run_parser():
    weekNum = '-1'
    encoded_group = urllib.parse.quote(group_name, safe='')
    headers = {
        'sec-ch-ua-platform': '"Windows"',
        'Referer': f'https://rasp.rea.ru/?q={encoded_group}',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 YaBrowser/25.12.0.0 Safari/537.36',
        'Accept': 'text/html, */*; q=0.01',
        'sec-ch-ua': '"Chromium";v="142", "YaBrowser";v="25.12", "Not_A Brand";v="99", "Yowser";v="2.5"',
        'sec-ch-ua-mobile': '?0',
    }

    params = {
        'selection': group_name,
        'weekNum': weekNum,
        'catfilter': '0',
    }

    response = requests.get('https://rasp.rea.ru/Schedule/ScheduleCard', params=params, headers=headers)

    timeTable_html = response.text 

    # Дальше подключаем BeautifulSoup
    timeTable = BeautifulSoup(timeTable_html, 'html.parser')
    weekNum = timeTable.find('input',id = 'weekNum')['value']
    raw_data = []
    #weekNum = weekData
    #print(weekData)
    
    for week in range(int(weekNum),46): #второе число в range это номер недели перед которой остановится парсинг
        print("Номер недели", week)
        params = {
            'selection': group_name,
            'weekNum': week,
            'catfilter': '0',
        }
        if(week != weekNum):
            response = requests.get('https://rasp.rea.ru/Schedule/ScheduleCard', params=params, headers=headers)
            timeTable_html = response.text 
            timeTable = BeautifulSoup(timeTable_html, 'html.parser')
        #############################lesson_data = [date,timeSlot,name,type,place,teacher_name]

        lessons = timeTable.find_all("a", class_="task")
        #print(table)
        
        for lesson in lessons:
            #сначала узнаем дату и номер пары
            raw_text = lesson['onclick'].split("'")
            lesson_data = [raw_text[1], raw_text[3]]
            #узнаем название, вид пары и местосщ
            additional_data = " ".join(lesson.get_text(separator = "|", strip = True).split())
            lesson_data.extend(additional_data.split("|"))
            lesson_data[4] = lesson_data[4].replace(" , пл. Основная", "")
            #Теперь узнаем препода, для этого надо пропарсить доп запрос
            params = {
                'selection': group_name,
                'date': lesson_data[0],
                'timeSlot': lesson_data[1],
            }
            response = requests.get('https://rasp.rea.ru/Schedule/GetDetails', params=params, headers=headers)
            details_html = response.text 
            details = BeautifulSoup(details_html, 'html.parser')
            teacher = details.find('div', class_= 'element-info-body')
            teacher = teacher.find('a')
            print()
            teacher_name = teacher.get_text().replace("school ",'')
            lesson_data.append(teacher_name)
            print(lesson_data)
            #time.sleep(0.5)
            raw_data.append(lesson_data)
            
    print()
    print(raw_data)
    # 2. Создаем словарь, где значение по умолчанию — пустой список
    # Структура будет: { "19.01.2026": [ {пара1}, {пара2} ], "24.01.2026": [...] }
    schedule_by_day = defaultdict(list)
    # 3. Множество (Set) для уникальных преподавателей
    # Set автоматически удаляет дубликаты
    unique_teachers = set()


    for lesson_data in raw_data:
        date = lesson_data[0]
        teacher = lesson_data[5] # Фамилия на 6-м месте (индекс 5)
            
        # Собираем красивый объект пары
        lesson_obj = {
            "slot": lesson_data[1],      # Номер пары
            "subject": lesson_data[2],   # Предмет
            "type": lesson_data[3],      # Лекция/Практика
            "location": lesson_data[4],  # Аудитория
            "teacher": teacher
        }
            
        # Кладем в словарь по дате
        schedule_by_day[date].append(lesson_obj)
            
        # Запоминаем преподавателя (если такого еще нет в списке)
        if teacher and teacher != "Преподаватель не указан":
            unique_teachers.add(teacher)

    # 4. Сохраняем результат в файл (наша база данных)
    with open("formatted_schedule.json", "w", encoding="utf-8") as f:
        json.dump(schedule_by_day, f, ensure_ascii=False, indent=4)
    with open("teachers_list.txt", "w", encoding="utf-8") as f:
        for teacher in sorted(unique_teachers):
            f.write(teacher + "\n")
            
    print(f" Сгруппировано дней: {len(schedule_by_day)}")
    print(f" Уникальных преподавателей: {len(unique_teachers)}")
    

def create_event(lesson, date_str):
    #Вспомогательная функция для создания события#
    slot = lesson['slot']
    
    if slot not in TIME_SLOTS:
        return None

    start_time_str = TIME_SLOTS[slot]
    full_start_dt_str = f"{date_str} {start_time_str}"
    
    try:
        # Сначала создаем "обычную" дату
        dt_naive = datetime.strptime(full_start_dt_str, "%d.%m.%Y %H:%M")
        
        # А потом жестко прикручиваем к ней часовой пояс
        # Теперь Python знает, что это 08:30 ИМЕННО в Москве
        start_dt = dt_naive.replace(tzinfo=TZ) # <--- 3. Магия здесь!
    except ValueError:
        return None # Если дата кривая

    end_dt = start_dt + LESSON_DURATION
    
    e = Event()
    e.name = f"{lesson['subject']} ({lesson['type']})"
    e.begin = start_dt
    e.end = end_dt
    e.location = lesson['location']
    e.description = f"👨‍🏫 {lesson['teacher']}\n📍 {lesson['location']}"
    return e



def save_ics(calendar, filename):
    with open(filename, "w", encoding="utf-8") as f:
        f.writelines(calendar.serialize_iter())
    print(f"✅ Создан файл: {filename} (Событий: {len(calendar.events)})")



if __name__ == "__main__":
    run_parser()
    # 1. Загружаем базу
    try:
        with open("formatted_schedule.json", "r", encoding="utf-8") as f:
            schedule_data = json.load(f)
    except FileNotFoundError:
        print("❌ Нет файла formatted_schedule.json. Сначала запусти парсер!")
        exit()

    # 2. Создаем ТРИ разных календаря
    cal_exams = Calendar()    # Для экзаменов и зачетов
    cal_lectures = Calendar() # Для лекций
    cal_seminars = Calendar() # Для практик и всего остального

    print("🚀 Генерация календарей...")

    for date_str, lessons in schedule_data.items():
        for lesson in lessons:
            event = create_event(lesson, date_str)
            if not event:
                continue
                
            l_type = lesson['type'].lower() # Приводим к нижнему регистру для проверки
            
            # ЛОГИКА СОРТИРОВКИ ПО ФАЙЛАМ
            if "экзамен" in l_type or "зачет" in l_type or "консультаци" in l_type or "диф. зачет" in l_type:
                cal_exams.events.add(event)
            elif "лекция" in l_type:
                cal_lectures.events.add(event)
            else:
                # Сюда попадут: Практические занятия, Лабораторные и т.д.
                cal_seminars.events.add(event)
                
            count += 1
    # 3. Сохраняем три файла
    save_ics(cal_exams, "reu_exams.ics")
    save_ics(cal_lectures, "reu_lectures.ics")
    save_ics(cal_seminars, "reu_seminars.ics")
    print(f"\nВсего обработано пар: {count}")
    
input("\nНажми Enter, чтобы выйти...")
