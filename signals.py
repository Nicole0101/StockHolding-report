from technical_indicators import safe_pos


def get_tech_signal(
    close, chgPct, amp, volume_ok,
    k, d, prev_k, prev_d,
    bb_pct,
    bias6, bias18, bias50,
    bias6_min, bias6_max,
    bias18_min, bias18_max,
    bias50_min, bias50_max,
    ma18, prev_ma18, prev_close,
    k_trend=None,
    d_trend=None,
):
    reasons = []

    # === KD 安全判斷 ===
    if None in (k, d, prev_k, prev_d):
        kd_gold_cross = False
        kd_dead_cross = False
    else:
        kd_gold_cross = prev_k <= prev_d and k > d
        kd_dead_cross = prev_k >= prev_d and k < d

    # === 月線突破 ===
    _ma18_break = (
        ma18 is not None and prev_ma18 is not None
        and prev_close <= prev_ma18 and close > ma18
    )

    # === Bias ===
    bias6_pos = safe_pos(bias6, bias6_min, bias6_max)
    bias18_pos = safe_pos(bias18, bias18_min, bias18_max)
    bias50_pos = safe_pos(bias50, bias50_min, bias50_max)

    # === KD score ===
    kd_score = 0
    if kd_gold_cross and k is not None and k < 35:
        kd_score = 2
        reasons.append('KD低檔黃金交叉')
    elif kd_gold_cross:
        kd_score = 1
        reasons.append('KD黃金交叉')
    elif kd_dead_cross and k is not None and k > 75:
        kd_score = -2
        reasons.append('KD高檔死亡交叉')
    elif kd_dead_cross:
        kd_score = -1
        reasons.append('KD死亡交叉')

    # === 價量 ===
    vol_price_score = 0
    if chgPct > 0 and volume_ok:
        vol_price_score = 2
        reasons.append('價漲量增')
    elif chgPct > 0:
        vol_price_score = 1
        reasons.append('上漲但量能普通')
    elif chgPct < 0 and volume_ok:
        vol_price_score = -2
        reasons.append('價跌量增')
    elif chgPct < 0:
        vol_price_score = -1
        reasons.append('股價走弱')

    # === 布林 ===
    bb_score = 0
    if bb_pct is not None:
        if bb_pct < 20:
            bb_score = 1
            reasons.append('接近布林下緣')
        elif bb_pct > 95:
            bb_score = -1
            reasons.append('接近布林上緣過熱')
        elif bb_pct > 80:
            bb_score = -0.5
            reasons.append('位於布林高檔區')

    # === Bias ===
    bias_score = 0
    if bias6_pos is not None:
        if bias6_pos < 0.2:
            bias_score += 1
        elif bias6_pos > 0.8:
            bias_score -= 1

    if bias18_pos is not None:
        if bias18_pos < 0.2:
            bias_score += 1
        elif bias18_pos > 0.8:
            bias_score -= 1

    if bias50_pos is not None:
        if bias50_pos < 0.2:
            bias_score += 0.5
        elif bias50_pos > 0.8:
            bias_score -= 0.5

    # === 趨勢 ===
    trend_score = 0
    if ma18 is not None and close > ma18:
        trend_score += 1

    # === 總分 ===
    total_score = kd_score + vol_price_score + bb_score + bias_score + trend_score

    if total_score >= 3:
        signal_result = '買進訊號'
        strategy = '買入'
        reason = '技術面轉強'
    elif total_score <= -3:
        signal_result = '賣出訊號'
        strategy = '出貨'
        reason = '技術面轉弱'
    else:
        signal_result = '觀望訊號'
        strategy = '觀察'
        reason = '方向不明'

    return {
        'signal_result': signal_result,
        'strategy': strategy,
        'reason': reason,
        'signal_text': ' / '.join(reasons) if reasons else '觀望',
    }
