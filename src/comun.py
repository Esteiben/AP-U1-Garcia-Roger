
"""Configuracion, bitacoras Lamport y cliente TCP de AforoSeguro."""

import json
import socket
import threading
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar_config():
    valores = {}
    archivo = RAIZ / "config.properties"
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip()

    return {
        "aforo": int(valores["aforo"]),
        "token": valores["token"],
        "host": valores["host"],
        "puerto": int(valores["puerto_coordinador"]),
        "latido": float(valores.get("latido_segundos", 2)),
        "caida": float(valores.get("caida_segundos", 6)),
    }


class Proceso:
    """Un reloj y un archivo de eventos por proceso real (0, 1, 2, 3)."""

    def __init__(self, identificador):
        self.id = identificador
        self.candado = threading.Lock()
        carpeta = RAIZ / "logs"
        carpeta.mkdir(parents=True, exist_ok=True)
        self.archivo = carpeta / f"{identificador}.log"
        self.lamport = 0

        # Si se reinicia una puerta, la marca no retrocede en su bitacora.
        if self.archivo.exists():
            for linea in self.archivo.read_text(encoding="utf-8").splitlines():
                partes = linea.split(";", 3)
                try:
                    if len(partes) == 4 and int(partes[1]) == identificador:
                        self.lamport = max(self.lamport, int(partes[0]))
                except ValueError:
                    continue

    def registrar(self, evento, detalle, recibido=None):
        with self.candado:
            if recibido is None:
                self.lamport += 1
            else:
                self.lamport = max(self.lamport, int(recibido)) + 1

            detalle = str(detalle).replace("\n", " ").replace(";", ",")
            with self.archivo.open("a", encoding="utf-8") as salida:
                salida.write(f"{self.lamport};{self.id};{evento};{detalle}\n")
            return self.lamport


def pedir(config, proceso, puerta, tipo, token=None, timeout=3):
    """Hace una solicitud JSON por conexion; retorna respuesta o None."""
    req_id = uuid.uuid4().hex[:12]
    marca = proceso.registrar("ENVIO", f"req={req_id} tipo={tipo} puerta={puerta}")
    solicitud = {
        "tipo": tipo,
        "token": config["token"] if token is None else token,
        "puerta": puerta,
        "lamport": marca,
        "req_id": req_id,
    }

    try:
        with socket.create_connection((config["host"], config["puerto"]), timeout=timeout) as conexion:
            conexion.settimeout(timeout)
            datos = json.dumps(solicitud, ensure_ascii=False) + "\n"
            conexion.sendall(datos.encode("utf-8"))
            with conexion.makefile("r", encoding="utf-8") as entrada:
                linea = entrada.readline()

        if not linea:
            raise ConnectionError("conexion cerrada sin respuesta")
        respuesta = json.loads(linea)
        if not isinstance(respuesta, dict) or "lamport" not in respuesta:
            raise ValueError("respuesta mal formada")
        proceso.registrar(
            "RECEPCION",
            f"req={req_id} resultado={respuesta.get('resultado')}",
            recibido=respuesta["lamport"],
        )
        return respuesta
    except (OSError, ValueError, TypeError) as error:
        proceso.registrar("ERROR_RED", f"req={req_id} detalle={error}")
        return None
