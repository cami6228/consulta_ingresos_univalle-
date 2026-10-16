import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from src.etl import cargar_y_limpiar_fuente, normalizar_nit, ANIOS
from src.export import generar_excel_consulta

# Configuración de respaldo para Pandas Styler
pd.set_option("styler.render.max_elements", 1_000_000)

st.set_page_config(
    page_title="Consulta de Ingresos · Univalle",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ Consulta de Valor Ejecutado por NIT")

# -------------------------------------------------------------
# 1. BARRA LATERAL: CARGA DE ARCHIVOS
# -------------------------------------------------------------
st.sidebar.header("📁 Carga de Información")

modo_carga = st.sidebar.radio(
    "Modalidad de fuentes:",
    [
        "📑 Fuentes Separadas (03-04 y 14)",
        "📚 Archivos Consolidados (2016–2025 / Anuales)",
    ],
    help="Elige si vas a subir las dos fuentes separadas (03-04 y 14) o archivos consolidados únicos/anuales.",
)

@st.cache_data(show_spinner="Procesando y auditando fuentes separadas...")
def procesar_fuentes_separadas(buffer_03, buffer_14):
    v03, r03 = cargar_y_limpiar_fuente(buffer_03, "Fuente 03-04")
    v14, r14 = cargar_y_limpiar_fuente(buffer_14, "Fuente 14")
    datos = pd.concat([v03, v14], ignore_index=True)
    rechazados = pd.concat([r03, r14], ignore_index=True)
    return datos, rechazados

@st.cache_data(show_spinner="Procesando y auditando archivos consolidados...")
def procesar_archivos_consolidados(buffers):
    dfs_validos = []
    dfs_rechazados = []
    for buf in buffers:
        nombre = getattr(buf, "name", "Consolidado")
        v, r = cargar_y_limpiar_fuente(buf, nombre_fuente=nombre, es_consolidado=True)
        dfs_validos.append(v)
        dfs_rechazados.append(r)
    datos = pd.concat(dfs_validos, ignore_index=True) if dfs_validos else pd.DataFrame()
    rechazados = pd.concat(dfs_rechazados, ignore_index=True) if dfs_rechazados else pd.DataFrame()
    return datos, rechazados

if modo_carga == "📑 Fuentes Separadas (03-04 y 14)":
    archivo_03 = st.sidebar.file_uploader("Fuente 03-04 (.xlsx) · Fondo Común", type=["xlsx"])
    archivo_14 = st.sidebar.file_uploader("Fuente 14 (.xlsx) · Proyecto/Unidad", type=["xlsx"])

    if not archivo_03 or not archivo_14:
        st.info("👆 Por favor sube ambos archivos (.xlsx) en la barra lateral izquierda para iniciar.")
        st.stop()

    try:
        datos, rechazados = procesar_fuentes_separadas(archivo_03, archivo_14)
    except Exception as e:
        st.error(f"Error al procesar los archivos: {e}")
        st.stop()
else:
    archivos_consolidados = st.sidebar.file_uploader(
        "Subir Archivo(s) Consolidado(s) (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=True,
        help="Puedes subir un archivo único consolidado o varios archivos anuales (ej: 2016 a 2025).",
    )

    if not archivos_consolidados:
        st.info("👆 Por favor sube uno o más archivos consolidados (.xlsx) en la barra lateral izquierda para iniciar.")
        st.stop()

    try:
        datos, rechazados = procesar_archivos_consolidados(archivos_consolidados)
    except Exception as e:
        st.error(f"Error al procesar los archivos consolidados: {e}")
        st.stop()

if datos.empty:
    st.warning("No se encontraron registros válidos en las fuentes suministradas.")
    st.stop()

# Subtítulo dinámico según los años presentes en los datos
min_anio = int(datos["Año del ingreso"].min())
max_anio = int(datos["Año del ingreso"].max())
if min_anio == max_anio:
    st.caption(f"Universidad del Valle · Consolidación de Ingresos (Vigencia {min_anio})")
else:
    st.caption(f"Universidad del Valle · Consolidación de Ingresos (Vigencias {min_anio}–{max_anio})")

# Métricas de consolidación en la barra lateral
st.sidebar.divider()
st.sidebar.subheader("Auditoría de Ingesta")
st.sidebar.write(f"✅ **Movimientos válidos:** {len(datos):,}")
st.sidebar.write(f"⚠️ **Registros excluidos:** {len(rechazados):,}")
if not rechazados.empty:
    with st.sidebar.expander("Ver motivos de exclusión"):
        st.dataframe(rechazados["Motivo exclusión"].value_counts())

# -------------------------------------------------------------
# 2. ÁREA DE BÚSQUEDA
# -------------------------------------------------------------
col_input, _ = st.columns([3, 1])
with col_input:
    nit_ingresado = st.text_input(
        "Ingresa el NIT a consultar:",
        placeholder="Ej: 901899532 o 901899532-3",
        help="Puedes incluir puntos, guion o dígito de verificación.",
    )

if not nit_ingresado:
    st.stop()

nit_busqueda = normalizar_nit(nit_ingresado)
detalle = (
    datos.loc[datos["NIT"] == nit_busqueda]
    .sort_values(["Año del ingreso", "Centro Información", "Fecha"])
    .reset_index(drop=True)
)

if detalle.empty:
    st.warning(f"No se encontraron registros para el NIT `{nit_ingresado}`.")
    st.stop()

# Identificar nombre de la entidad consultada
nombre_entidad = ""
if "Nombre Tercero" in detalle.columns:
    candidatos = [
        str(n).strip()
        for n in detalle["Nombre Tercero"].dropna().unique()
        if str(n).strip() and str(n).strip().lower() != "nan"
    ]
    if candidatos:
        nombre_entidad = candidatos[0]

if nombre_entidad:
    st.subheader(f"🏢 {nombre_entidad}")
    st.caption(f"NIT: **{nit_busqueda}** (búsqueda: `{nit_ingresado}`)")

# -------------------------------------------------------------
# 3. PROCESAMIENTO DEL REPORTE
# -------------------------------------------------------------
total_pesos = detalle["Valor_centavos"].sum() / 100
fondo_comun_pesos = detalle.loc[detalle["Tipo Asignación"] == "Fondo Común", "Valor_centavos"].sum() / 100
proyecto_pesos = detalle.loc[detalle["Tipo Asignación"] == "Proyecto / Unidad", "Valor_centavos"].sum() / 100

pct_fondo = (fondo_comun_pesos / total_pesos * 100) if total_pesos > 0 else 0.0
pct_proyecto = (proyecto_pesos / total_pesos * 100) if total_pesos > 0 else 0.0

# Años relevantes de la consulta
anios_reporte = sorted(detalle["Año del ingreso"].dropna().unique().astype(int).tolist())
if not anios_reporte:
    anios_reporte = sorted(datos["Año del ingreso"].dropna().unique().astype(int).tolist())
if not anios_reporte:
    anios_reporte = list(ANIOS)

# Resumen por año con desglose de fuentes
por_anio_piv = (
    detalle.pivot_table(
        index="Año del ingreso",
        columns="Tipo Asignación",
        values="Valor_centavos",
        aggfunc="sum",
        fill_value=0,
    ) / 100
).reindex(anios_reporte, fill_value=0)

for c in ["Fondo Común", "Proyecto / Unidad"]:
    if c not in por_anio_piv.columns:
        por_anio_piv[c] = 0.0

por_anio = por_anio_piv.reset_index().rename(columns={
    "Fondo Común": "Fondo Común (03-04)",
    "Proyecto / Unidad": "Proyecto / Unidad (14)",
})
por_anio["Total Ejecutado"] = por_anio["Fondo Común (03-04)"] + por_anio["Proyecto / Unidad (14)"]
por_anio["% Fondo Común"] = np.where(
    por_anio["Total Ejecutado"] > 0,
    (por_anio["Fondo Común (03-04)"] / por_anio["Total Ejecutado"]) * 100,
    0.0,
)

# Resumen por centro con detalle del proyecto y separación de fuentes
def extraer_descripciones(series):
    vals = [
        str(x).strip()
        for x in series.dropna().unique()
        if str(x).strip() and str(x).strip().lower() != "nan"
    ]
    return " | ".join(vals) if vals else "Sin descripción"

por_centro = (
    detalle.groupby("Centro Información", as_index=False)
    .apply(
        lambda g: pd.Series({
            "Proyecto / Observación": extraer_descripciones(g["Observación"]) if "Observación" in g.columns else "",
            "Concepto": extraer_descripciones(g["Nombre Concepto"]) if "Nombre Concepto" in g.columns else "",
            "Fondo Común (03-04)": g.loc[g["Tipo Asignación"] == "Fondo Común", "Valor_centavos"].sum() / 100,
            "Proyecto / Unidad (14)": g.loc[g["Tipo Asignación"] == "Proyecto / Unidad", "Valor_centavos"].sum() / 100,
            "Total Ejecutado": g["Valor_centavos"].sum() / 100,
            "Movimientos": len(g),
        }),
        include_groups=False,
    )
    .sort_values("Total Ejecutado", ascending=False)
    .reset_index(drop=True)
)
por_centro["% Fondo Común"] = np.where(
    por_centro["Total Ejecutado"] > 0,
    (por_centro["Fondo Común (03-04)"] / por_centro["Total Ejecutado"]) * 100,
    0.0,
)

# Matrices Centro x Año
matriz_total = (
    detalle.pivot_table(
        index="Centro Información",
        columns="Año del ingreso",
        values="Valor_centavos",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=anios_reporte, fill_value=0) / 100
)

matriz_fc = (
    detalle[detalle["Tipo Asignación"] == "Fondo Común"].pivot_table(
        index="Centro Información",
        columns="Año del ingreso",
        values="Valor_centavos",
        aggfunc="sum",
        fill_value=0,
    ).reindex(index=matriz_total.index, columns=anios_reporte, fill_value=0) / 100
)

matriz_proy = (
    detalle[detalle["Tipo Asignación"] == "Proyecto / Unidad"].pivot_table(
        index="Centro Información",
        columns="Año del ingreso",
        values="Valor_centavos",
        aggfunc="sum",
        fill_value=0,
    ).reindex(index=matriz_total.index, columns=anios_reporte, fill_value=0) / 100
)

# Detalle individual de movimientos
detalle_pesos = detalle.copy()
detalle_pesos["Valor Ejecutado"] = detalle_pesos["Valor_centavos"] / 100

cols_detalle = [
    col for col in [
        "Fecha",
        "Centro Información",
        "Observación",
        "Nombre Concepto",
        "Tipo Asignación",
        "Fuente",
        "Tipo Dcto",
        "Número",
        "Valor Ejecutado",
    ] if col in detalle_pesos.columns
]
detalle_vista = (
    detalle_pesos[cols_detalle]
    .sort_values(["Fecha", "Centro Información"], ascending=[False, True])
    .reset_index(drop=True)
)

# Resumen general para reporte Excel
resumen = pd.DataFrame([{
    "NIT consultado": nit_ingresado,
    "NIT normalizado": nit_busqueda,
    "Entidad": nombre_entidad,
    "Total General Ejecutado": total_pesos,
    "Fondo Común (Fuente 03-04)": fondo_comun_pesos,
    "% Fondo Común": pct_fondo / 100,
    "Proyecto / Unidad (Fuente 14)": proyecto_pesos,
    "% Proyecto": pct_proyecto / 100,
    "Movimientos Contabilizados": len(detalle),
    "Centros de Información": detalle["Centro Información"].nunique(),
}])

reporte = {
    "nit": nit_busqueda,
    "resumen": resumen,
    "anio": por_anio,
    "centro": por_centro,
    "matriz": matriz_total,
    "matriz_fc": matriz_fc,
    "matriz_proy": matriz_proy,
    "detalle": detalle_vista,
}

# -------------------------------------------------------------
# 4. TARJETAS DE RESULTADOS (KPIs)
# -------------------------------------------------------------
st.divider()
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total General Ejecutado", f"$ {total_pesos:,.2f}")
kpi2.metric("🏛️ Fondo Común (03-04)", f"$ {fondo_comun_pesos:,.2f}", f"{pct_fondo:.1f}%")
kpi3.metric("🔬 Proyecto / Unidad (14)", f"$ {proyecto_pesos:,.2f}", f"{pct_proyecto:.1f}%")
kpi4.metric(
    "Movimientos / Centros",
    f"{len(detalle):,} movs",
    f"{detalle['Centro Información'].nunique():,} centros",
)

# Botón de Descarga Excel
excel_bytes = generar_excel_consulta(reporte)
st.download_button(
    label="📥 Descargar Reporte en Excel",
    data=excel_bytes,
    file_name=f"Consulta_NIT_{nit_busqueda}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)

# -------------------------------------------------------------
# 5. VISTAS DETALLADAS EN PESTAÑAS Y VISUALIZACIONES
# -------------------------------------------------------------
tab_graf, tab1, tab2, tab_audit, tab3, tab4 = st.tabs([
    "📈 Visualizaciones y Tendencias",
    "📅 Resumen por Año", 
    "🏢 Por Centro de Información", 
    "🔍 Auditoría por Centro",
    "📊 Matriz Centro × Año", 
    "📋 Detalle de Movimientos"
])

with tab_graf:
    st.subheader("📊 Análisis Gráfico y Tendencias")
    st.caption("Resumen visual de asignación de recursos, evolución temporal y principales proyectos receptores.")

    col_g1, col_g2 = st.columns([3, 2])

    with col_g1:
        # Gráfico 1: Evolución por Año (Barras Apiladas)
        df_evolucion = (
            detalle.groupby(["Año del ingreso", "Tipo Asignación"], as_index=False)["Valor_centavos"]
            .sum()
        )
        df_evolucion["Valor"] = df_evolucion["Valor_centavos"] / 100
        df_evolucion["Año"] = df_evolucion["Año del ingreso"].astype(str)

        chart_anual = (
            alt.Chart(df_evolucion)
            .mark_bar()
            .encode(
                x=alt.X("Año:O", title="Año", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Valor:Q", title="Valor Ejecutado ($)", axis=alt.Axis(format="$,.0f")),
                color=alt.Color(
                    "Tipo Asignación:N",
                    title="Destino del Recurso",
                    scale=alt.Scale(
                        domain=["Fondo Común", "Proyecto / Unidad"],
                        range=["#C62828", "#1E88E5"],
                    ),
                    legend=alt.Legend(orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("Año:O", title="Año"),
                    alt.Tooltip("Tipo Asignación:N", title="Asignación"),
                    alt.Tooltip("Valor:Q", title="Valor", format="$,.2f"),
                ],
            )
            .properties(title="Evolución de Ingresos por Año y Destino", height=350)
        )
        st.altair_chart(chart_anual, use_container_width=True)

    with col_g2:
        # Gráfico 2: Participación Global (Donut Chart)
        df_donut = pd.DataFrame([
            {"Asignación": "Fondo Común (03-04)", "Valor": fondo_comun_pesos, "Porcentaje": pct_fondo},
            {"Asignación": "Proyecto / Unidad (14)", "Valor": proyecto_pesos, "Porcentaje": pct_proyecto},
        ])
        df_donut = df_donut[df_donut["Valor"] > 0]

        if not df_donut.empty:
            chart_donut = (
                alt.Chart(df_donut)
                .mark_arc(innerRadius=65, outerRadius=115)
                .encode(
                    theta=alt.Theta("Valor:Q"),
                    color=alt.Color(
                        "Asignación:N",
                        title="Destino",
                        scale=alt.Scale(
                            domain=["Fondo Común (03-04)", "Proyecto / Unidad (14)"],
                            range=["#C62828", "#1E88E5"],
                        ),
                        legend=alt.Legend(orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("Asignación:N", title="Destino"),
                        alt.Tooltip("Valor:Q", title="Total ($)", format="$,.2f"),
                        alt.Tooltip("Porcentaje:Q", title="Participación (%)", format=".1f"),
                    ],
                )
                .properties(title="Distribución Global del Recurso", height=350)
            )
            st.altair_chart(chart_donut, use_container_width=True)
        else:
            st.info("Sin montos positivos para graficar participación global.")

    st.divider()

    # Gráfico 3: Top Centros de Información / Proyectos (Barras Horizontales)
    top_centros = por_centro.head(10).copy()
    if not top_centros.empty:
        top_centros["Etiqueta"] = top_centros.apply(
            lambda r: f"{r['Centro Información']} - {str(r['Proyecto / Observación'])[:40]}..."
            if len(str(r['Proyecto / Observación'])) > 40
            else f"{r['Centro Información']} - {str(r['Proyecto / Observación'])}",
            axis=1,
        )

        top_centros_melt = pd.melt(
            top_centros,
            id_vars=["Etiqueta", "Centro Información"],
            value_vars=["Fondo Común (03-04)", "Proyecto / Unidad (14)"],
            var_name="Tipo Asignación",
            value_name="Valor",
        )
        top_centros_melt["Tipo Asignación"] = (
            top_centros_melt["Tipo Asignación"].str.replace(r"\s*\(.*?\)", "", regex=True)
        )

        chart_centros = (
            alt.Chart(top_centros_melt)
            .mark_bar()
            .encode(
                y=alt.Y("Etiqueta:N", title="Centro de Información / Proyecto", sort="-x"),
                x=alt.X("Valor:Q", title="Valor Ejecutado ($)", axis=alt.Axis(format="$,.0f")),
                color=alt.Color(
                    "Tipo Asignación:N",
                    title="Asignación",
                    scale=alt.Scale(
                        domain=["Fondo Común", "Proyecto / Unidad"],
                        range=["#C62828", "#1E88E5"],
                    ),
                    legend=alt.Legend(orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("Centro Información:N", title="Centro"),
                    alt.Tooltip("Tipo Asignación:N", title="Asignación"),
                    alt.Tooltip("Valor:Q", title="Valor", format="$,.2f"),
                ],
            )
            .properties(
                title="Top Centros de Información / Proyectos Receptores",
                height=max(260, len(top_centros) * 35),
            )
        )
        st.altair_chart(chart_centros, use_container_width=True)

    # Gráfico 4: Desembolsos Mensuales en el Tiempo
    detalle_mensual = detalle.copy()
    detalle_mensual["Mes_Anio"] = detalle_mensual["Fecha"].dt.to_period("M").dt.to_timestamp()
    df_mensual = (
        detalle_mensual.groupby(["Mes_Anio", "Tipo Asignación"], as_index=False)["Valor_centavos"]
        .sum()
    )
    df_mensual["Valor"] = df_mensual["Valor_centavos"] / 100

    if len(df_mensual) > 1:
        st.divider()
        chart_mensual = (
            alt.Chart(df_mensual)
            .mark_bar(size=14)
            .encode(
                x=alt.X("Mes_Anio:T", title="Fecha (Mes)", axis=alt.Axis(format="%b %Y")),
                y=alt.Y("Valor:Q", title="Valor Desembolsado ($)", axis=alt.Axis(format="$,.0f")),
                color=alt.Color(
                    "Tipo Asignación:N",
                    title="Asignación",
                    scale=alt.Scale(
                        domain=["Fondo Común", "Proyecto / Unidad"],
                        range=["#C62828", "#1E88E5"],
                    ),
                    legend=alt.Legend(orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("Mes_Anio:T", title="Mes", format="%B %Y"),
                    alt.Tooltip("Tipo Asignación:N", title="Asignación"),
                    alt.Tooltip("Valor:Q", title="Valor", format="$,.2f"),
                ],
            )
            .properties(title="Cronología Histórica de Pagos y Desembolsos", height=320)
        )
        st.altair_chart(chart_mensual, use_container_width=True)

with tab1:
    st.dataframe(
        por_anio,
        column_config={
            "Año del ingreso": st.column_config.NumberColumn("Año", format="%d"),
            "Fondo Común (03-04)": st.column_config.NumberColumn("Fondo Común (03-04)", format="dollar"),
            "Proyecto / Unidad (14)": st.column_config.NumberColumn("Proyecto / Unidad (14)", format="dollar"),
            "Total Ejecutado": st.column_config.NumberColumn("Total Ejecutado", format="dollar"),
            "% Fondo Común": st.column_config.NumberColumn("% Fondo Común", format="%.1f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    st.caption("Detalle de proyectos y destinos por Centro de Información")
    st.dataframe(
        por_centro,
        column_config={
            "Centro Información": st.column_config.TextColumn("Centro Inf.", width="small"),
            "Proyecto / Observación": st.column_config.TextColumn("Proyecto / Observación", width="large"),
            "Concepto": st.column_config.TextColumn("Concepto", width="medium"),
            "Fondo Común (03-04)": st.column_config.NumberColumn("Fondo Común (03-04)", format="dollar"),
            "Proyecto / Unidad (14)": st.column_config.NumberColumn("Proyecto / Unidad (14)", format="dollar"),
            "Total Ejecutado": st.column_config.NumberColumn("Total Ejecutado", format="dollar"),
            "% Fondo Común": st.column_config.NumberColumn("% Fondo Común", format="%.1f%%"),
            "Movimientos": st.column_config.NumberColumn("Movs", format="%d", width="small"),
        },
        use_container_width=True,
        hide_index=True,
    )

with tab_audit:
    st.subheader("🔍 Auditoría Focalizada por Centro de Información")
    st.caption("Selecciona un centro de información específico para auditar sus pagos, proyectos asociados y estado de transacciones.")

    # Diccionario descriptivo para el selector
    opciones_centros = {}
    for _, r in por_centro.iterrows():
        ci = str(r["Centro Información"]).strip()
        obs = str(r["Proyecto / Observación"]).strip()
        val = r["Total Ejecutado"]
        if obs and obs != "Sin descripción":
            obs_corta = obs[:45] + "..." if len(obs) > 45 else obs
            etiqueta = f"{ci} · {obs_corta} (${val:,.0f})"
        else:
            etiqueta = f"{ci} (${val:,.0f})"
        opciones_centros[ci] = etiqueta

    lista_ci = list(opciones_centros.keys())
    if not lista_ci:
        st.info("No hay centros de información registrados para este NIT.")
    else:
        col_select, _ = st.columns([3, 1])
        with col_select:
            centro_sel = st.selectbox(
                "Centro de Información a consultar:",
                options=lista_ci,
                format_func=lambda x: opciones_centros.get(x, x),
            )

        # Filtrar datos exclusivos de este centro
        df_c = detalle[detalle["Centro Información"] == centro_sel].copy()

        # Métricas principales del centro
        c_total = df_c["Valor_centavos"].sum() / 100
        c_fc = df_c.loc[df_c["Tipo Asignación"] == "Fondo Común", "Valor_centavos"].sum() / 100
        c_proy = df_c.loc[df_c["Tipo Asignación"] == "Proyecto / Unidad", "Valor_centavos"].sum() / 100
        c_pct_fc = (c_fc / c_total * 100) if c_total > 0 else 0.0
        c_pct_proy = (c_proy / c_total * 100) if c_total > 0 else 0.0

        # Rango de fechas de ejecución
        fechas_validas = df_c["Fecha"].dropna()
        if not fechas_validas.empty:
            f_min = fechas_validas.min().strftime("%d/%m/%Y")
            f_max = fechas_validas.max().strftime("%d/%m/%Y")
            rango_fechas = f"{f_min} al {f_max}"
        else:
            rango_fechas = "No registradas"

        # Ficha del Proyecto
        st.markdown(f"### 📌 Centro de Información: `{centro_sel}`")
        
        obs_unicas = [
            str(o).strip()
            for o in df_c["Observación"].dropna().unique()
            if str(o).strip() and str(o).strip().lower() != "nan"
        ]
        conceptos_unicos = [
            str(c).strip()
            for c in df_c["Nombre Concepto"].dropna().unique()
            if str(c).strip() and str(c).strip().lower() != "nan"
        ]

        if obs_unicas:
            st.markdown(f"**Proyecto / Objeto:** {' | '.join(obs_unicas)}")
        if conceptos_unicos:
            st.markdown(f"**Concepto:** {' | '.join(conceptos_unicos)}")

        # Métricas en columnas
        st.divider()
        c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
        c_kpi1.metric("Total Ejecutado en Centro", f"$ {c_total:,.2f}")
        c_kpi2.metric("🏛️ Fondo Común (03-04)", f"$ {c_fc:,.2f}", f"{c_pct_fc:.1f}%")
        c_kpi3.metric("🔬 Proyecto / Unidad (14)", f"$ {c_proy:,.2f}", f"{c_pct_proy:.1f}%")
        c_kpi4.metric("Movimientos", f"{len(df_c):,} pagos", rango_fechas)

        # Gráfico de desembolsos del centro en el tiempo
        if len(df_c) > 1:
            st.divider()
            df_c_chart = df_c.copy()
            df_c_chart["Valor"] = df_c_chart["Valor_centavos"] / 100
            chart_c_time = (
                alt.Chart(df_c_chart)
                .mark_bar(size=14)
                .encode(
                    x=alt.X("Fecha:T", title="Fecha de Pago", axis=alt.Axis(format="%d/%m/%Y")),
                    y=alt.Y("Valor:Q", title="Valor Desembolsado ($)", axis=alt.Axis(format="$,.0f")),
                    color=alt.Color(
                        "Tipo Asignación:N",
                        title="Asignación",
                        scale=alt.Scale(
                            domain=["Fondo Común", "Proyecto / Unidad"],
                            range=["#C62828", "#1E88E5"],
                        ),
                        legend=alt.Legend(orient="top"),
                    ),
                    tooltip=[
                        alt.Tooltip("Fecha:T", title="Fecha", format="%d/%m/%Y"),
                        alt.Tooltip("Tipo Dcto:N", title="Tipo"),
                        alt.Tooltip("Número:N", title="Dcto #"),
                        alt.Tooltip("Tipo Asignación:N", title="Asignación"),
                        alt.Tooltip("Observación:N", title="Detalle"),
                        alt.Tooltip("Valor:Q", title="Valor", format="$,.2f"),
                    ],
                )
                .properties(title=f"Cronología de Desembolsos · Centro {centro_sel}", height=280)
            )
            st.altair_chart(chart_c_time, use_container_width=True)

        # Tabla detallada de movimientos de este centro
        st.divider()
        st.subheader("📋 Movimientos y Estado de Pagos del Centro")
        
        df_c_vista = df_c.copy()
        df_c_vista["Valor Ejecutado"] = df_c_vista["Valor_centavos"] / 100

        cols_c_mostrar = [
            c for c in [
                "Fecha",
                "Tipo Dcto",
                "Número",
                "Observación",
                "Nombre Concepto",
                "Fuente",
                "Tipo Asignación",
                "Estado",
                "Valor Ejecutado",
            ] if c in df_c_vista.columns
        ]

        df_c_tabla = df_c_vista[cols_c_mostrar].sort_values("Fecha", ascending=False).reset_index(drop=True)

        st.dataframe(
            df_c_tabla,
            column_config={
                "Fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
                "Tipo Dcto": st.column_config.TextColumn("Tipo"),
                "Número": st.column_config.TextColumn("Dcto #"),
                "Observación": st.column_config.TextColumn("Detalle / Observación", width="large"),
                "Nombre Concepto": st.column_config.TextColumn("Concepto"),
                "Fuente": st.column_config.TextColumn("Fuente"),
                "Tipo Asignación": st.column_config.TextColumn("Asignación"),
                "Estado": st.column_config.TextColumn("Estado", help="ca: Causado / an: Anulado"),
                "Valor Ejecutado": st.column_config.NumberColumn("Valor Ejecutado", format="dollar"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # Botón para descargar reporte de este centro en Excel
        st.caption("Descarga la auditoría exclusiva de este Centro de Información:")
        rep_c = {
            "resumen": pd.DataFrame([{
                "NIT": nit_busqueda,
                "Entidad": nombre_entidad,
                "Centro Información": centro_sel,
                "Proyecto": " | ".join(obs_unicas),
                "Total Ejecutado": c_total,
                "Fondo Común (03-04)": c_fc,
                "% Fondo Común": c_pct_fc / 100,
                "Proyecto / Unidad (14)": c_proy,
                "% Proyecto": c_pct_proy / 100,
                "Transacciones": len(df_c),
                "Período de Ejecución": rango_fechas,
            }]),
            "anio": df_c.pivot_table(
                index="Año del ingreso", columns="Tipo Asignación", values="Valor_centavos", aggfunc="sum", fill_value=0
            ).reset_index(),
            "centro": por_centro[por_centro["Centro Información"] == centro_sel],
            "matriz": df_c.pivot_table(index="Centro Información", columns="Año del ingreso", values="Valor_centavos", aggfunc="sum", fill_value=0) / 100,
            "detalle": df_c_tabla,
        }
        excel_c_bytes = generar_excel_consulta(rep_c)
        st.download_button(
            label=f"📥 Descargar Reporte de Centro {centro_sel} en Excel",
            data=excel_c_bytes,
            file_name=f"Auditoria_Centro_{centro_sel}_NIT_{nit_busqueda}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab3:
    col_sel, _ = st.columns([2, 2])
    with col_sel:
        vista_matriz = st.radio(
            "Visualizar valores de:",
            ["Total Consolidado", "Fondo Común (03-04)", "Proyecto / Unidad (14)"],
            horizontal=True,
        )
    
    matriz_mostrar = matriz_total
    if vista_matriz == "Fondo Común (03-04)":
        matriz_mostrar = matriz_fc
    elif vista_matriz == "Proyecto / Unidad (14)":
        matriz_mostrar = matriz_proy

    st.dataframe(
        matriz_mostrar,
        column_config={
            col: st.column_config.NumberColumn(format="dollar")
            for col in matriz_mostrar.columns
        },
        use_container_width=True,
    )

with tab4:
    st.caption(f"Mostrando {len(detalle_vista):,} movimientos individuales ordenados cronológicamente")
    st.dataframe(
        detalle_vista,
        column_config={
            "Fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
            "Centro Información": st.column_config.TextColumn("Centro Inf."),
            "Observación": st.column_config.TextColumn("Proyecto / Observación", width="large"),
            "Nombre Concepto": st.column_config.TextColumn("Concepto"),
            "Tipo Asignación": st.column_config.TextColumn("Asignación"),
            "Fuente": st.column_config.TextColumn("Fuente"),
            "Tipo Dcto": st.column_config.TextColumn("Tipo Dcto"),
            "Número": st.column_config.TextColumn("Dcto #"),
            "Valor Ejecutado": st.column_config.NumberColumn("Valor Ejecutado", format="dollar"),
        },
        use_container_width=True,
        hide_index=True,
    )
