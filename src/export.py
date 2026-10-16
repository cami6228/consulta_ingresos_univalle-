import io
import pandas as pd

def generar_excel_consulta(reporte: dict) -> io.BytesIO:
    salida = io.BytesIO()

    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        reporte["resumen"].to_excel(writer, sheet_name="Resumen", index=False)
        reporte["anio"].to_excel(writer, sheet_name="Total por Año", index=False)
        reporte["centro"].to_excel(writer, sheet_name="Total por Centro", index=False)
        reporte["matriz"].to_excel(writer, sheet_name="Centro x Año (Total)")
        if "matriz_fc" in reporte:
            reporte["matriz_fc"].to_excel(writer, sheet_name="Centro x Año (Fondo Común)")
        if "matriz_proy" in reporte:
            reporte["matriz_proy"].to_excel(writer, sheet_name="Centro x Año (Proyecto)")
        reporte["detalle"].to_excel(writer, sheet_name="Detalle", index=False)

        formato_moneda = '"$"#,##0.00'
        formato_porcentaje = '0.0%'
        formato_entero = '#,##0'

        for ws in writer.book.worksheets:
            # Auto-ajuste de ancho de columnas con límite razonable
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 13), 60)

            # Identificación de formatos por encabezado
            headers = [cell.value for cell in ws[1]]
            for col_idx, header in enumerate(headers, start=1):
                h_str = str(header or "").lower()

                if "%" in h_str or "porcentaje" in h_str:
                    col_fmt = formato_porcentaje
                elif any(m in h_str for m in ["valor", "total", "fondo", "proyecto", "ejecutado", "saldo", "pagado", "2024", "2025", "2026"]):
                    # Verificar que no sea columna 'año' explícita
                    if h_str in ["año", "año del ingreso"]:
                        col_fmt = "0"
                    else:
                        col_fmt = formato_moneda
                elif any(e in h_str for e in ["movimientos", "movs"]):
                    col_fmt = formato_entero
                elif h_str in ["año", "año del ingreso"]:
                    col_fmt = "0"
                else:
                    col_fmt = None

                if col_fmt:
                    for row in range(2, ws.max_row + 1):
                        cell = ws.cell(row=row, column=col_idx)
                        if isinstance(cell.value, (int, float)):
                            if col_fmt == formato_porcentaje and cell.value > 1.0:
                                cell.value = cell.value / 100
                            cell.number_format = col_fmt

    salida.seek(0)
    return salida
