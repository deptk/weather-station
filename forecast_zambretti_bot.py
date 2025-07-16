import math  # модуль для математических операций (используется в функции to_sea_level_pressure)
import pandas as pd  # библиотека для работы с таблицами
import psycopg2  # модуль для подключения к PostgreSQL
from sqlalchemy import create_engine  # SQLAlchemy для подключения к БД через pandas
from zambretti_py import PressureData, Zambretti  # библиотека Замбретти для прогноза погоды
from datetime import datetime, timedelta  # для работы с временными метками
from telegram import Update  # для обработки сообщений Telegram
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes)  # фреймворк Telegram Bot API
import matplotlib.pyplot as plt  # для построения графиков
import matplotlib.dates as mdates  # форматирование временной оси графика
import io  # буфер изображений для отправки в Telegram

# Подключение к БД
DB_CONFIG = { 
             "dbname":"YOU_DB_NAME",
             "user":"YOU_USER",
             "password":"YOU_PASSWORD",
             "host":"localhost",
             "port":5432 
             }
ALTITUDE_M = 456  # м — высота станции над уровнем моря
WINDOW_HOURS = 3  # временное окно для анализа давления в часах

# Инициализация SQL Alchemy:
engine = create_engine(
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
        )

def get_pressure_history(hours=WINDOW_HOURS):
    # Получение истории давления и уличной температуры за последние 3 часа
    df = pd.read_sql(f"""
      SELECT created_at, pressure_hpa, outdoor_temp
      FROM weather_data
      WHERE created_at >= NOW() - INTERVAL '{hours} hours'
      ORDER BY created_at
    """, con=engine)
    return df

def to_sea_level_pressure(p_hpa, temp_c):
    # Перевод давления к уровню моря — оставлено на случай использования, но сейчас не применяется в логике прогнозов
    p_pa = p_hpa * 100.0
    g = 9.80665
    R_d = 287.05
    T_k = temp_c + 273.15
    p0 = p_pa * math.exp((g * ALTITUDE_M) / (R_d * T_k))
    return p0 / 100.0

async def periodic_job(context: ContextTypes.DEFAULT_TYPE):
    # Периодическая задача: вычисление прогноза погоды по Замбретти
    df = get_pressure_history(hours=WINDOW_HOURS * 2)
    if df.shape[0] < 6:
        return

    readings = list(zip(df['created_at'], df['pressure_hpa']))  # используем давление БЕЗ пересчёта к морю
    pd_data = PressureData(readings)  # создаём объект PressureData
    z = Zambretti()  # создаём объект прогноза
    last_temp = df['outdoor_temp'].iloc[-1]  # последняя температура
    forecast = z.forecast(elevation=ALTITUDE_M, temperature=last_temp, pressure_data=pd_data)  # прогноз

    # Сохраняем прогноз в БД
    conn = psycopg2.connect(**DB_CONFIG)
    with conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO weather_forecast (forecast) VALUES (%s)", (forecast,))
    conn.close()

# Telegram-команда для получения последнего сохранённого прогноза:
async def cmd_forecast(update, ctx):
    # Возвращает последний прогноз погоды
    conn = psycopg2.connect(**DB_CONFIG)
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT forecast FROM weather_forecast ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
    conn.close()
    await update.message.reply_text(row[0] if row else "Прогноз ещё не готов.")

# Telegram-команда /weather — текущее состояние погоды
async def cmd_weather(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    df = pd.read_sql(f"""
        SELECT created_at, outdoor_temp, pressure_hpa, pressure_mmhg
        FROM weather_data
        ORDER BY created_at DESC
        LIMIT 1
    """, con=engine)
    if df.empty:
        await update.message.reply_text("Нет данных о погоде.")
        return

    ts, temp, p_hpa, p_mmhg = df.iloc[0]
    p_sea = to_sea_level_pressure(p_hpa, temp)  # расчёт давления на уровне моря (не используется в логике)

    text = (
            f"📅 {ts:%Y-%m-%d %H:%M}\n"  # формат времени
            f"🌡 Температура: {temp:.1f} °C\n"
            f"📈 Давление: {p_hpa:.1f} гПа\n"
            f"📈 Давление: {p_mmhg:.1f} мм рт. ст."
            )
    await update.message.reply_text(text)

# Telegram-команда /pressure — график давления за последние 3 часа
async def cmd_pressure(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    df = get_pressure_history(hours=WINDOW_HOURS)
    if df.empty:
        await update.message.reply_text("Нет данных за последние 3 часа.")
        return

    fig, ax = plt.subplots()
    ax.plot(df['created_at'], df['pressure_hpa'], marker='o')  # график давления
    ax.grid()
    formatter = mdates.DateFormatter('%H:%M')  # формат оси времени
    ax.xaxis.set_major_formatter(formatter)
    fig.autofmt_xdate()

    delta = df['pressure_hpa'].iloc[-1] - df['pressure_hpa'].iloc[0]  # разница давления

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    buf.name = 'pressure.png'
    plt.close(fig)

    await update.message.reply_photo(buf, caption=f"📈 Давление за последние 3 часа\nΔ = {delta:.1f} гПа\n{p_hpa:.1f} гПа")

# Telegram-команда /forecast_now — расчёт прогноза прямо сейчас
async def cmd_forecast_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    df = get_pressure_history(hours=WINDOW_HOURS * 2)  # берём последние 6 часов
    if df.shape[0] < 6:
        await update.message.reply_text("Недостаточно данных для прогноза (нужно ≥6 точек).")
        return

    readings = list(zip(df['created_at'], df['pressure_hpa']))  # формируем список (время, давление)
    pd_data = PressureData(readings)  # объект данных для zambretti_py
    z = Zambretti()  # объект прогноза
    last_temp = df['outdoor_temp'].iloc[-1]  # последняя температура
    forecast = z.forecast(elevation=ALTITUDE_M, temperature=last_temp, pressure_data=pd_data)  # расчёт прогноза

    await update.message.reply_text(f"🌤 Прогноз на ближайшее время: {forecast}")  # отправка в Telegram

def main():
    # Главная функция запуска Telegram-бота
    app = ApplicationBuilder().token("XXXXXXXXXX:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX").build()
    app.add_handler(CommandHandler("weather", cmd_weather))  # команда /weather
    app.add_handler(CommandHandler("forecast", cmd_forecast))  # команда /forecast
    app.add_handler(CommandHandler("pressure", cmd_pressure))  # команда /pressure
    app.add_handler(CommandHandler("forecast_now", cmd_forecast_now))  # команда /forecast_now — НОВАЯ
    
    # Регистрируем periodic_job на запуск раз в час
    interval_seconds = 3600
    app.job_queue.run_repeating(
        periodic_job,
        interval=interval_seconds,
        first=10  # запуск через 10 сек после старта (можно изменить или убрать)
    )
    
    app.run_polling()  # запуск опроса Telegram

if __name__ == "__main__":
    main()
