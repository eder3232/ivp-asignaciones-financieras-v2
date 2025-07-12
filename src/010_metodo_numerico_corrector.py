proyecto = "cabanaconde"
mes = 5
anio = 2025

import pandas as pd
import os
import pprint
import scipy.optimize as opt
import pprint
import pickle
import json
import xlsxwriter
from xlsxwriter.utility import xl_range, xl_rowcol_to_cell
import re
from typing import Dict, List, Any
import itertools
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from google.oauth2 import service_account
from google.cloud import firestore
import excel2img
from dotenv import load_dotenv, find_dotenv
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import win32com.client as win32

# %% [markdown]
# ## Funciones utiles
#

# %% [markdown]
# ### Calculadora de costo total
#

# %%
from typing import TypedDict


class CostoIngenieriaResult(TypedDict):
    costo_directo: float
    gastos_generales: float
    utilidad: float
    subtotal: float
    igv: float
    total: float


def calculadora_costo_total(costo_directo: float) -> CostoIngenieriaResult:
    """
    Calcula el costo total de un proyecto de ingeniería civil en soles peruanos.

    Args:
        costo_directo (float): Costo directo del proyecto

    Returns:
        CostoIngenieriaResult: Diccionario con todos los valores calculados
    """
    # Calcular gastos generales (10% del costo directo)
    gastos_generales = round(costo_directo * 0.10, 2)

    # Calcular utilidad (5% del costo directo)
    utilidad = round(costo_directo * 0.05, 2)

    # Calcular subtotal
    subtotal = round(costo_directo + gastos_generales + utilidad, 2)

    # Calcular IGV (18% del subtotal)
    igv = round(subtotal * 0.18, 2)

    # Calcular total
    total = round(subtotal + igv, 2)

    return {
        "costo_directo": round(costo_directo, 2),
        "gastos_generales": gastos_generales,
        "utilidad": utilidad,
        "subtotal": subtotal,
        "igv": igv,
        "total": total,
    }


# %% [markdown]
# ### Multiplicar el precio unitario actualizado por la carga trabajo
#


# %%
def calcular_costos_unitarios(dict_precios_unitarios_actualizados, cargas_trabajo):
    """
    Multiplica cada carga de trabajo del contratista por su precio unitario
    correspondiente.

    Si alguna clave en cargas_trabajo tiene carga > 0 y no existe
    en dict_precios_unitarios_actualizados, levanta KeyError.
    Claves con carga = 0 se ignoran (no dan error), y claves en precios que noprecios_uninatrios_expediente
    están en cargas se tratan con carga = 0.

    Args:
        dict_precios_unitarios_actualizados (dict): código → precio unitario.
        cargas_trabajo (dict): código → carga de trabajo.

    Returns:
        dict: código → precio total (precio_unitario * carga).

    Raises:
        KeyError: si alguna clave con carga > 0 en cargas_trabajo
                  no existe en dict_precios_unitarios_actualizados.
    """
    # Detectar faltantes solo para cargas > 0
    faltantes = {
        codigo
        for codigo, carga in cargas_trabajo.items()
        if carga != 0 and codigo not in dict_precios_unitarios_actualizados
    }
    if faltantes:
        raise KeyError(f"Faltan precios unitarios para las claves: {faltantes}")

    # Construir resultado: para cada precio, multiplicar por carga (0 si no hay)
    resultado = {}
    for codigo, precio_unitario in dict_precios_unitarios_actualizados.items():
        carga = cargas_trabajo.get(codigo, 0)
        resultado[codigo] = precio_unitario * carga

    return resultado


# %% [markdown]
# ### Fusionar diccionarios


# %%
def fusionar_diccionarios(diccionario_de_diccionarios):
    """
    Fusiona diccionarios separados en un diccionario unificado.
    Solo incluye claves donde ambos valores sean diferentes de cero.
    Usa dinámicamente las claves del diccionario de entrada.

    Args:
        diccionario_de_diccionarios (dict): Diccionario con estructura:
            {
                "nombre_campo1": {clave: valor, ...},
                "nombre_campo2": {clave: valor, ...}
            }

    Returns:
        dict: Diccionario fusionado con estructura {clave: {nombre_campo1: valor, nombre_campo2: valor}}
    """
    # Obtener las claves (nombres de los campos) del diccionario principal
    nombres_campos = list(diccionario_de_diccionarios.keys())

    if len(nombres_campos) != 2:
        raise ValueError("El diccionario debe contener exactamente 2 campos")

    campo1_nombre = nombres_campos[0]
    campo2_nombre = nombres_campos[1]

    campo1_datos = diccionario_de_diccionarios[campo1_nombre]
    campo2_datos = diccionario_de_diccionarios[campo2_nombre]

    fusionado = {}

    # Obtener todas las claves únicas de ambos diccionarios
    todas_las_claves = set(campo1_datos.keys()) | set(campo2_datos.keys())

    for clave in todas_las_claves:
        valor1 = campo1_datos.get(clave, 0)
        valor2 = campo2_datos.get(clave, 0)

        # Solo agregar si ambos valores son diferentes de cero
        if valor1 != 0 and valor2 != 0:
            fusionado[clave] = {campo1_nombre: valor1, campo2_nombre: valor2}

    return fusionado


# %% [markdown]
# ### Formatear progresiva


# %%
def formatear_progresiva(distancia, decimales=0):
    """
    Convierte una distancia en metros a notación de progresiva.

    Parámetros:
    - distancia: int o float, la distancia en metros.
    - decimales: int, número de decimales a mostrar en la parte de los metros.

    Retorna:
    - str: progresiva en formato 'K+XXX' con los decimales indicados.
    """
    if not isinstance(distancia, (int, float)):
        raise ValueError("La distancia debe ser un número (int o float).")
    if not isinstance(decimales, int) or decimales < 0:
        raise ValueError("Los decimales deben ser un entero no negativo.")

    km = int(distancia) // 1000
    metros = distancia - (km * 1000)

    formato_metros = f"{metros:0.{decimales}f}".zfill(
        3 + (1 if decimales > 0 else 0) + decimales
    )
    return f"{km}+{formato_metros}"


# %% [markdown]
# ### Calcular avance


# %%
def calcular_avance(programado, ejecutado):
    """
    Calcula el porcentaje de avance basado en lo programado y lo ejecutado.

    Si lo programado es 0 y lo ejecutado es mayor a 0, devuelve 'ejecución adelantada'.
    Si ambos son 0, devuelve 0.0.
    En cualquier otro caso, devuelve el porcentaje (0-1) como float redondeado a 2 decimales.
    """
    if programado == 0:
        if ejecutado > 0:
            return "Ejec. adelantada"
        else:
            return 0.0
    else:
        porcentaje = ejecutado / programado
        return porcentaje


# %% [markdown]
# ### Ordenar por centena


# %%
def ordenar_por_centena(data: Any) -> List[Dict[str, Any]]:
    """
    Toma un dict (o un JSON en formato str) cuyas claves acaban en número
    y devuelve una lista de dicts {'key':…, 'value':…} ordenada por ese número.
    Compatible con Firestore (to_dict()) y JSON.
    """
    # Si viene como cadena JSON, lo convertimos
    if isinstance(data, str):
        data = json.loads(data)

    # Aseguramos que sea dict
    if not isinstance(data, dict):
        raise ValueError(
            "Se esperaba un diccionario o un string JSON que represente un diccionario."
        )

    pattern = re.compile(r"(\d+)$")

    def obtener_clave_numerica(item):
        clave = str(item[0])  # Convertimos clave a string en caso no lo sea
        match = pattern.search(clave)
        if match:
            return int(match.group(1))
        else:
            return float("inf")  # Opcional: claves sin número al final se van al final

    sorted_items = sorted(data.items(), key=obtener_clave_numerica)

    return [{"key": k, "value": v} for k, v in sorted_items]


# %% [markdown]
# ### Clave grupo


# %%
def clave_grupo(item):
    return int(item["key"][2:]) // 100  # 101→1, 201→2, etc.


# %% [markdown]
# ## Carga de datos
#

# %% [markdown]
# ### Firebase
#

# %%
# 1. Busca el .env en el directorio actual o en cualquiera de los padres
dotenv_path = find_dotenv()
if not dotenv_path:
    raise FileNotFoundError(
        "No se encontró ningún archivo .env en este directorio ni en sus padres."
    )
load_dotenv(dotenv_path)

# 2. Define el root del proyecto como la carpeta que contiene el .env
project_root = Path(dotenv_path).parent

# 3. Obtén la ruta relativa de las credenciales desde la variable de entorno
rel_cred_path = os.getenv("FIRESTORE_CREDENTIALS")
if not rel_cred_path:
    raise RuntimeError("No existe la variable FIRESTORE_CREDENTIALS en el .env")

# 4. Construye la ruta absoluta al JSON
cred_path = Path(rel_cred_path)
if not cred_path.is_absolute():
    cred_path = (project_root / cred_path).resolve()

if not cred_path.exists():
    raise FileNotFoundError(f"No existe el archivo de credenciales en: {cred_path}")

# 5. Carga las credenciales y crea el cliente de Firestore
credentials = service_account.Credentials.from_service_account_file(str(cred_path))
client = firestore.Client(credentials=credentials, project=credentials.project_id)

# 6. Prueba que funcione
print("Colecciones disponibles:", [c.id for c in client.collections()])

# %%
db = firestore.Client(credentials=credentials, project=credentials.project_id)

# %% [markdown]
# #### Documento del proyecto firebase

# %%
doc_proyecto_firebase = db.collection("rutinarios").document(proyecto).get().to_dict()

pprint.pprint(doc_proyecto_firebase)

# %% [markdown]
# #### Contrato
#

# %%
contrato = doc_proyecto_firebase["contrato"]
pprint.pprint(contrato)

# %%
monto_contrato = contrato["monto_contrato"]
print(monto_contrato)

# %% [markdown]
# #### Expediente técnico firebase

# %%
expediente_tecnico_firebase = doc_proyecto_firebase["expediente"]

pprint.pprint(expediente_tecnico_firebase)

# %% [markdown]
# #### Progresiva de inicio y fin del expediente

# %%
progresiva_inicio = expediente_tecnico_firebase["coordenadas"]["inicio"]["progresiva"]
progresiva_fin = expediente_tecnico_firebase["coordenadas"]["fin"]["progresiva"]

print(progresiva_inicio)
print(progresiva_fin)

# %% [markdown]
# #### Valorización programada mensual
#

# %%
desembolsos = (
    db.collection("rutinarios")
    .document(proyecto)
    .collection("presupuestos")
    .document("desembolsos")
    .get()
    .to_dict()
)
cronogramas_desembolsos = desembolsos["cronograma_desembolsos"]
pprint.pprint(cronogramas_desembolsos)

# %%
desembolso_current_month = cronogramas_desembolsos[str(mes)]
print(desembolso_current_month["mantenimiento_con_igv"])

# %% [markdown]
# #### Cargas de trabajo mensual presentadas por el contratista
#

# %%
valorizaciones = (
    db.collection("rutinarios")
    .document(proyecto)
    .collection("valorizaciones")
    .document(str(mes))
    .get()
    .to_dict()
)
cargas_trabajo_contratista = valorizaciones["cargas_trabajo_contratista_inicial"]
print(cargas_trabajo_contratista)

# %% [markdown]
# #### Cargas de trabajo del expediente técnico

# %%
cargas_trabajo_expediente_tecnico = doc_proyecto_firebase["expediente"][
    "cargas_trabajo"
]

pprint.pprint(cargas_trabajo_expediente_tecnico)

# %% [markdown]
# #### Precios unitarios del expediente técnico

# %%
precios_unitarios_expediente_tecnico = doc_proyecto_firebase["expediente"][
    "precios_unitarios"
]

pprint.pprint(precios_unitarios_expediente_tecnico)

# %% [markdown]
# ### Pickle

# %% [markdown]
# #### Cargas de trabajo programadas

# %%
# Concatenar la ruta completa al archivo .pkl
ruta_archivo = os.path.join("src", "data", proyecto, f"{proyecto}_cargas_trabajo.pkl")

# Leer el archivo pickle
with open(ruta_archivo, "rb") as f:
    cargas_trabajo_programadas_anualmente = pickle.load(f)

cargas_trabajo_programadas_anualmente.tail(15)

# %%
# eliminando el total
cargas_trabajo_programadas_anualmente = cargas_trabajo_programadas_anualmente.iloc[:-1]

# %%
cargas_trabajo_programadas_current_month = cargas_trabajo_programadas_anualmente[
    f"2025-{mes:02d}"
].to_dict()
pprint.pprint(cargas_trabajo_programadas_current_month)

# %%
cargas_trabajo_programadas_anualmente.index.to_list()

# %% [markdown]
# #### Cronograma anual

# %%
# Concatenar la ruta completa al archivo .pkl
ruta_archivo = os.path.join("src", "data", proyecto, f"{proyecto}_cronograma_anual.pkl")

# Leer el archivo pickle
with open(ruta_archivo, "rb") as f:
    df_cronograma_anual = pickle.load(f)

df_cronograma_anual.head(15)

# %% [markdown]
# ### JSON

# %% [markdown]
# #### Actividades

# %%
ruta_actividades = os.path.join("src", "data", "general_data", "actividades.json")
with open(ruta_actividades, "r", encoding="utf-8") as archivo:
    actividades = json.load(archivo)
# Ahora 'datos' es un diccionario de Python
print(actividades)

# %% [markdown]
# ## Cálculos
#

# %% [markdown]
# ### Cargas de trabajo y pu de expediente tecnico


# %%
def funcion_input(x):
    cargas_trabajo_contratista = {
        "MR301": 5409.77,
        "MR203": 42.42,
        "MR201": 2272.73,
        "MR101": 2.31,
        "MR104": 17.01,
        "MR102": x,
        "MR701": 3.87,
        "MR401": 5.87,
    }

    datos_cargas_trabajo_expediente_tecnico = fusionar_diccionarios(
        {
            "precio_unitario": precios_unitarios_expediente_tecnico,
            "carga_trabajo": cargas_trabajo_expediente_tecnico,
        }
    )

    pprint.pprint(datos_cargas_trabajo_expediente_tecnico)

    # %%
    # Crear DataFrame usando pd.DataFrame.from_dict() con orient='index'
    df_cargas_trabajo_expediente = pd.DataFrame.from_dict(
        datos_cargas_trabajo_expediente_tecnico, orient="index"
    )

    # Resetear el índice para convertir las claves MR en una columna
    df_cargas_trabajo_expediente = df_cargas_trabajo_expediente.reset_index().rename(
        columns={"index": "codigo_MR"}
    )

    # %%
    # Agregar columna parcial
    df_cargas_trabajo_expediente["parcial"] = (
        df_cargas_trabajo_expediente["precio_unitario"]
        * df_cargas_trabajo_expediente["carga_trabajo"]
    )

    # %%
    df_cargas_trabajo_expediente.head()

    # %%
    # Calcular el total
    costo_directo = df_cargas_trabajo_expediente["parcial"].sum()
    print("costo_directo", costo_directo)

    # %%
    costo_total_expediente = calculadora_costo_total(costo_directo)
    print(costo_total_expediente["total"])

    # %%
    # Agregar columna parcial
    df_cargas_trabajo_expediente["precio_unitario_actualizado"] = (
        df_cargas_trabajo_expediente["precio_unitario"]
        * (monto_contrato / costo_total_expediente["total"])
    )

    df_cargas_trabajo_expediente["parcial_actualizado"] = (
        df_cargas_trabajo_expediente["precio_unitario_actualizado"]
        * df_cargas_trabajo_expediente["carga_trabajo"]
    )

    # Calcular el total
    costo_directo_actualizado = df_cargas_trabajo_expediente[
        "parcial_actualizado"
    ].sum()

    print(f"El costo directo es: {costo_directo_actualizado}")

    # %%
    df_cargas_trabajo_expediente.head(10)

    # %%
    pago_costo_total_contratista = calculadora_costo_total(costo_directo_actualizado)
    print(pago_costo_total_contratista["total"])

    # %%
    dict_precios_unitarios_actualizados = dict(
        zip(
            df_cargas_trabajo_expediente["codigo_MR"],
            df_cargas_trabajo_expediente["precio_unitario_actualizado"],
        )
    )

    pprint.pprint(dict_precios_unitarios_actualizados)

    # %% [markdown]
    # ### Cálculo de pago de acuerdo a cargas de trabajo
    #

    # %%
    pago_costo_directo_parciales_contratista = calcular_costos_unitarios(
        dict_precios_unitarios_actualizados, cargas_trabajo_contratista
    )
    pprint.pprint(pago_costo_directo_parciales_contratista)

    # %% [markdown]
    # ##### Visualizacion en dataframe
    #

    # %%
    df_pago_costo_directo_parciales_contratista = pd.DataFrame.from_dict(
        pago_costo_directo_parciales_contratista, orient="index"
    )

    df_pago_costo_directo_parciales_contratista = (
        df_pago_costo_directo_parciales_contratista.reset_index().rename(
            columns={"index": "codigo_MR"}
        )
    )

    df_pago_costo_directo_parciales_contratista = (
        df_pago_costo_directo_parciales_contratista.rename(columns={0: "monto_pago"})
    )

    df_pago_costo_directo_parciales_contratista

    # %%
    # Ordenar el DataFrame por la columna 'monto_pago'
    # Por defecto, el orden es ascendente (de menor a mayor)
    df_ordenado = df_pago_costo_directo_parciales_contratista.sort_values(
        by="monto_pago", ascending=False
    )

    print("\nDataFrame Ordenado por 'monto_pago' (ascendente):")
    print(df_ordenado)

    # %%
    # Lambda que suma todos los valores de un diccionario
    sumar_valores = lambda d: sum(d.values())

    # %%
    pago_costo_directo_contratista = sumar_valores(
        pago_costo_directo_parciales_contratista
    )
    print(pago_costo_directo_contratista)

    # %%
    pago_costo_total_contratista = calculadora_costo_total(
        pago_costo_directo_contratista
    )
    return pago_costo_total_contratista["total"]


target_output = 8382.4

# Necesitas una estimación inicial (guess) para el método de Newton-Raphson.
# Una buena estimación inicial puede ayudar a la convergencia y a encontrar la raíz correcta
# si hay múltiples raíces.
initial_guess = 245


def function_to_find_root(x, target_output_val):
    """
    Esta es la función g(x) = f(x) - target_output_val.
    Queremos encontrar el 'x' para el cual g(x) = 0.
    """
    return funcion_input(x) - target_output_val


result = opt.newton(function_to_find_root, initial_guess, args=(target_output,))

print("resultado final")
print(result)
