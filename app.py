import streamlit as st
import pandas as pd
from groq import Groq
import math
import io
from datetime import datetime

cliente = Groq(api_key=st.secrets["GROQ_API_KEY"])

st.set_page_config(page_title="StokIA", page_icon="📦", layout="centered")

st.markdown("""
<div style="background:#1F4E79;padding:20px 24px;border-radius:12px;margin-bottom:24px">
    <h1 style="color:white;margin:0;font-size:28px">📦 StokIA</h1>
    <p style="color:#BDD7EE;margin:6px 0 0 0;font-size:15px">Compras inteligentes para tu negocio</p>
</div>
""", unsafe_allow_html=True)

archivo = st.file_uploader("Sube tu inventario en Excel", type=["xlsx"], help="Compatible con plantilla StokIA V1 y V2")

def pedir_ia(prompt):
    r = cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content.strip()

def calcular_abc(df_valido):
    df_valido = df_valido.copy()
    df_valido["ingreso_semanal"] = df_valido["ventas"] * df_valido["precio_venta"]
    total = df_valido["ingreso_semanal"].sum()
    if total == 0:
        df_valido["abc"] = "C"
        return df_valido
    df_valido = df_valido.sort_values("ingreso_semanal", ascending=False)
    df_valido["ingreso_acum"] = df_valido["ingreso_semanal"].cumsum()
    df_valido["pct_acum"] = df_valido["ingreso_acum"] / total
    def clasificar(pct):
        if pct <= 0.80: return "A"
        elif pct <= 0.95: return "B"
        else: return "C"
    df_valido["abc"] = df_valido["pct_acum"].apply(clasificar)
    return df_valido

def stock_minimo_sugerido(ventas, lead_time, abc):
    factor = {"A": 3, "B": 2, "C": 1}.get(abc, 2)
    return math.ceil(ventas * (lead_time / 7 + factor))

def badge_abc(abc):
    colores = {"A": "#C6EFCE", "B": "#FFEB9C", "C": "#FFCCCC"}
    textos = {"A": "#276221", "B": "#9C5700", "C": "#9C0006"}
    bg = colores.get(abc, "#F2F2F2")
    tx = textos.get(abc, "#595959")
    return f'<span style="background:{bg};color:{tx};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">{abc}</span>'

def encontrar_col(df, opciones):
    """Busca el nombre de columna correcto entre varias opciones posibles."""
    cols_norm = {c.strip().replace("\n", " "): c for c in df.columns}
    for op in opciones:
        op_norm = op.strip().replace("\n", " ")
        if op_norm in cols_norm:
            return cols_norm[op_norm]
    return None

if archivo is not None:
    df_raw = pd.read_excel(archivo, sheet_name="Inventario", skiprows=2)
    df_raw.columns = [str(c).strip().replace("\n", " ") for c in df_raw.columns]
    df_raw = df_raw.dropna(subset=["Nombre del producto"])

    # Mapeo flexible V1 y V2
    MAP = {
        "nombre":        ["Nombre del producto"],
        "stock":         ["Stock actual"],
        "ventas":        ["Ventas promedio semanal", "Ventas promedio semanal (unidades)"],
        "precio_venta":  ["Precio de venta unitario", "Precio de venta unitario (COP)"],
        "precio_compra": ["Precio de compra unitario", "Precio de compra unitario (COP)"],
        "proveedor":     ["Proveedor preferido", "Proveedor"],
        "lead_time":     ["Lead time (días entrega)", "Lead time (días entrega)"],
        "stock_min":     ["Stock mínimo deseado"],
    }

    col_ventas  = encontrar_col(df_raw, MAP["ventas"])
    col_pv      = encontrar_col(df_raw, MAP["precio_venta"])
    col_pc      = encontrar_col(df_raw, MAP["precio_compra"])
    col_prov    = encontrar_col(df_raw, MAP["proveedor"])
    col_lt      = encontrar_col(df_raw, MAP["lead_time"])
    col_sm      = encontrar_col(df_raw, MAP["stock_min"])

    tiene_precios  = col_pc is not None and df_raw[col_pc].sum() > 0 if col_pc else False
    tiene_leadtime = col_lt is not None
    version = "V2" if tiene_leadtime else "V1"

    filas = []
    for _, row in df_raw.iterrows():
        try:
            nombre        = str(row.get("Nombre del producto", "")).strip()
            if not nombre or nombre.lower() == "nan": continue
            stock         = float(row.get("Stock actual", 0) or 0)
            ventas        = float(row[col_ventas] if col_ventas else 0)
            precio_venta  = float(row[col_pv] if col_pv else 0)
            precio_compra = float(row[col_pc] if col_pc else 0)
            proveedor     = str(row[col_prov] if col_prov else "Sin proveedor")
            lead_time_raw = float(row[col_lt]) if col_lt and pd.notna(row[col_lt]) else 3
            lead_time     = int(lead_time_raw) if not math.isnan(lead_time_raw) else 3
            stock_min_raw = float(row[col_sm]) if col_sm and pd.notna(row[col_sm]) else 0
            filas.append({
                "nombre": nombre, "stock": int(stock), "ventas": ventas,
                "precio_venta": precio_venta, "precio_compra": precio_compra,
                "proveedor": proveedor, "lead_time": lead_time,
                "stock_min_usuario": stock_min_raw
            })
        except:
            continue

    df = pd.DataFrame(filas)

    st.success(f"✅ {len(df)} productos cargados · Plantilla {version}" +
               (" · Análisis avanzado activado ⭐" if tiene_precios else ""))
    with st.expander("Ver inventario completo"):
        st.dataframe(df_raw, use_container_width=True)

    if st.button("🔍 Analizar con IA", type="primary", use_container_width=True):

        df_abc = calcular_abc(df[df["ventas"] > 0].copy())
        abc_map = dict(zip(df_abc["nombre"], df_abc["abc"])) if len(df_abc) > 0 else {}

        urgentes, proximos, exceso, normales = [], [], [], []

        for _, row in df.iterrows():
            try:
                nombre        = row["nombre"]
                stock         = row["stock"]
                ventas        = row["ventas"]
                costo         = row["precio_compra"]
                pv            = row["precio_venta"]
                proveedor     = row["proveedor"]
                lead_time     = row["lead_time"]
                abc           = abc_map.get(nombre, "C")
                margen        = pv - costo if costo > 0 else 0
                roi           = round(margen / costo * 100) if costo > 0 else 0
                stock_min     = stock_minimo_sugerido(ventas, lead_time, abc)

                if ventas > 0:
                    semanas    = stock / ventas
                    dias_stock = semanas * 7

                    if (tiene_leadtime and dias_stock < lead_time) or semanas < 1:
                        uds = max(math.ceil((ventas * 2) - stock), 1)
                        urgentes.append({
                            "nombre": nombre, "stock": stock, "ventas": int(ventas),
                            "semanas": round(semanas, 1), "uds": uds,
                            "costo_total": uds * costo if costo > 0 else 0,
                            "proveedor": proveedor, "lead_time": lead_time,
                            "abc": abc, "roi": roi, "margen": int(margen),
                            "ganancia_potencial": int(uds * margen) if margen > 0 else 0,
                            "stock_min": stock_min
                        })
                    elif semanas < 2:
                        uds = max(math.ceil((ventas * 2) - stock), 1)
                        proximos.append({
                            "nombre": nombre, "stock": stock, "ventas": int(ventas),
                            "semanas": round(semanas, 1), "uds": uds,
                            "costo_total": uds * costo if costo > 0 else 0,
                            "proveedor": proveedor, "lead_time": lead_time,
                            "abc": abc, "roi": roi, "margen": int(margen),
                            "ganancia_potencial": int(uds * margen) if margen > 0 else 0,
                            "stock_min": stock_min
                        })
                    elif stock > ventas * 4:
                        exc = math.ceil(stock - (ventas * 4))
                        exceso.append({
                            "nombre": nombre, "stock": stock, "ventas": int(ventas),
                            "exceso_uds": exc, "valor": exc * costo if costo > 0 else 0,
                            "abc": abc, "roi": roi
                        })
                    else:
                        normales.append({
                            "nombre": nombre, "ventas": ventas,
                            "costo": costo, "roi": roi, "abc": abc
                        })
            except:
                continue

        urgentes.sort(key=lambda x: ({"A":0,"B":1,"C":2}[x["abc"]], -x["roi"]))
        proximos.sort(key=lambda x: x["semanas"])

        total_sem1   = int(sum(p["costo_total"] for p in urgentes))
        total_sem2   = math.ceil(sum(p["ventas"] * p["costo"] for p in normales) * 0.6 + sum(p["costo_total"] for p in proximos))
        total_sem3   = math.ceil(sum(p["ventas"] * p["costo"] for p in normales) * 0.4)
        total_exceso = int(sum(p["valor"] for p in exceso))

        lista_urgentes = "\n".join([f"- {p['nombre']} (ABC:{p['abc']}, {p['semanas']} sem, lead {p['lead_time']}d)" for p in urgentes]) or "Ninguno."
        lista_proximos = "\n".join([f"- {p['nombre']}: {p['semanas']} semanas de stock" for p in proximos]) or "Ninguno."
        lista_exceso   = "\n".join([f"- {p['nombre']}: {p['exceso_uds']} uds de más" for p in exceso]) or "Ninguno."
        lista_normales = ", ".join([p["nombre"] for p in normales[:8]])

        with st.spinner("Analizando tu inventario..."):
            intro_urgentes = pedir_ia(f"""Eres StokIA. Tono cercano, directo, segunda persona. Máximo 2 oraciones.
Explica por qué estos productos son críticos considerando su categoría ABC y lead time del proveedor. Sin listas ni números.
Productos: {lista_urgentes}""")

            intro_sem2 = pedir_ia(f"""Eres StokIA. Tono cercano, directo, segunda persona. Máximo 2 oraciones.
Explica qué reponer en Semana 2 basándote EXACTAMENTE en estos productos específicos del negocio.
Menciona productos concretos por nombre. Sin números de cantidades ni precios.
Productos próximos a agotarse: {lista_proximos}
Productos de rotación normal para reponer: {lista_normales}""")

            intro_sem3 = pedir_ia(f"""Eres StokIA. Tono cercano, directo, segunda persona. Máximo 2 oraciones.
Da un consejo concreto de qué revisar en Semana 3 basado en el comportamiento real de este inventario.
Considera que hubo productos urgentes y capital atrapado. Sé específico, no genérico.
Urgentes: {lista_urgentes[:150]}
Capital atrapado: {lista_exceso[:150]}""")

            intro_exceso = pedir_ia(f"""Eres StokIA. Tono cercano, directo, segunda persona. Máximo 2 oraciones.
Explica brevemente qué hacer con el exceso para liberar capital. Sin listas ni números.
Productos en exceso: {lista_exceso}""")

            consejo = pedir_ia(f"""Eres StokIA. Tono cercano, directo, segunda persona.
Una sugerencia concreta y accionable para mejorar ventas o flujo de caja esta semana.
Específica para este inventario. Máximo 2 oraciones.
Urgentes: {lista_urgentes[:200]}
Exceso: {lista_exceso[:200]}""")

        # ── REPORTE ──────────────────────────────────────────
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        st.markdown(f"---\n### 📊 Reporte StokIA — {fecha}")

        col1, col2, col3 = st.columns(3)
        col1.metric("🚨 Semana 1", f"${total_sem1:,}" if total_sem1 > 0 else "Ver abajo", f"{len(urgentes)} productos")
        col2.metric("📅 Semana 2", f"${total_sem2:,}" if total_sem2 > 0 else "—", f"{len(proximos)} a reponer")
        col3.metric("💰 Capital atrapado", f"${total_exceso:,}" if total_exceso > 0 else "—", f"{len(exceso)} productos")

        # ABC
        st.divider()
        st.markdown("### 📊 Clasificación ABC de tu inventario")
        conteo = {"A": 0, "B": 0, "C": 0}
        for v in abc_map.values(): conteo[v] = conteo.get(v, 0) + 1
        ca, cb, cc = st.columns(3)
        ca.markdown(f'<div style="background:#C6EFCE;border-radius:10px;padding:12px 16px;text-align:center"><div style="font-size:24px;font-weight:700;color:#276221">{conteo["A"]}</div><div style="font-size:12px;color:#276221;font-weight:600">Productos A</div><div style="font-size:11px;color:#276221">80% de tus ingresos · Nunca pueden faltar</div></div>', unsafe_allow_html=True)
        cb.markdown(f'<div style="background:#FFEB9C;border-radius:10px;padding:12px 16px;text-align:center"><div style="font-size:24px;font-weight:700;color:#9C5700">{conteo["B"]}</div><div style="font-size:12px;color:#9C5700;font-weight:600">Productos B</div><div style="font-size:11px;color:#9C5700">Rotación media · Importantes</div></div>', unsafe_allow_html=True)
        cc.markdown(f'<div style="background:#FFCCCC;border-radius:10px;padding:12px 16px;text-align:center"><div style="font-size:24px;font-weight:700;color:#9C0006">{conteo["C"]}</div><div style="font-size:12px;color:#9C0006;font-weight:600">Productos C</div><div style="font-size:11px;color:#9C0006">Bajo impacto · Stock mínimo</div></div>', unsafe_allow_html=True)

        # ALERTAS URGENTES
        st.divider()
        st.markdown("### 🚨 Alertas urgentes — compra hoy")
        st.markdown(intro_urgentes)
        for p in urgentes:
            color_borde = "#FF0000" if p["abc"] == "A" else "#FFA500" if p["abc"] == "B" else "#70AD47"
            st.markdown(f"""
<div style="background:#FFF2CC;border-left:4px solid {color_borde};border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
    <div><span style="font-weight:600;font-size:14px">{'🔴' if p['abc']=='A' else '🟡' if p['abc']=='B' else '🟢'} {p['nombre']}</span>
    &nbsp;{badge_abc(p['abc'])}&nbsp;<span style="font-size:11px;color:#595959">Lead time: {p['lead_time']}d · Stock mín. sugerido: {p['stock_min']} uds</span></div>
    <div><span style="font-weight:600">Comprar: {p['uds']} uds</span>{'&nbsp;·&nbsp;<b>$'+f"{int(p['costo_total']):,}"+'</b>' if p['costo_total']>0 else ''}</div>
  </div>
  <div style="font-size:11px;color:#595959;margin-top:4px">Proveedor: {p['proveedor']} · Stock: {p['stock']} · Vende {p['ventas']}/sem · {p['semanas']} sem restantes</div>
</div>""", unsafe_allow_html=True)

        if total_sem1 > 0:
            st.info(f"💵 **TOTAL A INVERTIR HOY: ${total_sem1:,} COP**")

        if urgentes and tiene_precios:
            with st.expander("💡 ¿No alcanza el presupuesto? Compra en este orden"):
                st.caption("Ordenado por prioridad ABC y ROI")
                acumulado = 0
                for i, p in enumerate(urgentes):
                    acumulado += p["costo_total"]
                    st.markdown(f"**{i+1}.** {p['nombre']} {badge_abc(p['abc'])} · ROI: **{p['roi']}%** · Ganancia potencial: **${p['ganancia_potencial']:,} COP** · Inversión acumulada: **${int(acumulado):,} COP**", unsafe_allow_html=True)
                    st.progress(min(p["roi"], 100) / 100)

        # PLAN DE COMPRAS
        st.divider()
        st.markdown("### 📅 Plan de compras — 3 semanas")
        cs1, cs2, cs3 = st.columns(3)
        cs1.metric("Semana 1", f"${total_sem1:,} COP" if total_sem1 > 0 else "Ver arriba")
        cs2.metric("Semana 2", f"${total_sem2:,} COP" if total_sem2 > 0 else "—")
        cs3.metric("Semana 3", f"${total_sem3:,} COP" if total_sem3 > 0 else "—")

        st.markdown("**📦 Semana 1 — Urgente**")
        for p in urgentes:
            st.markdown(f"- {badge_abc(p['abc'])} **{p['nombre']}** · {p['uds']} uds · {p['proveedor']}" + (f" · ${int(p['costo_total']):,} COP" if p['costo_total'] > 0 else ""), unsafe_allow_html=True)

        st.markdown("**📦 Semana 2 — Reposición**")
        st.markdown(intro_sem2)
        for p in proximos:
            st.markdown(f"- {badge_abc(p['abc'])} **{p['nombre']}** · {p['semanas']} sem · {p['uds']} uds" + (f" · ${int(p['costo_total']):,} COP" if p['costo_total'] > 0 else ""), unsafe_allow_html=True)

        st.markdown("**📦 Semana 3 — Ajuste**")
        st.markdown(intro_sem3)

        # CAPITAL ATRAPADO
        st.divider()
        st.markdown("### 💰 Capital atrapado")
        st.markdown(intro_exceso)
        for p in exceso:
            st.markdown(f"""
<div style="background:#FFF2F2;border-left:4px solid #C00000;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap">
    <span style="font-weight:600">{p['nombre']}</span>&nbsp;{badge_abc(p['abc'])}
    <span style="color:#C00000;font-weight:600">{p['exceso_uds']} uds de más{'&nbsp;·&nbsp;$'+f"{int(p['valor']):,}"+' COP' if p['valor']>0 else ''}</span>
  </div>
</div>""", unsafe_allow_html=True)
        if total_exceso > 0:
            st.warning(f"🔒 **TOTAL CAPITAL ATRAPADO: ${total_exceso:,} COP**")

        # CONSEJO
        st.divider()
        st.markdown("### 💡 Consejo de tu socio StokIA")
        st.success(consejo)

        # DESCARGA
        st.divider()
        st.markdown("### 📥 Descargar reporte")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            if urgentes:
                pd.DataFrame([{"Producto": p["nombre"], "ABC": p["abc"], "Stock": p["stock"],
                    "Ventas/sem": p["ventas"], "Lead time días": p["lead_time"],
                    "Stock mín. sugerido": p["stock_min"], "Uds a comprar": p["uds"],
                    "Costo total COP": int(p["costo_total"]) if p["costo_total"]>0 else "-",
                    "ROI %": p["roi"] if p["roi"]>0 else "-",
                    "Ganancia potencial COP": p["ganancia_potencial"] if p["ganancia_potencial"]>0 else "-",
                    "Proveedor": p["proveedor"]} for p in urgentes]).to_excel(writer, sheet_name="🚨 Urgentes", index=False)

            plan = [{"Semana": 1, "Producto": p["nombre"], "ABC": p["abc"], "Uds": p["uds"],
                     "Costo COP": int(p["costo_total"]) if p["costo_total"]>0 else "-",
                     "Proveedor": p["proveedor"]} for p in urgentes]
            plan += [{"Semana": 2, "Producto": p["nombre"], "ABC": p["abc"], "Uds": p["uds"],
                      "Costo COP": int(p["costo_total"]) if p["costo_total"]>0 else "-",
                      "Proveedor": p["proveedor"]} for p in proximos]
            if plan:
                pd.DataFrame(plan).to_excel(writer, sheet_name="📅 Plan compras", index=False)

            if exceso:
                pd.DataFrame([{"Producto": p["nombre"], "ABC": p["abc"], "Stock": p["stock"],
                    "Ventas/sem": p["ventas"], "Uds de más": p["exceso_uds"],
                    "Capital inmovilizado COP": int(p["valor"]) if p["valor"]>0 else "-"} for p in exceso]).to_excel(writer, sheet_name="💰 Capital atrapado", index=False)

            ranking = sorted(urgentes + proximos, key=lambda x: ({"A":0,"B":1,"C":2}[x["abc"]], -x["roi"]))
            if ranking and tiene_precios:
                pd.DataFrame([{"Prioridad": i+1, "Producto": p["nombre"], "ABC": p["abc"],
                    "ROI %": p["roi"], "Margen unit. COP": p["margen"], "Uds": p["uds"],
                    "Inversión COP": int(p["costo_total"]),
                    "Ganancia potencial COP": p["ganancia_potencial"],
                    "Proveedor": p["proveedor"]} for i, p in enumerate(ranking)]).to_excel(writer, sheet_name="📈 Ranking ROI", index=False)

            abc_data = [{"Producto": n, "ABC": c,
                "Ventas/sem": int(df[df["nombre"]==n]["ventas"].iloc[0]),
                "Precio venta COP": int(df[df["nombre"]==n]["precio_venta"].iloc[0]),
                "Ingreso semanal COP": int(df[df["nombre"]==n]["ventas"].iloc[0] * df[df["nombre"]==n]["precio_venta"].iloc[0])}
                for n, c in abc_map.items() if len(df[df["nombre"]==n]) > 0]
            if abc_data:
                pd.DataFrame(abc_data).sort_values("Ingreso semanal COP", ascending=False).to_excel(writer, sheet_name="📊 ABC", index=False)

            pd.DataFrame([
                {"Concepto": "Total urgentes Semana 1", "Valor COP": total_sem1},
                {"Concepto": "Total Semana 2", "Valor COP": total_sem2},
                {"Concepto": "Total Semana 3", "Valor COP": total_sem3},
                {"Concepto": "Capital atrapado", "Valor COP": total_exceso},
            ]).to_excel(writer, sheet_name="📋 Resumen", index=False)

        st.download_button(
            label="📥 Descargar reporte completo en Excel",
            data=output.getvalue(),
            file_name=f"reporte_stokia_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

else:
    st.info("👆 Sube tu archivo Excel para comenzar")
