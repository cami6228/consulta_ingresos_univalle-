import io
import pandas as pd

def generar_excel_consulta(reporte: dict) -> io.BytesIO:
    salida = io.BytesIO()

    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        reporte["resumen"].to_excel(writer, sheet_name="Resumen", index=False)
        reporte["anio"].to_excel(writer, sheet_name="Total por Año", index=False)
        reporte["centro"].to_excel(writer, sheet_name="Total por Centro", index=False)
        reporte["matriz"].to_excel(writer, sheet_name="Centro x Año")
        reporte["detalle"].to_excel(writer, sheet_name="Detalle", index=False)

        formato_moneda = '"$"#,##0.00'
        for ws in writer.book.worksheets:
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = max(max_len + 3, 13)

            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = formato_moneda

    salida.seek(0)
    return salida
