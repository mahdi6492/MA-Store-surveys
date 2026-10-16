import os
import json
import logging
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
DATA_FILE = "orders.json"

SERVICES = {
    "qmee": ("Qmee", 35000),
    "lifepoints": ("LifePoints", 45000),
}

PAYMENTS = {
    "sham": "شام كاش\nمعرّف الدفع:\nc08f32af6968e8476bc434a36d868ef8",
    "syriatel": "سيريتل كاش\nرقم الدفع: 0995614942",
}

def load_orders():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"orders": [], "next_id": 1001}

def save_orders(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Qmee — 35,000 ل.س", callback_data="service:qmee")],
        [InlineKeyboardButton("LifePoints — 45,000 ل.س", callback_data="service:lifepoints")],
        [InlineKeyboardButton("💳 طرق الدفع", callback_data="payments")],
        [InlineKeyboardButton("📦 طلباتي", callback_data="myorders")],
        [InlineKeyboardButton("📞 التواصل مع الإدارة", callback_data="contact")],
    ])

def order_buttons(order_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد الدفع", callback_data=f"paid:{order_id}"),
            InlineKeyboardButton("❌ رفض الطلب", callback_data=f"reject:{order_id}"),
        ],
        [InlineKeyboardButton("⏳ قيد التجهيز", callback_data=f"processing:{order_id}")],
        [InlineKeyboardButton("📦 تم التسليم", callback_data=f"delivered:{order_id}")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً في متجر MA Store Surveys!\n\n"
        "اختر الخدمة التي تريد حجزها:",
        reply_markup=main_menu(),
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data.startswith("service:"):
        key = data.split(":", 1)[1]
        name, price = SERVICES[key]
        context.user_data["service"] = key
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 حجز الخدمة", callback_data="reserve")],
            [InlineKeyboardButton("↩️ رجوع", callback_data="home")],
        ])
        await query.edit_message_text(
            f"🔹 الخدمة: {name}\n"
            f"💰 السعر: {price:,} ليرة سورية\n"
            "⏳ مدة التجهيز: حسب توفر الخدمة\n\n"
            "اضغط حجز الخدمة للمتابعة.",
            reply_markup=keyboard,
        )

    elif data == "reserve":
        key = context.user_data.get("service")
        if key not in SERVICES:
            await query.edit_message_text(
                "اختر الخدمة من القائمة الرئيسية أولاً.",
                reply_markup=main_menu(),
            )
            return
        context.user_data["stage"] = "payment"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("شام كاش", callback_data="pay:sham")],
            [InlineKeyboardButton("سيريتل كاش", callback_data="pay:syriatel")],
        ])
        await query.edit_message_text(
            "اختر طريقة الدفع:",
            reply_markup=keyboard,
        )

    elif data.startswith("pay:"):
        method = data.split(":", 1)[1]
        if method not in PAYMENTS:
            return
        context.user_data["payment_method"] = method
        context.user_data["stage"] = "proof"
        await query.edit_message_text(
            f"💳 {PAYMENTS[method]}\n\n"
            "حوّل المبلغ الصحيح، ثم أرسل صورة إثبات التحويل هنا.\n"
            "سيتم مراجعة الدفع يدوياً قبل تأكيد الطلب."
        )

    elif data == "payments":
        await query.edit_message_text(
            "💳 طرق الدفع المتاحة:\n\n"
            + PAYMENTS["sham"] + "\n\n" + PAYMENTS["syriatel"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ رجوع", callback_data="home")]
            ]),
        )

    elif data == "home":
        await query.edit_message_text(
            "اختر الخدمة التي تريد حجزها:",
            reply_markup=main_menu(),
        )

    elif data == "contact":
        await query.edit_message_text(
            "📞 للتواصل مع الإدارة، أرسل رسالة إلى حساب الإدارة على تلغرام.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ رجوع", callback_data="home")]
            ]),
        )

    elif data == "myorders":
        data_store = load_orders()
        mine = [
            o for o in data_store["orders"]
            if o["user_id"] == user.id
        ]
        if not mine:
            text = "ليس لديك طلبات مسجلة حالياً."
        else:
            text = "📦 طلباتك:\n\n" + "\n".join(
                f"#{o['id']} — {o['service']} — {o['status']}"
                for o in mine[-10:]
            )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ رجوع", callback_data="home")]
            ]),
        )

    elif ":" in data:
        action, order_id = data.split(":", 1)
        if action not in {"paid", "reject", "processing", "delivered"}:
            return
        if user.id != ADMIN_ID:
            await query.answer("هذا الزر خاص بالإدارة.", show_alert=True)
            return

        store = load_orders()
        order = next(
            (o for o in store["orders"] if str(o["id"]) == order_id),
            None,
        )
        if not order:
            await query.answer("الطلب غير موجود.", show_alert=True)
            return

        statuses = {
            "paid": "تم تأكيد الدفع",
            "reject": "مرفوض",
            "processing": "قيد التجهيز",
            "delivered": "تم التسليم",
        }
        order["status"] = statuses[action]
        save_orders(store)

        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=f"📦 تحديث طلبك #{order['id']}:\nالحالة: {order['status']}",
            )
        except Exception:
            log.exception("Could not notify customer")

        await query.edit_message_reply_markup(
            reply_markup=order_buttons(order["id"])
        )
        await query.message.reply_text(
            f"تم تحديث الطلب #{order['id']} إلى: {order['status']}"
        )

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("stage") != "proof":
        await update.message.reply_text(
            "اختر الخدمة أولاً من القائمة الرئيسية باستخدام /start."
        )
        return

    user = update.effective_user
    key = context.user_data.get("service")
    method = context.user_data.get("payment_method")

    if key not in SERVICES or method not in PAYMENTS:
        await update.message.reply_text("حدث خطأ. ابدأ من جديد باستخدام /start.")
        return

    if update.message.photo:
        proof = update.message.photo[-1].file_id
    elif update.message.document:
        proof = update.message.document.file_id
    else:
        await update.message.reply_text("أرسل صورة إثبات الدفع من فضلك.")
        return

    store = load_orders()
    order_id = store["next_id"]
    store["next_id"] += 1

    name, price = SERVICES[key]
    order = {
        "id": order_id,
        "user_id": user.id,
        "username": user.username or "",
        "service": name,
        "price": price,
        "payment_method": method,
        "proof_file_id": proof,
        "status": "بانتظار مراجعة الدفع",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store["orders"].append(order)
    save_orders(store)
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ استلمنا طلبك رقم #{order_id}.\n"
        "📌 الحالة: بانتظار مراجعة الدفع.\n"
        "سيتم إعلامك عند تحديث الحالة."
    )

    keyboard = order_buttons(order_id)
    caption = (
        f"📥 طلب جديد #{order_id}\n"
        f"الخدمة: {name}\n"
        f"السعر: {price:,} ليرة سورية\n"
        f"طريقة الدفع: {method}\n"
        f"الزبون: @{user.username or 'بدون اسم مستخدم'}\n"
        f"معرّف الزبون: {user.id}\n"
        "الحالة: بانتظار مراجعة الدفع"
    )

    try:
        if update.message.photo:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=proof,
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=proof,
                caption=caption,
                reply_markup=keyboard,
            )
    except Exception:
        log.exception("Could not send order to admin")
        await update.message.reply_text(
            "تم تسجيل الطلب، لكن تعذر إرسال إشعار للإدارة. يرجى التواصل مع الإدارة."
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.ALL,
            receive_proof,
        )
    )
    app.run_polling()

if __name__ == "__main__":
    main()
