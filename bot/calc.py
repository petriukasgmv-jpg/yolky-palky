import math
import re


def parse_calc_args(text):
    """Parse /calc arguments into numeric values."""
    args = {}
    labels = {
        "price": ("цена", "price", "продажа"),
        "cost": ("себестоимость", "себест", "cost", "материалы", "расходы"),
        "sales": ("кол-во", "количество", "штук", "sales"),
        "fee": ("комиссия", "комис", "fee", "процент"),
        "shipping": ("доставка", "доставки", "shipping"),
        "advertising": ("реклама", "рекламу", "ads", "advertising"),
        "tax": ("налог", "налоги", "tax"),
        "goal": ("цель", "goal"),
        "hours": ("часы", "часов", "время", "hours"),
    }
    for key, words in labels.items():
        for word in words:
            match = re.search(
                rf"{re.escape(word)}\s*[:=]\s*(\d[\d ]*)(?:[.,](\d+))?",
                text,
                re.IGNORECASE,
            )
            if match:
                whole = match.group(1).replace(" ", "")
                fraction = match.group(2) or ""
                args[key] = float(f"{whole}.{fraction}" if fraction else whole)
                break
    return args


def format_euro(value):
    if value == int(value):
        return f"€{value:,.0f}"
    return f"€{value:,.2f}".rstrip("0").rstrip(".")


def calculate(
    price,
    cost,
    sales=1,
    fee=0,
    shipping=0,
    goal=5000,
    advertising=0,
    tax=0,
    hours=0,
):
    """Calculate cash profit and separately validate owner workload.

    Owner labour is not deducted from cash profit. Its hours are checked
    against the 160-hour monthly capacity when ``hours`` is provided.
    """
    values = (price, cost, sales, fee, shipping, goal, advertising, tax, hours)
    if (
        any(value < 0 for value in values)
        or price <= 0
        or sales < 0
        or fee > 100
        or tax > 100
    ):
        return None

    fee_amount = price * fee / 100.0
    advertising_amount = advertising
    tax_amount = price * tax / 100.0
    unit_profit = (
        price
        - cost
        - fee_amount
        - shipping
        - advertising_amount
        - tax_amount
    )
    margin = unit_profit / price * 100
    monthly_profit = unit_profit * sales if sales else None
    sales_to_goal = math.ceil(goal / unit_profit) if unit_profit > 0 else None
    total_hours = hours * sales if hours and sales else 0

    warnings = []
    if unit_profit <= 0:
        warnings.append("Цена не покрывает денежные расходы.")
    if total_hours > 160:
        warnings.append("Нагрузка превышает 160 часов в месяц.")
    if hours and sales > 20:
        warnings.append("Больше 20 ручных заказов в месяц на одного человека.")

    return {
        "price": price,
        "cost": cost,
        "fee": fee,
        "fee_amount": fee_amount,
        "shipping": shipping,
        "advertising": advertising_amount,
        "tax": tax,
        "tax_amount": tax_amount,
        "unit_profit": unit_profit,
        "margin": margin,
        "goal": goal,
        "monthly_profit": monthly_profit,
        "sales_to_goal": sales_to_goal,
        "hours": hours,
        "total_hours": total_hours,
        "hours_violation": total_hours > 160,
        "manual_orders_violation": bool(hours and sales > 20),
        "warnings": warnings,
        "feasible": not warnings,
    }


def render_calc(result):
    lines = [
        "📊 Экономика одной продажи",
        "",
        f"💰 Цена продажи:       {format_euro(result['price'])}",
        f"🧱 Материалы/прочее:   -{format_euro(result['cost'])}",
    ]
    if result["fee"]:
        lines.append(
            f"🧾 Комиссия {result['fee']:.0f}%:     -{format_euro(result['fee_amount'])}"
        )
    if result["shipping"]:
        lines.append(f"📦 Доставка:            -{format_euro(result['shipping'])}")
    if result["advertising"]:
        lines.append(f"📣 Реклама:             -{format_euro(result['advertising'])}")
    if result["tax"]:
        lines.append(
            f"🧮 Налог {result['tax']:.1f}%:       -{format_euro(result['tax_amount'])}"
        )
    lines += [
        "──────────────────────",
        f"✅ Денежная прибыль:    {format_euro(result['unit_profit'])}",
        f"📈 Маржа:               {result['margin']:.1f}%",
    ]

    if result["hours"]:
        lines += [
            "",
            f"⏱ Время на заказ:      {result['hours']:.1f} ч",
            f"⏱ Всего часов:         {result['total_hours']:.1f} ч/мес",
        ]
        if result["hours_violation"]:
            lines.append("🔴 НЕВОЗМОЖНО: это больше лимита 160 ч/мес.")
        elif result["manual_orders_violation"]:
            lines.append("🔴 НЕВОЗМОЖНО: больше 20 ручных заказов на одного человека.")

    if result["monthly_profit"] is not None:
        lines += ["", f"📅 Прибыль за месяц:    {format_euro(result['monthly_profit'])}"]

    if result["sales_to_goal"] is not None:
        goal = result["goal"] or 5000
        lines += [
            "",
            f"🎯 Цель €{goal:,.0f} чистыми/мес",
            f"👀 Нужно продаж в месяц: {result['sales_to_goal']}",
        ]
    else:
        lines.append("🔴 Денежная прибыль с продажи ≤ 0 — цена ниже расходов.")

    lines.append("ℹ️ Труд владельца показан через часы и не вычтен повторно из денежной прибыли.")
    return "\n".join(lines)


HELP_TEXT = (
    "Как пользоваться:\n\n"
    "/calc цена:150 себестоимость:40\n"
    "/calc цена:150 себест:40 комиссия:10 доставка:5 реклама:3 налог:5\n"
    "/calc цена:150 себест:40 часы:20 кол-во:6 цель:5000\n\n"
    "Ключи: цена, себестоимость, комиссия %, доставка, реклама, налог %, "
    "кол-во, часы на заказ, цель."
)
