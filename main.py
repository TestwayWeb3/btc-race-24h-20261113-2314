import json
import sys

LOOKBACK = 90
FALL_BPS = 75
LOW_WIN = 30
LOW_AGE = 0
RECOVERY_BPS = 45
BOUNCE_BPS = 5
TAKE_BPS = 80
STOP_BPS = 25
TRAIL_BPS = 50
TRAIL_ARM_BPS = 70
POSITION_BPS = 8500
SLIP_BPS = 150
MAX_BUYS = 5
COOLDOWN = 45
PAUSE_BPS = 500
CAP_BPS = 180
LOW60_AGE = 0
DECAY1_BARS = 60
DECAY1_TRAIL = 25
DECAY2_BARS = 120
DECAY2_TRAIL = 15


def main():
    symbol = "CBBTC"
    price_scale = 5
    qty_scale = 8
    quote_scale = 6
    min_notional = 1000000
    warmup = 0
    closes = []
    entry_price = None
    peak_price = None
    pending_buy = None
    pending_sell = None
    order_no = 0
    buys_filled = 0
    last_exit_index = -1000000
    equity_peak = 0
    held_bars = 0
    bar_count = 0
    batch_count = 0
    out = sys.stdout
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        mtype = msg.get("type")
        if mtype == "hello":
            syms = msg.get("symbols") or []
            if syms:
                first = syms[0]
                symbol = first.get("symbol", symbol)
                price_scale = int(first.get("price_scale", price_scale))
                qty_scale = int(first.get("qty_scale", qty_scale))
            cap = msg.get("capital") or {}
            quote_scale = int(cap.get("quote_scale", quote_scale))
            fees = msg.get("fees") or {}
            min_notional = int(fees.get("min_notional_quote_units", min_notional))
            warmup = int(msg.get("warmup_bars") or 0)
            continue
        if mtype == "done":
            break
        if mtype != "batch":
            continue
        batch_count += 1
        seq = msg.get("seq", 0)
        orders = []
        for fill in msg.get("fills") or []:
            cid = fill.get("client_id", "")
            if cid == pending_buy:
                if fill.get("status") == "filled":
                    entry_price = int(fill.get("price", "0"))
                    peak_price = entry_price
                    buys_filled += 1
                pending_buy = None
            elif cid == pending_sell:
                if fill.get("status") == "filled":
                    entry_price = None
                    peak_price = None
                    last_exit_index = bar_count
                pending_sell = None
        account = msg.get("account") or {}
        cash = int(account.get("cash_quote_units", "0"))
        equity = int(account.get("equity_quote_units", "0"))
        if equity > equity_peak:
            equity_peak = equity
        pos_qty = 0
        pos_cost = 0
        for pos in account.get("positions") or []:
            if pos.get("symbol") == symbol:
                pos_qty = int(pos.get("qty", "0"))
                pos_cost = int(pos.get("cost_quote_units", "0"))
        close = None
        bar_high = None
        bar_low = None
        for bar in msg.get("bars") or []:
            if bar.get("symbol") == symbol:
                close = int(bar.get("c", "0"))
                bar_high = int(bar.get("h", "0"))
                bar_low = int(bar.get("l", "0"))
        if close is not None and close > 0:
            closes.append(close)
            bar_count += 1
            if entry_price is not None and pos_qty > 0 and bar_high:
                if peak_price is None or bar_high > peak_price:
                    peak_price = bar_high
        if pos_qty > 0 and entry_price is None and pending_buy is None and pos_cost > 0:
            expo = price_scale + qty_scale - quote_scale
            entry_price = pos_cost * (10 ** expo) // pos_qty
            peak_price = close if close else entry_price
        if pos_qty == 0 and pending_buy is None and pending_sell is None:
            entry_price = None
            peak_price = None
        if pos_qty > 0:
            held_bars += 1
        else:
            held_bars = 0
        if close is not None and batch_count > warmup:
            if pending_buy is None and pending_sell is None:
                if pos_qty > 0 and entry_price is not None and entry_price > 0:
                    eff_trail = TRAIL_BPS
                    if held_bars >= DECAY2_BARS:
                        eff_trail = DECAY2_TRAIL
                    elif held_bars >= DECAY1_BARS:
                        eff_trail = DECAY1_TRAIL
                    sell = False
                    if bar_high and bar_high * 10000 >= entry_price * (10000 + TAKE_BPS):
                        sell = True
                    elif bar_low and bar_low * 10000 <= entry_price * (10000 - STOP_BPS):
                        sell = True
                    elif (
                        peak_price is not None
                        and peak_price * 10000 >= entry_price * (10000 + TRAIL_ARM_BPS)
                        and close * 10000 <= peak_price * (10000 - eff_trail)
                    ):
                        sell = True
                    if sell:
                        order_no += 1
                        cid = "s" + str(order_no)
                        orders.append(
                            {
                                "side": "sell",
                                "client_id": cid,
                                "symbol": symbol,
                                "qty": str(pos_qty),
                                "max_slippage_bps": SLIP_BPS,
                            }
                        )
                        pending_sell = cid
                elif pos_qty == 0 and buys_filled < MAX_BUYS:
                    if bar_count - last_exit_index >= COOLDOWN and len(closes) > LOOKBACK:
                        paused = equity_peak > 0 and equity * 10000 < equity_peak * (10000 - PAUSE_BPS)
                        if not paused:
                            window = closes[-LOOKBACK - 1 : -1]
                            high = max(window)
                            prev = closes[-2]
                            recent = closes[-LOW_WIN - 1 : -1]
                            low = recent[0]
                            low_pos = 0
                            for j in range(1, len(recent)):
                                if recent[j] < low:
                                    low = recent[j]
                                    low_pos = j
                            wide = closes[-61:-1]
                            wide_low = wide[0]
                            wide_low_pos = 0
                            for j in range(1, len(wide)):
                                if wide[j] < wide_low:
                                    wide_low = wide[j]
                                    wide_low_pos = j
                            washed = (high - close) * 10000 >= FALL_BPS * high
                            bounced = (close - closes[-3]) * 10000 >= BOUNCE_BPS * closes[-3]
                            recovered = (close - low) * 10000 >= RECOVERY_BPS * low
                            aged = 60 - wide_low_pos >= LOW60_AGE
                            capped = False
                            if len(closes) > 120:
                                top = max(closes[-121:-1])
                                bottom = min(closes[-61:-1])
                                capped = (top - bottom) * 10000 >= CAP_BPS * top
                            if washed and bounced and recovered and aged and capped:
                                notional = cash * POSITION_BPS // 10000
                                if notional >= min_notional and notional > 0:
                                    order_no += 1
                                    cid = "b" + str(order_no)
                                    orders.append(
                                        {
                                            "side": "buy",
                                            "client_id": cid,
                                            "symbol": symbol,
                                            "notional_quote_units": str(notional),
                                            "max_slippage_bps": SLIP_BPS,
                                        }
                                    )
                                    pending_buy = cid
        reply = {"type": "reply", "seq": seq, "orders": orders}
        out.write(json.dumps(reply, separators=(",", ":")) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
