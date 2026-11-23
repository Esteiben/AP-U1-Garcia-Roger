from pathlib import Path
import json
import socket
import threading
import uuid

RAIZ = Path(__file__).resolve().parent.parent


def cargar_config():
    valores = {}
    for linea in (RAIZ / "config.properties").read_text(encoding="utf-8").splitlines():
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
    def __init__(self, identificador):
        self.id = identificador
        self.candado = threading.Lock()
        ruta_logs = RAIZ / "logs"
        ruta_logs.mkdir(exist_ok=True)
        self.archivo = ruta_logs / f"{identificador}.log"
        self.lamport = 0
        if self.archivo.exists():
            for linea in self.archivo.read_text(encoding="utf-8").splitlines():
                try:
                    if int(linea.split(";", 2)[1]) == identificador:
                        self.lamport = max(self.lamport, int(linea.split(";", 1)[0]))
                except (ValueError, IndexError):
                    pass

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


def pedir(config, proceso, puerta, tipo, token=None, timeout=2.5):
    """Una peticion por conexion, delimitada por \n; retorna dict o None."""
    correlacion = uuid.uuid4().hex[:10]
    marca = proceso.registrar("ENVIO", f"req={correlacion} tipo={tipo} puerta={puerta}")
    solicitud = {
        "tipo": tipo,
        "token": config["token"] if token is None else token,
        "puerta": puerta,
        "lamport": marca,
        "req_id": correlacion,
    }
    datos = (json.dumps(solicitud, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with socket.create_connection((config["host"], config["puerto"]), timeout=timeout) as conexion:
            conexion.settimeout(timeout)
            conexion.sendall(datos)
            with conexion.makefile("r", encoding="utf-8") as entrada:
                linea = entrada.readline()
            if not linea:
                raise ConnectionError("el coordinador cerro la conexion sin responder")
            respuesta = json.loads(linea)
            proceso.registrar(
                "RECEPCION", f"req={correlacion} resultado={respuesta.get('resultado')}",
                recibido=respuesta["lamport"],
            )
            return respuesta
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        proceso.registrar("ERROR_RED", f"req={correlacion} detalle={error}")
        return None
