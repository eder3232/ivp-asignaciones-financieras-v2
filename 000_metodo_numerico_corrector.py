# %% [markdown]
# # Asignaciones financieras
#

# %% [markdown]
# ## Datos de proyecto en análisis
#

# %%
proyecto = "callacalla"
mes = 5
anio = 2025

# %% [markdown]
# ## Librerias necesarias
#

# %%
import pandas as pd
import scipy.optimize as opt
import os
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

# %% [markdown]
# ## Funciones utiles

# %% [markdown]
# ### Calculadora de costo total

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
# #### Multiplicar el precio unitario actualizado por la carga trabajo


# %%
def calcular_costos_unitarios(
    dict_precios_unitarios_actualizados, cargas_trabajo_contratista
):
    """
    Multiplica cada carga de trabajo del contratista por su precio unitario
    correspondiente.

    Args:
        dict_precios_unitarios_actualizados (dict): mapea código → precio unitario.
        cargas_trabajo_contratista (dict): mapea código → carga de trabajo.

    Returns:
        dict: mapea código → precio total (precio unitario * carga).

    Raises:
        KeyError: si alguna clave de cargas_trabajo_contratista no existe en
                  dict_precios_unitarios_actualizados.
    """
    # Comprobar que no falte ninguna clave
    faltantes = set(cargas_trabajo_contratista) - set(
        dict_precios_unitarios_actualizados
    )
    if faltantes:
        raise KeyError(f"Faltan precios unitarios para las claves: {faltantes}")

    # Generar el diccionario resultado
    resultado = {
        clave: dict_precios_unitarios_actualizados[clave]
        * cargas_trabajo_contratista[clave]
        for clave in cargas_trabajo_contratista
    }
    return resultado


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

# %%
# 4. Define la ruta a tu documento anidado
colec_raiz = "rutinarios"
doc_proyecto = proyecto  # puede ser tu variable proyecto
colec_valoriz = "presupuestos"
id_valoriz = "desembolsos"

doc_ref = (
    db.collection(colec_raiz)
    .document(doc_proyecto)
    .collection(colec_valoriz)
    .document(id_valoriz)
)

# %%
data_mantenimiento_res = doc_ref.get()

print(data_mantenimiento_res)

if not data_mantenimiento_res.exists:
    print(f"El documento {doc_ref.path} no existe.")

data_mantenimiento = data_mantenimiento_res.to_dict()
print(data_mantenimiento)

# %% [markdown]
# #### Contrato

# %%
# 4. Define la ruta a tu documento anidado
colec_raiz = "rutinarios"
doc_proyecto = proyecto  # puede ser tu variable proyecto
colec_valoriz = "presupuestos"
id_valoriz = "desembolsos"

doc_ref = db.collection(colec_raiz).document(doc_proyecto)

# %%
mantenimiento = doc_ref.get().to_dict()
contrato = mantenimiento["contrato"]
print(contrato)

# %%
monto_contrato = contrato["monto_contrato"]
print(monto_contrato)

# %% [markdown]
# #### Valorización programada mensual

# %%
# 4. Define la ruta a tu documento anidado
doc_proyecto = proyecto  # puede ser tu variable proyecto
colec_valoriz = "presupuestos"
id_valoriz = "desembolsos"

doc_ref = (
    db.collection("rutinarios")
    .document(doc_proyecto)
    .collection(colec_valoriz)
    .document(id_valoriz)
)

desembolsos = doc_ref.get().to_dict()
cronograma_desembolsos = desembolsos["cronograma_desembolsos"]
print(cronograma_desembolsos)


# %%
desembolso_current_month = cronograma_desembolsos[str(mes)]
print(desembolso_current_month["mantenimiento_con_igv"])


def funcion_input(x):
    cargas_trabajo_contratista = {
        "MR101": 0.99,
        "MR301": 3903.83,
        "MR103": 5.01,
        "MR102": x,
        "MR203": 44.45,
        "MR206": 33.91,
        "MR104": 10.17,
        "MR701": 3.43,
    }

    datos_cargas_trabajo_expediente_tecnico = {
        "MR101": {"precio_unitario": 265.30, "carga_trabajo": 7.95},
        "MR102": {"precio_unitario": 10.27, "carga_trabajo": 2558.43},
        "MR103": {"precio_unitario": 21.0, "carga_trabajo": 20.03},
        "MR104": {"precio_unitario": 17.50, "carga_trabajo": 71.20},
        "MR203": {"precio_unitario": 5.25, "carga_trabajo": 333.36},
        "MR206": {"precio_unitario": 3.6, "carga_trabajo": 237.37},
        "MR301": {"precio_unitario": 0.14, "carga_trabajo": 31230.64},
        "MR401": {"precio_unitario": 11.42, "carga_trabajo": 15.97},
        "MR601": {"precio_unitario": 2.10, "carga_trabajo": 39.73},
        "MR701": {"precio_unitario": 43.75, "carga_trabajo": 17.16},
    }

    # Crear DataFrame usando pd.DataFrame.from_dict() con orient='index'
    df_cargas_trabajo_expediente = pd.DataFrame.from_dict(
        datos_cargas_trabajo_expediente_tecnico, orient="index"
    )

    # Resetear el índice para convertir las claves MR en una columna
    df_cargas_trabajo_expediente = df_cargas_trabajo_expediente.reset_index().rename(
        columns={"index": "codigo_MR"}
    )

    # Agregar columna parcial
    df_cargas_trabajo_expediente["parcial"] = (
        df_cargas_trabajo_expediente["precio_unitario"]
        * df_cargas_trabajo_expediente["carga_trabajo"]
    )

    # Calcular el total
    costo_directo = df_cargas_trabajo_expediente["parcial"].sum()

    costo_total_expediente = calculadora_costo_total(costo_directo)

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

    dict_precios_unitarios_actualizados = dict(
        zip(
            df_cargas_trabajo_expediente["codigo_MR"],
            df_cargas_trabajo_expediente["precio_unitario_actualizado"],
        )
    )

    # Cálculo de pago de acuerdo a cargas de trabajo
    pago_costo_directo_parciales_contratista = calcular_costos_unitarios(
        dict_precios_unitarios_actualizados, cargas_trabajo_contratista
    )

    # Lambda que suma todos los valores de un diccionario
    sumar_valores = lambda d: sum(d.values())

    pago_costo_directo_contratista = sumar_valores(
        pago_costo_directo_parciales_contratista
    )

    pago_costo_total_contratista = calculadora_costo_total(
        pago_costo_directo_contratista
    )

    return pago_costo_total_contratista["total"]


target_output = 7686.04

# Necesitas una estimación inicial (guess) para el método de Newton-Raphson.
# Una buena estimación inicial puede ayudar a la convergencia y a encontrar la raíz correcta
# si hay múltiples raíces.
initial_guess = 3880


def function_to_find_root(x, target_output_val):
    """
    Esta es la función g(x) = f(x) - target_output_val.
    Queremos encontrar el 'x' para el cual g(x) = 0.
    """
    return funcion_input(x) - target_output_val


result = opt.newton(function_to_find_root, 3880, args=(target_output,))

print("resultado final")
print(result)
