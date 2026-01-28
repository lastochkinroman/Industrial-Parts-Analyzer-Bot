import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from mistralai.client import MistralClient

from config import Config
from bot_core import analyzer
from excel_generator import report_generator
from database import db_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

mistral_client = MistralClient(api_key=Config.MISTRAL_API_KEY)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🏭 *Industrial Parts Analyzer Bot*

Я помогаю анализировать цены на промышленные запчасти.

*Как использовать:*
1. Отправьте каталожные номера через запятую:
   `BP-12345-67890, MC-54321-09876`

2. Укажите поставщиков (опционально):
   `!industrialsupply` - IndustrialSupply.ru
   `!machineparts` - MachineParts.com
   `!factorystock` - FactoryStock.eu

*Примеры:*
- `BP-12345-67890` - поиск у всех поставщиков
- `BP-12345-67890 !industrialsupply !machineparts` - только у двух
- `BP-12345-67890, GR-98765-43210 !factorystock` - две запчасти, один поставщик

Результат: Excel-отчет с анализом цен и рекомендациями AI.
    """

    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 *Доступные команды:*

/start - Начало работы
/help - Эта справка
/history [номер] - История цен за 30 дней
/stats - Статистика поисков

*Поставщики:*
• IndustrialSupply.ru - Широкий ассортимент
• MachineParts.com - Европейские бренды
• FactoryStock.eu - Быстрая доставка

*Формат номеров:*
BP-xxxxx-xxxxx - Подшипники
MC-xxxxx-xxxxx - Муфты
GR-xxxxx-xxxxx - Редукторы
    """

    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text

    logger.info(f"Message from {user.id}: {message_text}")

    await update.message.chat.send_action(action="typing")

    try:
        part_numbers, suppliers = analyzer.extract_search_params(message_text)

        if not part_numbers:
            await update.message.reply_text(
                "❌ Не найдены каталожные номера запчастей.\n"
                "Пример: `BP-12345-67890, MC-54321-09876`",
                parse_mode='Markdown'
            )
            return

        supplier_names = [
            analyzer.supplier_mapping.get(s, s)
            for s in suppliers
        ]

        status_msg = await update.message.reply_text(
            f"🔍 *Поиск информации...*\n"
            f"• Запчастей: {len(part_numbers)}\n"
            f"• Поставщики: {', '.join(supplier_names)}\n"
            f"⏳ Ожидайте...",
            parse_mode='Markdown'
        )

        search_results = await analyzer.search_parts(part_numbers, suppliers)

        if not search_results:
            await status_msg.edit_text("❌ Не удалось найти информацию по указанным запчастям.")
            return

        analysis_results = []
        for part_data in search_results:
            analysis = analyzer.analyze_prices(part_data)
            if analysis:
                analysis_results.append(analysis)

        ai_analyses = await generate_ai_analysis(analysis_results)

        user_info = {
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name
        }

        report_path = report_generator.generate_report(analysis_results, user_info)

        if ai_analyses:
            analysis_text = "🤖 *AI Анализ цен:*\n\n"
            for ai_analysis in ai_analyses[:3]:
                analysis_text += f"*{ai_analysis['part_number']}*\n"
                analysis_text += f"{ai_analysis['analysis']}\n\n"

            await update.message.reply_text(analysis_text, parse_mode='Markdown')

        with open(report_path, 'rb') as report_file:
            await update.message.reply_document(
                document=report_file,
                filename=f"parts_analysis_{user.id}.xlsx",
                caption=f"📊 Отчет по {len(analysis_results)} запчастям"
            )

        await status_msg.delete()

        log_search_request(user, part_numbers, suppliers, len(analysis_results))

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже."
        )

async def generate_ai_analysis(analysis_results):
    if not Config.MISTRAL_API_KEY:
        return []

    analyses = []

    for result in analysis_results[:5]:
        try:
            prompt = f"""
            Проанализируй данные по промышленной запчасти:

            Каталожный номер: {result['part_number']}
            Наименование: {result['name']}
            Бренды: {', '.join(result['brands'])}

            Цены от поставщиков:
            {chr(10).join([f"- {p['supplier_name']}: {p['price']} руб., {p['delivery']} дней ({p['brand']})" for p in result['all_prices']])}

            Минимальная цена: {result['min_price']['price']} руб. ({result['min_price']['supplier_name']})
            Медианная цена: {result['median_price']['price']} руб. ({result['median_price']['supplier_name']})

            Сделай краткий анализ (3-4 предложения) с рекомендацией по выбору оптимального варианта.
            Учитывай соотношение цена/срок поставки/бренд.
            """

            response = mistral_client.chat(
                model="mistral-medium",
                messages=[
                    {"role": "system", "content": "Ты эксперт по промышленным запчастям."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300
            )

            analyses.append({
                'part_number': result['part_number'],
                'analysis': response.choices[0].message.content
            })

        except Exception as e:
            logger.error(f"Mistral AI error: {e}")
            analyses.append({
                'part_number': result['part_number'],
                'analysis': "AI анализ временно недоступен."
            })

    return analyses

def log_search_request(user, part_numbers, suppliers, results_count):
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        query = """
        INSERT INTO search_requests
        (telegram_user_id, telegram_username, part_numbers, suppliers, results_count)
        VALUES (%s, %s, %s, %s, %s)
        """

        import json
        cursor.execute(query, (
            user.id,
            user.username,
            json.dumps(part_numbers),
            json.dumps(suppliers),
            results_count
        ))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"Error logging search request: {e}")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        await update.message.reply_text(
            "Укажите каталожный номер: `/history BP-12345-67890`",
            parse_mode='Markdown'
        )
        return

    part_number = args[0].upper()

    try:
        history = db_manager.get_part_history(part_number)

        if not history:
            await update.message.reply_text(
                f"📭 История цен для {part_number} не найдена."
            )
            return

        response = f"📈 *История цен: {part_number}*\n\n"

        from collections import defaultdict
        by_date = defaultdict(list)

        for record in history[:10]:
            by_date[record['date']].append(record)

        for date, records in list(by_date.items())[:5]:
            response += f"*{date}*\n"
            for record in records:
                response += f"• {record['supplier_name']}: {record['price']} руб. ({record['delivery_days']} дн.)\n"
            response += "\n"

        await update.message.reply_text(response, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in history command: {e}")
        await update.message.reply_text("⚠️ Ошибка при получении истории.")

def main():
    application = Application.builder().token(Config.TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Industrial Parts Analyzer Bot запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
