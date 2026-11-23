
"""Generador auxiliar: 30 ENTRAR simultaneos (10 por puerta)."""

import argparse
import json
import socket
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from comun import cargar_config


def solicitud_directa(config, puerta, tipo, token=None):
    """El auxiliar NO escribe en los logs 1,2,3: pertenecen a las puertas reales."""
    mensaje = {
        "tipo": tipo,
        "token": config["token"] if token is None else token,
        "puerta": puerta,
        "lamport": 1,  # Reloj inicial de cada cliente auxiliar independiente.
        "req_id": "carga-" + uuid.uuid4().hex[:12],
    }
    try:
        with socket.create_connection((config["host"], config["puerto"]), timeout=5) as conexion:
            conexion.settimeout(5)
            conexion.sendall((json.dumps(mensaje) + "\n").encode("utf-8"))
            with conexion.makefile("r", encoding="utf-8") as entrada:
                linea = entrada.readline()
        return json.loads(linea) if linea else None
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cantidad", type=int, default=30)
    parser.add_argument("--token-falso", action="store_true")
    args = parser.parse_args()
    if args.cantidad < 1 or args.cantidad > 100:
        parser.error("--cantidad debe estar entre 1 y 100")

    config = cargar_config()
    inicio = Barrier(args.cantidad)
    token = "token_incorrecto" if args.token_falso else None

    def tarea(indice):
        inicio.wait(timeout=10)
        respuesta = solicitud_directa(config, indice % 3 + 1, "ENTRAR", token=token)
        return "SIN_RESPUESTA" if respuesta is None else respuesta.get("resultado", "SIN_RESPUESTA")

    with ThreadPoolExecutor(max_workers=args.cantidad) as ejecutor:
        resultados = list(ejecutor.map(tarea, range(args.cantidad)))

    conteo = Counter(resultados)
    consulta = solicitud_directa(config, 1, "ESTADO")
    print("Solicitudes:", args.cantidad)
    print("Permitidas:", conteo["PERMITIDA"])
    print("Rechazadas:", conteo["RECHAZADA"])
    print("Sin respuesta:", conteo["SIN_RESPUESTA"])
    print("Dentro en coordinador:", consulta["dentro"] if consulta else "NO DISPONIBLE")


if __name__ == "__main__":
    main()
