import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from heater import Heater


class HeaterHttpHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logging.debug(format, *args)

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def _properties(self) -> dict:
        heater: Heater = self.server.heater
        return {
            "power": heater.power,
            "heating_rod_power": heater.HEATER_ROD_POWER,
            "heating_rods": heater.heating_rods,
            "heating_rods_active": heater.heating_rods_active,
            "heating_rod0_activated": heater.get_heating_rod(0).is_activated,
            "heating_rod1_activated": heater.get_heating_rod(1).is_activated,
            "heating_rod2_activated": heater.get_heating_rod(2).is_activated,
            "status": heater.status,
            "heater_consumption_today": heater.heater_consumption_today,
            "heater_consumption_current_year": heater.heater_consumption_current_year,
            "heater_consumption_estimated_year": heater.heater_consumption_estimated_year,
            "last_time_power_updated": heater.last_time_power_updated.strftime("%Y-%m-%dT%H:%M"),
            "last_time_heating": heater.last_time_heating.strftime("%Y-%m-%dT%H:%M"),
            "heater_consumption_last_15_min": heater.consumed_power(15),
            "heater_consumption_last_30_min": heater.consumed_power(30),
            "heater_consumption_last_60_min": heater.consumed_power(60),
        }

    def do_GET(self):
        path = self.path.rstrip("/")
        if path == "" or path == "/properties":
            self._send_json(self._properties())
        elif path.startswith("/properties/"):
            name = path.split("/properties/", 1)[1]
            props = self._properties()
            if name in props:
                self._send_json({name: props[name]})
            else:
                self._send_error(404, f"unknown property '{name}'")
        else:
            self._send_error(404, "not found")

    def do_PUT(self):
        path = self.path.rstrip("/")
        if path == "/properties/heating_rods_active":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                new_num = int(body.get("heating_rods_active", body.get("value")))
            except Exception:
                self._send_error(400, "expected JSON with 'heating_rods_active' integer")
                return
            heater: Heater = self.server.heater
            if not (0 <= new_num <= heater.heating_rods):
                self._send_error(400, f"value must be 0..{heater.heating_rods}")
                return
            heater.set_heating_rods_active(new_num)
            self._send_json({"heating_rods_active": heater.heating_rods_active})
        else:
            self._send_error(405, "property is read-only or unknown")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


class HeaterHttpServer:

    def __init__(self, port: int, heater: Heater):
        self._server = HTTPServer(("", port), HeaterHttpHandler)
        self._server.heater = heater
        self._thread = None
        self._port = port

    def start(self):
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logging.info("HTTP server started on port %d", self._port)

    def stop(self):
        self._server.shutdown()
        logging.info("HTTP server stopped")
