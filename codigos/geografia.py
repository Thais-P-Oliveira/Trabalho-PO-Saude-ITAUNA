"""Utilitarios geograficos sem bibliotecas de projecao: limite municipal (IBGE) e distancias por haversine.

Distancias de cobertura: formula de haversine (R = 6371,0088 km), a mesma do modelo original.
Para desenhar mapas usa-se apenas uma conversao local graus -> km (equirretangular) em torno do centro
de Itauna; ela serve somente a visualizacao e nao entra em nenhum calculo de cobertura.
"""
import json
import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import transform
from caminhos import BASE

R_TERRA_KM = 6371.0088
LAT0, LON0 = -20.0750, -44.5758
LIMITE = BASE/'limite_municipal/itauna_3133808.geojson'


def projetar(lon, lat):
    """Conversao local (somente mapas): graus -> metros a partir de (LAT0, LON0)."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    x = np.radians(lon-LON0)*R_TERRA_KM*1000*np.cos(np.radians(LAT0))
    y = np.radians(lat-LAT0)*R_TERRA_KM*1000
    return x, y


def limite_municipal():
    dados = json.loads(LIMITE.read_text(encoding='utf-8'))
    geo = shape(dados['features'][0]['geometry'])
    return transform(lambda x, y, z=None: projetar(x, y), geo), geo


def distancias_haversine_km(lon1, lat1, lon2, lat2, fator_rota=1.0):
    p1 = np.radians(np.asarray(lat1, float))[:, None]
    p2 = np.radians(np.asarray(lat2, float))[None, :]
    dl = np.radians(np.asarray(lon2, float))[None, :]-np.radians(np.asarray(lon1, float))[:, None]
    a = np.sin((p2-p1)/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2*R_TERRA_KM*np.arcsin(np.sqrt(a))*fator_rota


def circulo(x, y, raio_km, resolucao=64):
    return Point(x, y).buffer(raio_km*1000.0, resolution=resolucao)
