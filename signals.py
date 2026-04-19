from technical_indicators import safe_pos


def get_tech_signal(
    close,
    chgPct,
    amp,
    volume_ok=None,
    volume=None,
    prev_volume=None,
    prev2_volume=None,
    k=None,
    d=None,
    prev_k=None,
    prev_d=None,
    bb_pct=None,
    bias6=None,
    bias18=None,
    bias50=None,
    bias6_min=None,
    bias6_max=None,
    bias18_min=None,
    bias18_max=None,
    bias50_min=None,
    bias50_max=None,
    ma18=None,
    prev_ma18=None,
    prev_close=None,
    k_trend=None,
    d_trend=None,
):
    reasons = []

    if close is None:
        return {
            'signal': '等待觀察',
            'reason': '缺少收盤價資料',
            'signal_text': '資料不足',
        }

    # === KD 判斷 ===
    if None in (k, d, prev_k, prev_d):
        kd_gold_cross = False
        kd_dead_cross = False
    else:
        kd_gold_cross = prev_k <= prev_d and k > d
        kd_dead_cross = prev_k >= prev_d and k < d

    kd_low = (k is not None and d is not None and k < 30 and d < 30)
    kd_high = (k is not None and d is not None and k > 80 and d > 80)
    kd_mid = (k is not None and d is not None and 30 <= k <= 80 and 30 <= d <= 80)

    kd_turn_strong = False
    kd_turn_weak = False
    if prev_k is not None and k is not None:
        kd_turn_strong = k > prev_k
        kd_turn_weak = k < prev_k

    if kd_gold_cross:
        reasons.append('KD黃金交叉')
    if kd_dead_cross:
        reasons.append('KD死亡交叉')
    if kd_low:
        reasons.append('KD位於低檔區')
    if kd_high:
        reasons.append('KD位於高檔區')

    # technical_indicators.py 的 kd_trend 會回傳箭頭
    k_trend_up = k_trend in ('↑', '↗', 'up')
    k_trend_down = k_trend in ('↓', '↘', 'down')

    if k_trend_up and not kd_gold_cross:
        reasons.append('KD動能走強')
    if k_trend_down and not kd_dead_cross:
        reasons.append('KD動能轉弱')

    # === 成交量判斷 ===
    # 新版：volume > prev_volume > prev2_volume
    # 舊版：若只有 volume_ok，則退回舊判斷
    volume_2day_up = False
    volume_up = False
    volume_not_bad = False

    if None not in (volume, prev_volume, prev2_volume):
        volume_2day_up = volume > prev_volume > prev2_volume
        volume_up = volume > prev_volume
        volume_not_bad = volume >= prev_volume * 0.9
    else:
        volume_2day_up = bool(volume_ok)
        volume_up = bool(volume_ok)
        volume_not_bad = bool(volume_ok)

    if volume_2day_up:
        reasons.append('成交量連續兩天放大')
    elif volume_up:
        reasons.append('成交量放大')
    elif volume_not_bad:
        reasons.append('成交量維持')

    # === 股價 / 趨勢 ===
    price_up = chgPct is not None and chgPct > 0
    price_down = chgPct is not None and chgPct < 0
    price_flat = chgPct is not None and abs(chgPct) < 0.5

    above_ma18 = ma18 is not None and close > ma18
    below_ma18 = ma18 is not None and close < ma18

    ma18_break = (
        ma18 is not None and prev_ma18 is not None and prev_close is not None
        and prev_close <= prev_ma18 and close > ma18
    )

    ma18_fall_break = (
        ma18 is not None and prev_ma18 is not None and prev_close is not None
        and prev_close >= prev_ma18 and close < ma18
    )

    if price_up:
        reasons.append('股價上漲')
    elif price_down:
        reasons.append('股價下跌')
    if price_flat:
        reasons.append('股價接近橫盤整理')

    if above_ma18:
        reasons.append('股價位於月線之上')
    elif below_ma18:
        reasons.append('股價位於月線之下')

    if ma18_break:
        reasons.append('股價突破月線')
    if ma18_fall_break:
        reasons.append('股價跌破月線')

    # === 布林 ===
    # bb_pct 視為 0~100
    bb_low = bb_pct is not None and bb_pct < 20
    bb_mid_low = bb_pct is not None and 20 <= bb_pct <= 50
    bb_mid = bb_pct is not None and 35 <= bb_pct <= 80
    bb_high = bb_pct is not None and bb_pct > 80
    bb_overheat = bb_pct is not None and bb_pct > 95

    if bb_low:
        reasons.append('接近布林下緣')
    elif bb_high:
        reasons.append('位於布林高檔區')
    elif bb_mid:
        reasons.append('布林位於中性偏強區')

    if bb_overheat:
        reasons.append('接近布林上緣過熱')

    # === Bias 輔助 ===
    bias6_pos = safe_pos(bias6, bias6_min, bias6_max)
    bias18_pos = safe_pos(bias18, bias18_min, bias18_max)
    bias50_pos = safe_pos(bias50, bias50_min, bias50_max)

    low_count = 0
    high_count = 0
    for pos in (bias6_pos, bias18_pos, bias50_pos):
        if pos is None:
            continue
        if pos < 0.2:
            low_count += 1
        elif pos > 0.8:
            high_count += 1

    bias_low_zone = low_count >= 2
    bias_high_zone = high_count >= 2

    if bias_low_zone:
        reasons.append('乖離處於相對低檔')
    if bias_high_zone:
        reasons.append('乖離處於相對高檔')

    # === 規則判斷 ===
    # 1) 明確買進：要強一點，仍保留連續量兩天
    if (
        volume_2day_up
        and price_up
        and kd_gold_cross
        and (above_ma18 or ma18_break)
        and not bb_overheat
    ):
        return {
            'signal': '買進',
            'reason': '量價齊揚，KD黃金交叉，技術面轉強',
            'signal_text': ' / '.join(reasons),
        }

    # 2) 低檔轉強：允許單日量增或量能不差，不再強綁連續兩天放量
    if (
        not price_down
        and (volume_2day_up or volume_up or volume_not_bad)
        and (kd_low or kd_gold_cross or k_trend_up or kd_turn_strong)
        and (bb_low or bb_mid_low or bias_low_zone)
    ):
        return {
            'signal': '觀察再買進',
            'reason': '低檔有量能回補，出現轉強跡象，但尚待確認',
            'signal_text': ' / '.join(reasons),
        }

    # 3) 趨勢續強股：像 2404 這類容易落在這裡
    if (
        not price_down
        and above_ma18
        and (k_trend_up or kd_turn_strong or kd_gold_cross)
        and bb_mid
        and (volume_up or volume_not_bad)
        and not bb_overheat
        and not bias_high_zone
    ):
        return {
            'signal': '觀察再買進',
            'reason': '股價維持月線之上，KD動能偏多，屬趨勢續強整理',
            'signal_text': ' / '.join(reasons),
        }

    # 4) 明確賣出：保留較嚴格條件
    if (
        volume_2day_up
        and price_down
        and kd_dead_cross
        and (kd_high or bb_high or bb_overheat or ma18_fall_break or below_ma18)
    ):
        return {
            'signal': '賣出',
            'reason': '高檔轉弱，量增下跌，技術面轉空',
            'signal_text': ' / '.join(reasons),
        }

    # 5) 高檔轉弱：允許量能沒有連兩天放大
    if (
        (volume_2day_up or volume_up or volume_not_bad)
        and (kd_high or bb_high or bias_high_zone)
        and (kd_dead_cross or kd_turn_weak or k_trend_down)
        and not (ma18_fall_break and price_down)
    ):
        return {
            'signal': '觀察再賣出',
            'reason': '股價位於高檔區，動能轉弱，宜留意賣點',
            'signal_text': ' / '.join(reasons),
        }

    # 6) 中性盤整
    return {
        'signal': '等待觀察',
        'reason': '價格、量能、KD與布林尚未形成明確方向',
        'signal_text': ' / '.join(reasons) if reasons else '等待觀察',
    }