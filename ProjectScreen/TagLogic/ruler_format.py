def format_tick_strings(values, scale, spacing):
    if spacing >= 1.0:
        dec = 0
        fmt = "{sign}{m}:{s:02d}"
    elif spacing >= 0.1:
        dec = 1
        fmt = "{sign}{m}:{s:02d}.{frac}"
    else:
        dec = 2
        fmt = "{sign}{m}:{s:02d}.{frac}"

    out = []
    for v in values:
        try:
            fv = float(v)
        except (TypeError, ValueError):
            out.append("")
            continue

        sign = "-" if fv < 0 else ""
        absv = abs(fv)
        total_seconds = int(absv)
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        if dec == 0:
            out.append(fmt.format(sign=sign, m=minutes, s=seconds))
            continue

        frac_value = absv - total_seconds
        frac_int = int(round(frac_value * (10**dec)))
        if frac_int >= 10**dec:
            frac_int -= 10**dec
            seconds += 1
            if seconds >= 60:
                seconds = 0
                minutes += 1
        out.append(
            fmt.format(
                sign=sign,
                m=minutes,
                s=seconds,
                frac=str(frac_int).zfill(dec),
            )
        )
    return out
