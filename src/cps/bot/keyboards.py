"""Inline keyboard builders — returns dicts for easy testing, converted to
InlineKeyboardMarkup at the handler level.

Each builder returns list[list[dict]] where dict has 'text' + ('url' or 'callback_data').
"""


def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _url_btn(text: str, url: str) -> dict:
    return {"text": text, "url": url}


def to_telegram_markup(keyboard: list[list[dict]]):
    """Convert our dict-based keyboard to telegram InlineKeyboardMarkup.

    Import telegram only here to keep rest of module dependency-free for testing.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for row in keyboard:
        buttons = []
        for btn in row:
            if "url" in btn:
                buttons.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
            else:
                buttons.append(InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
        rows.append(buttons)
    return InlineKeyboardMarkup(rows)


def build_buy_keyboard(buy_url: str) -> list[list[dict]]:
    return [[_url_btn("Buy on Amazon →", buy_url)]]


def build_price_report_keyboard(
    buy_url: str, asin: str, density: str,
) -> list[list[dict]]:
    """Price report buttons: Buy + detail toggle + set alert."""
    row1 = [_url_btn("Buy on Amazon →", buy_url)]
    row2 = []

    if density == "compact":
        row2.append(_btn("More detail ▼", f"density:standard:{asin}"))
    elif density == "detailed":
        row2.append(_btn("Less detail ▲", f"density:compact:{asin}"))
    else:  # standard
        row2.append(_btn("More detail ▼", f"density:detailed:{asin}"))

    row2.append(_btn("Set alert", f"alert:{asin}"))
    return [row1, row2]


def build_target_keyboard(asin: str, targets: list[dict]) -> list[list[dict]]:
    """Target price selection: preset buttons + custom + skip."""
    rows = []
    for t in targets:
        rows.append([_btn(t["label"], f"target:{asin}:{t['price']}")])
    rows.append([
        _btn("Custom price", f"target_custom:{asin}"),
        _btn("Skip", f"target:{asin}:skip"),
    ])
    return rows


def build_monitor_item_keyboard(asin: str) -> list[list[dict]]:
    return [
        [_btn("View details", f"view_detail:{asin}")],
        [_btn("Remove", f"remove_monitor:{asin}")],
    ]


def build_monitor_expiry_keyboard(asin: str) -> list[list[dict]]:
    return [[
        _btn("Remove", f"remove_monitor:{asin}"),
        _btn("Keep watching", f"keep_monitor:{asin}"),
    ]]


def build_deal_push_keyboard(
    buy_url: str, asin: str, category: str | None,
) -> list[list[dict]]:
    """Deal push: Buy + dismiss (spec Section 4.2)."""
    dismiss_data = f"dismiss_cat:{category}" if category else f"dismiss_asin:{asin}"
    return [
        [_url_btn("Buy on Amazon →", buy_url)],
        [_btn("Stop suggestions like this", dismiss_data)],
    ]


def build_reengagement_keyboard() -> list[list[dict]]:
    return [[
        _btn("Yes, restart deals", "reengage:yes"),
        _btn("No thanks", "reengage:no"),
    ]]


def build_downgrade_keyboard(new_frequency: str) -> list[list[dict]]:
    return [[
        _btn("Keep daily", "downgrade:keep"),
        _btn(f"{new_frequency.capitalize()} is fine", "downgrade:accept"),
    ]]
