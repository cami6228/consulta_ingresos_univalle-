import streamlit as st
import pandas as pd
from src.etl import cargar_y_limpiar_fuente, normalizar_nit, ANIOS
from src.export import generar_excel_consulta

st.set_page_config(
    page_title="Consulta de Ingresos · Univalle",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ Consulta de Valor Ejecutado por NIT")
st.caption("Universidad del Valle · Consolidación Fuentes 03-04 y 14 (Vigencias 2024–2026)")

# -------------------------------------------------------------
# 1. BARRA LATERAL: CARGA DE ARCHIVOS
# -------------------------------------------------------------
st.sidebar.header("📁 Carga de Fuentes")
archivo_03 = st.sidebar.file_uploader("Fuente 03-04 (.xlsx)", type=["xlsx"])
archivo_14 = st.sidebar.file_uploader("Fuente 14 (.xlsx)", type=["xlsx"])

@st.cache_data(show_spinner="Procesando y auditando fuentes...")
def procesar_archivos(buffer_03, buffer_14):
    v03, r03 = cargar_y_limpiar_fuente(buffer_03, "Fuente 03-04")
    v14, r14 = cargar_y_limpiar_fuente(buffer_14, "Fuente 14")
    
    datos = pd.concat([v03, v14], ignore_index=True)
    rechazados = pd.concat([r03, r14], ignore_index=True)
    
    indice = (
        datos.groupby(["NIT", "Centro Información", "Año del ingreso"])["Valor_centavos"]
        .sum()
        .reset_index()
    )
    return datos, rechazados, indice

if not archivo_03 or not archivo_14:
    st.info("👆 Por favor sube ambos archivos (.xlsx) en la barra lateral izquierda para iniciar.")
    st.stop()

try:
    datos, rechazados, indice = procesar_archivos(archivo_03, archivo_14)
except Exception as e:
    st.error(f"Error al procesar los archivos: {e}")
    st.stop()

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
col_input, col_btn = st.columns([3, 1])
with col_input:
    nit_ingresado = st.text_input(
        "Ingresa el NIT a consultar:",
        placeholder="Ej: 901899532 o 901899532-3",
        help="Puedes incluir puntos, guion o dígito de verificación.",
    )

if not nit_ingresado:
    st.stop()

nit_busqueda = normalizar_nit(nit_ingresado)

grupos = indice.loc[indice["NIT"] == nit_busqueda].copy()

if grupos.empty:
    st.warning(f"No se encontraron registros para el NIT `{nit_ingresado}`.")
    st.stop()

# -------------------------------------------------------------
# 3. PROCESAMIENTO DEL REPORTE
# -------------------------------------------------------------
detalle = (
    datos.loc[datos["NIT"] == nit_busqueda]
    .sort_values(["Año del ingreso", "Centro Información", "Fecha"])
    .reset_index(drop=True)
)

total_pesos = detalle["Valor_centavos"].sum() / 100

por_anio = (
    grupos.groupby("Año del ingreso")["Valor_centavos"]
    .sum()
    .reindex(ANIOS, fill_value=0)
    .reset_index()
)
por_anio["Valor Ejecutado"] = por_anio["Valor_centavos"] / 100
por_anio = por_anio.drop(columns=["Valor_centavos"])

por_centro = (
    grupos.groupby("Centro Información", as_index=False)["Valor_centavos"]
    .sum()
    .sort_values("Valor_centavos", ascending=False)
)
por_centro["Valor Ejecutado"] = por_centro["Valor_centavos"] / 100
por_centro = por_centro.drop(columns=["Valor_centavos"])

matriz = (
    grupos.pivot_table(
        index="Centro Información",
        columns="Año del ingreso",
        values="Valor_centavos",
        aggfunc="sum",
        fill_value=0,
    )
    .reindex(columns=ANIOS, fill_value=0)
) / 100

resumen = pd.DataFrame([{
    "NIT consultado": nit_ingresado,
    "Total General Ejecutado": total_pesos,
    "Movimientos originales": len(detalle),
    "Centros de Información": grupos["Centro Información"].nunique(),
}])

detalle_pesos = detalle.copy()
detalle_pesos["Valor Ejecutado"] = detalle_pesos["Valor_centavos"] / 100
detalle_pesos = detalle_pesos.drop(columns=["Valor_centavos", "Motivo exclusión"])

reporte = {
    "nit": nit_busqueda,
    "resumen": resumen,
    "anio": por_anio,
    "centro": por_centro,
    "matriz": matriz,
    "detalle": detalle_pesos,
}

# -------------------------------------------------------------
# 4. TARJETAS DE RESULTADOS (KPIs)
# -------------------------------------------------------------
st.divider()
kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("Total General Ejecutado", f"$ {total_pesos:,.2f}")
kpi2.metric("Movimientos Contabilizados", f"{len(detalle):,}")
kpi3.metric("Centros de Información", f"{grupos['Centro Información'].nunique():,}")

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
# 5. VISTAS DETALLADAS EN PESTAÑAS
# -------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Resumen por Año", 
    "🏢 Por Centro de Información", 
    "📊 Matriz Centro × Año", 
    "📋 Detalle de Movimientos"
])

with tab1:
    st.dataframe(
        por_anio.style.format({"Valor Ejecutado": "${:,.2f}"}),
        use_container_width=True,
    )

with tab2:
    st.dataframe(
        por_centro.style.format({"Valor Ejecutado": "${:,.2f}"}),
        use_container_width=True,
    )

with tab3:
    st.dataframe(
        matriz.style.format("${:,.2f}"),
        use_container_width=True,
    )

with tab4:
    st.dataframe(
        detalle_pesos.style.format({"Valor Ejecutado": "${:,.2f}"}),
        use_container_width=True,
    )
