import re


def parse_calc_args(text):
    """Parse /calc arguments. Returns dict or None.

    Supported keys: цена/price, себестоимость/cost,
    кол-во/sales/штук, цель/goal, комиссия/fee.
    """
    args = {}
    for key, label in (
        ("price", ("цена", "price", "продажа")),
        ("cost", ("себестоимость", "себест", "cost", "материалы", "расходы")),
        ("sales", ("кол-во", "количество", "штук", "sales")),
        ("fee", ("комиссия", "комис", "fee", "процент")),
        ("shipping", ("доставка", "доставки", "shipping")),
        ("goal", ("цель", "goal")),
    ):
        m = None
        for word in label:
            m = re.search(
                rf"{word}\s*[:=]\s*(\d[\d ]*)",
                text,
                re.IGNORECASE,
            )
            if m:
                break
        if m:
            args[key] = float(m.group(1).replace(" ", "").replace(",", "."))
    return args


def format_euro(value):
    return f"€{value:,.2f}".replace(",0", "")


def calculate(price, cost, sales=1, fee=0, shipping=0, goal=5000):
    """Return a dict of economics."""

    if price <= 0:
        return None

    fee_amount = price * fee / 100.0 if fee else 0
    unit_profit = price - cost - fee_amount - shipping
    margin = (unit_profit / price * 100) if price else 0

    result = {
        "price": price,
        "cost": cost,
        "fee": fee,
        "fee_amount": fee_amount,
        "shipping": shipping,
        "unit_profit": unit_profit,
        "margin": margin,
    }

    if sales:
        monthly_profit = unit_profit * sales
    else:
        monthly_profit = None

    result["monthly_profit"] = monthly_profit

    if unit_profit > 0:
        sales_to_goal = goal / unit_profit
        result["sales_to_goal"] = sales_to_goal
    else:
        result["sales_to_goal"] = None

    return result


def render_calc(result):
    """Render the economics as a readable message."""

    lines = []
    lines.append("📊 Экономика одной продажи")
    lines.append("")
    lines.append(f"💰 Цена продажи:       {format_euro(result['price'])}")
    if result["fee"]:
        lines.append(
            f"🧾 Комиссия {result['fee']:.0f}%:     -{format_euro(result['fee_amount'])}"
        )
    if result["shipping"]:
        lines.append(f"📦 Доставка:            -{format_euro(result['shipping'])}")
    lines.append(f"🧱 Себестоимость:       -{format_euro(result['cost'])}")
    lines.append("──────────────────────")
    unit_profit = result["unit_profit"]
    lines.append(f"✅ Прибыль с продажи:   {format_euro(unit_profit)}")
    lines.append(f"📈 Маржа:               {result['margin']:.1f}%")

    monthly = result.get("monthly_profit")
    if monthly is not None:
        lines.append("")
        lines.append(f"📅 Прибыль за месяц:    {format_euro(monthly)}")

    sales_to_goal = result.get("sales_to_goal")
    if sales_to_goal is not None:
        lines.append("")
        lines.append("🎯 Цель €5 000 чистыми/мес")
        lines.append(f"👀 Нужно продаж в месяц: ~{sales_to_goal:,.0f}")
        if sales_to_goal > 200:
            lines.append("⚠️ Больше 200 продаж/мес — высокая нагрузка.")
        elif sales_to_goal <= 10:
            lines.append("✅ До 10 продаж/мес — реалистично для старта.")
        elif sales_to_goal <= 30:
            lines.append("🟡 10–30 продаж/мес — реально при постоянной работе.")
        else:
            lines.append("🟠 30–200 продаж/мес — потребуется поток/ассистенты.")
    else:
        lines.append("🔴 Прибыль с продажи ≤ 0 — цена ниже себестоимости.")

    return "\n".join(lines)


HELP_TEXT = (
    "Как пользоваться:\n\n"
    "/calc цена:150 себестоимость:40\n"
    "/calc цена:150 себест:40 комиссия:10 доставка:5\n"
    "/calc цена:250 себест:50 кол-во:20\n\n"
    "Ключи: цена (price), себестоимость (cost/себест), "
    "комиссия % (fee), доставка (shipping), кол-во (sales), цель (goal)."
)