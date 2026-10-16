import io
import re
from zipfile import ZipFile, ZIP_DEFLATED
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
import pandas as pd
import numpy as np

ANIOS = (2024, 2025, 2026)
RANGO_ANIOS_VALIDOS = tuple(range(2010, 2035))
FILA_ENCABEZADO = 6
COLUMNAS_NECESARIAS = {
    "Tercero",
    "Fecha",
    "Centro Información",
    "Valor Ejecutado",
}

def reparar_date1900_buffer(file_buffer) -> io.BytesIO:
    """
    Repara el error date1900 en memoria sin escribir en disco.
    Acepta un archivo subido o BytesIO y devuelve un nuevo BytesIO reparado.
    """
    buffer_salida = io.BytesIO()
    
    with ZipFile(file_buffer, "r") as zin:
        with ZipFile(buffer_salida, "w", compression=ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                contenido = zin.read(item.filename)
                if item.filename == "xl/workbook.xml":
                    contenido = re.sub(rb'\sdate1900="[^"]*"', b"", contenido)
                zout.writestr(item, contenido)
                
    buffer_salida.seek(0)
    return buffer_salida

def normalizar_nit(valor) -> str:
    if pd.isna(valor):
        return ""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if not float(valor).is_integer():
            return ""
        texto = str(int(valor))
    else:
        texto = str(valor).strip()
        if re.fullmatch(r"\d+\.0", texto):
            texto = texto[:-2]

    # Valida números con o sin DV (separado por guion o espacio)
    coincidencia = re.fullmatch(
        r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]+)(?:\s*-\s*([0-9]))?",
        texto,
    )
    if coincidencia is None:
        return ""
    return re.sub(r"[.\s]", "", coincidencia.group(1))

def normalizar_centro_informacion(valor) -> str:
    if pd.isna(valor):
        return ""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if float(valor).is_integer():
            return str(int(valor))
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.strip()

def inferir_fuente_y_asignacion(cuenta):
    """
    Infiere la fuente (Fuente 03-04 o Fuente 14) y el tipo de asignación
    a partir del código contable en 'Cuenta de Movimiento'.
    """
    if pd.isna(cuenta) or not str(cuenta).strip():
        return "No especificada", "Otros"
    texto = str(cuenta).strip()
    partes = texto.split(".")
    if len(partes) >= 3:
        f = partes[2].strip()
        if f in ("03", "04"):
            return "Fuente 03-04", "Fondo Común"
        elif f == "14":
            return "Fuente 14", "Proyecto / Unidad"
    if ".14." in texto:
        return "Fuente 14", "Proyecto / Unidad"
    elif ".03." in texto or ".04." in texto:
        return "Fuente 03-04", "Fondo Común"
    return "Otras Fuentes", "Otros"

def convertir_centavos(valor):
    if pd.isna(valor) or isinstance(valor, bool):
        return None

    if isinstance(valor, (int, float)):
        texto = str(valor)
    else:
        texto = str(valor).strip().replace("\xa0", "").replace("$", "")
        texto = re.sub(r"\s+", "", texto)
        if not texto:
            return None

        negativo = False
        if texto.startswith("(") and texto.endswith(")"):
            negativo = True
            texto = texto[1:-1]
        elif texto.startswith("-"):
            negativo = True
            texto = texto[1:]

        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", texto):
            texto = texto.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d+(?:,\d{1,2})?", texto):
            texto = texto.replace(",", ".")
        elif re.fullmatch(r"\d+\.\d{1,2}", texto):
            pass
        else:
            return None

        if negativo:
            texto = "-" + texto

    try:
        numero = Decimal(texto)
        centavos = numero * 100
        if not numero.is_finite():
            return None
            
        # Tolerancia épsilon para absorber ruido de float binario
        centavos_redondeados = centavos.quantize(Decimal("1"))
        if abs(centavos - centavos_redondeados) > Decimal("0.001"):
            return None

        return int(centavos_redondeados)
    except (InvalidOperation, ValueError):
        return None

def convertir_fecha(valor):
    if pd.isna(valor):
        return pd.NaT
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(valor)

    texto = str(valor).strip()
    formatos = (
        "%d/%m/%Y", "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y", "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d", "%Y-%m-%d %H:%M:%S",
    )
    for formato in formatos:
        try:
            return pd.Timestamp(datetime.strptime(texto, formato))
        except ValueError:
            continue
    return pd.NaT

def cargar_y_limpiar_fuente(archivo, nombre_fuente: str = "Consolidado", es_consolidado: bool = False):
    """
    Repara y procesa una fuente en memoria (fuente individual o consolidado histórico).
    Retorna un DataFrame limpio y un DataFrame de rechazados.
    """
    buffer_reparado = reparar_date1900_buffer(archivo)
    
    df = pd.read_excel(
        buffer_reparado,
        header=FILA_ENCABEZADO,
        sheet_name=0,
        engine="openpyxl",
        dtype={"Tercero": object, "Valor Ejecutado": object, "Centro Información": object},
    )

    faltantes = COLUMNAS_NECESARIAS - set(df.columns)
    if faltantes:
        # Intento de respaldo con header=0 por si el consolidado no trae el banner de 6 filas
        buffer_reparado.seek(0)
        df_alt = pd.read_excel(
            buffer_reparado,
            header=0,
            sheet_name=0,
            engine="openpyxl",
            dtype={"Tercero": object, "Valor Ejecutado": object, "Centro Información": object},
        )
        if not (COLUMNAS_NECESARIAS - set(df_alt.columns)):
            df = df_alt
        else:
            raise ValueError(f"{nombre_fuente}: faltan columnas obligatorias: {sorted(faltantes)}")

    trabajo = df.copy()

    # Determinación de Fuente y Tipo Asignación
    if es_consolidado or ("03" not in nombre_fuente and "14" not in nombre_fuente):
        if "Cuenta de Movimiento" in trabajo.columns:
            inferred = trabajo["Cuenta de Movimiento"].map(inferir_fuente_y_asignacion)
            trabajo["Fuente"] = [x[0] for x in inferred]
            trabajo["Tipo Asignación"] = [x[1] for x in inferred]
        elif "Fuente" in trabajo.columns:
            trabajo["Fuente"] = trabajo["Fuente"].astype(str).str.strip()
            trabajo["Tipo Asignación"] = np.where(
                trabajo["Fuente"].str.contains("03|04"), "Fondo Común", "Proyecto / Unidad"
            )
        else:
            trabajo["Fuente"] = nombre_fuente
            trabajo["Tipo Asignación"] = "Otros"
    else:
        trabajo["Fuente"] = nombre_fuente
        trabajo["Tipo Asignación"] = "Fondo Común" if "03" in nombre_fuente else "Proyecto / Unidad"

    trabajo["NIT"] = trabajo["Tercero"].map(normalizar_nit)
    trabajo["Fecha"] = pd.to_datetime(trabajo["Fecha"].map(convertir_fecha), errors="coerce")
    trabajo["Centro Información"] = trabajo["Centro Información"].map(normalizar_centro_informacion)
    trabajo["Valor_centavos"] = pd.Series(
        [convertir_centavos(v) for v in trabajo["Valor Ejecutado"]],
        index=trabajo.index,
        dtype=object,
    )
    trabajo["Año del ingreso"] = trabajo["Fecha"].dt.year

    # Limpieza de campos descriptivos de apoyo
    for col in ["Observación", "Nombre Concepto", "Nombre Tercero", "Tipo Dcto"]:
        if col in trabajo.columns:
            trabajo[col] = trabajo[col].fillna("").astype(str).str.strip()

    if "Número" in trabajo.columns:
        trabajo["Número"] = (
            trabajo["Número"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .replace("nan", "")
            .str.strip()
        )

    # Vectorización de exclusiones
    m_nit = trabajo["NIT"] == ""
    m_fecha = trabajo["Fecha"].isna()
    m_centro = trabajo["Centro Información"] == ""
    m_valor = trabajo["Valor_centavos"].isna()
    m_anio = trabajo["Fecha"].notna() & (~trabajo["Año del ingreso"].isin(RANGO_ANIOS_VALIDOS))

    condiciones = (
        (m_nit, "NIT inválido o vacío"),
        (m_fecha, "Fecha inválida"),
        (m_centro, "Centro vacío"),
        (m_valor, "Valor inválido"),
        (m_anio, "Año fuera del período"),
    )

    motivos = np.full(len(trabajo), "", dtype=object)
    for mascara, texto in condiciones:
        mask_arr = mascara.to_numpy()
        prefijo = np.where(motivos == "", "", "; ")
        motivos = np.where(mask_arr, motivos + prefijo + texto, motivos)

    trabajo["Motivo exclusión"] = motivos

    validos = trabajo.loc[trabajo["Motivo exclusión"] == ""].copy()
    rechazados = trabajo.loc[trabajo["Motivo exclusión"] != ""].copy()

    validos["Valor_centavos"] = validos["Valor_centavos"].astype("int64")
    validos["Año del ingreso"] = validos["Año del ingreso"].astype("int64")

    return validos, rechazados

