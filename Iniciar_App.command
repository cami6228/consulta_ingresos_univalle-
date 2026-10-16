#!/bin/bash
cd "$(dirname "$0")"

echo "=============================================================="
echo " INICIANDO CONSULTA DE INGRESOS · UNIVERSIDAD DEL VALLE"
echo "=============================================================="
echo ""

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Configurando entorno por primera vez..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
fi

echo "Abriendo la aplicación en tu navegador web..."
echo "(Para cerrar la aplicación cuando termines, cierra esta ventana)"
echo ""

streamlit run app.py
