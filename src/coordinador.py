
"""Coordinador TCP. Uso: python src/coordinador.py [--inseguro]"""

import argparse
import json
import socketserver
import threading
import time

from comun import Proceso, cargar_config


class EstadoAforo:
    def __init__(self, config, inseguro=False):
        self.config = config
        self.inseguro = inseguro
        self.proceso = Proceso(0)
        self.candado = threading.Lock()
        self.dentro = 0
        inicio = time.monotonic()
        self.ultimo_latido = {p: inicio for p in (1, 2, 3)}
        self.estados = {p: "SIN_LATIDO" for p in (1, 2, 3)}

    def fotografia(self):
        with self.candado:
            return {
                "dentro": self.dentro,
                "aforo": self.config["aforo"],
                "puertas": dict(self.estados),
            }

    def resolver(self, solicitud):
        tipo = solicitud.get("tipo")
        puerta = solicitud.get("puerta")
        req_id = solicitud.get("req_id", "sin-id")

        if solicitud.get("token") != self.config["token"]:
            self.proceso.registrar("TOKEN_INVALIDO", f"req={req_id} puerta={puerta}")
            return {"resultado": "RECHAZADA", "motivo": "token invalido"}

        if type(puerta) is not int or puerta not in (1, 2, 3):
            return {"resultado": "RECHAZADA", "motivo": "puerta invalida"}

        if tipo == "LATIDO":
            reactivada = False
            with self.candado:
                self.ultimo_latido[puerta] = time.monotonic()
                if self.estados[puerta] != "ACTIVA":
                    self.estados[puerta] = "ACTIVA"
                    reactivada = True
            if reactivada:
                self.proceso.registrar("PUERTA_ACTIVA", f"puerta={puerta}")
            return {"resultado": "PERMITIDA", "motivo": "latido recibido"}

        if tipo == "ENTRAR":
            if self.inseguro:
                # Deliberadamente NO protege lectura+escritura como una unidad.
                with self.candado:
                    habia_espacio = self.dentro < self.config["aforo"]
                if habia_espacio:
                    time.sleep(0.05)
                    with self.candado:
                        self.dentro += 1  # Sin segunda comprobacion: puede desbordar.
                    return {"resultado": "PERMITIDA", "motivo": "entrada insegura"}
            else:
                with self.candado:
                    if self.dentro < self.config["aforo"]:
                        self.dentro += 1
                        return {"resultado": "PERMITIDA", "motivo": "entrada aceptada"}
            return {"resultado": "RECHAZADA", "motivo": "aforo completo"}

        if tipo == "SALIR":
            with self.candado:
                if self.dentro == 0:
                    return {"resultado": "RECHAZADA", "motivo": "nadie dentro"}
                self.dentro -= 1
            return {"resultado": "PERMITIDA", "motivo": "salida registrada"}

        if tipo == "ESTADO":
            return {"resultado": "PERMITIDA", "motivo": "estado disponible"}

        return {"resultado": "RECHAZADA", "motivo": "tipo desconocido"}

    def vigilar(self, detener):
        while not detener.wait(0.25):
            ahora = time.monotonic()
            caidas = []
            with self.candado:
                for puerta, ultimo in self.ultimo_latido.items():
                    if ahora - ultimo >= self.config["caida"] and self.estados[puerta] != "CAIDA":
                        self.estados[puerta] = "CAIDA"
                        caidas.append(puerta)
            for puerta in caidas:
                self.proceso.registrar("PUERTA_CAIDA", f"puerta={puerta}")


class Manejador(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        linea = self.rfile.readline(65537)
        if not linea or len(linea) > 65536 or not linea.endswith(b"\n"):
            return
        estado = self.server.estado
        try:
            solicitud = json.loads(linea.decode("utf-8"))
            if not isinstance(solicitud, dict):
                raise ValueError("se esperaba un objeto JSON")
            marca_recibida = solicitud.get("lamport", 0)
            if type(marca_recibida) is not int or marca_recibida < 0:
                raise ValueError("lamport debe ser entero no negativo")
        except (ValueError, UnicodeDecodeError) as error:
            estado.proceso.registrar("ERROR_FORMATO", str(error))
            return

        req_id = solicitud.get("req_id", "sin-id")
        estado.proceso.registrar(
            "RECEPCION",
            f"req={req_id} tipo={solicitud.get('tipo')} puerta={solicitud.get('puerta')}",
            recibido=marca_recibida,
        )
        respuesta = estado.resolver(solicitud)
        respuesta.update(estado.fotografia())
        respuesta.update({"tipo": "RESPUESTA", "req_id": req_id})
        respuesta["lamport"] = estado.proceso.registrar(
            "ENVIO",
            f"req={req_id} resultado={respuesta['resultado']} motivo={respuesta['motivo']}",
        )
        try:
            self.wfile.write((json.dumps(respuesta, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()
        except OSError as error:
            estado.proceso.registrar("ERROR_RED", f"req={req_id} error={error}")


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inseguro", action="store_true")
    args = parser.parse_args()

    config = cargar_config()
    estado = EstadoAforo(config, args.inseguro)
    detener = threading.Event()
    hilo = threading.Thread(target=estado.vigilar, args=(detener,), daemon=True)
    hilo.start()

    modo = "INSEGURO" if args.inseguro else "SEGURO"
    try:
        with Servidor((config["host"], config["puerto"]), Manejador) as servidor:
            servidor.estado = estado
            print(f"Coordinador {modo} en {config['host']}:{config['puerto']} | aforo={config['aforo']}")
            print("Pulsa Ctrl+C para detenerlo")
            try:
                servidor.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                print("Coordinador detenido")
    finally:
        detener.set()


if __name__ == "__main__":
    main()
