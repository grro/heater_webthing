"""Shelly Pro 3 (Gen2 RPC) - Sicherheitsabschaltung fuer die PV-Heizstaebe.

Verifiziert gegen: SPSW-003XE16EU "Pro3", MAC C8F09E884250, Gen 2, FW 2.0.0
(fw_id 20260710-101217/2.0.0-g87fbfa4).
"""

import json
import logging
import threading
from string import Template

from requests import Session


# Sicherheitsabschaltung: laeuft ein Heizstab laenger als diese Zeit
# ununterbrochen, schaltet ihn das Shelly-Script selbst aus - unabhaengig
# von jeder uebergeordneten Regelung.
AUTO_OFF_MINUTES = 45

# HTTP-Timeouts. Ohne Timeout blockiert ein haengendes Geraet den Aufrufer
# unbegrenzt - in einem Regelkreis, der im Minutentakt tickt, ist das der
# Unterschied zwischen einem Fehlversuch und einem stehenden Task.
TIMEOUT_S = 10
TIMEOUT_UPLOAD_S = 15

# Shelly Pro 3: drei Relaiskanaele, keine Leistungsmessung.
SWITCH_IDS = (0, 1, 2)


# $switch_id ist die SWITCH-Nummer (0..2). Die Script-ID wird NICHT hier
# gesetzt - sie wird ueber den Script-Namen aufgeloest, siehe upload_script().
#
# Shelly.getComponentStatus(type_or_key, id): der id-Parameter ist optional,
# wenn ein voller Key uebergeben wird ("switch:0"). Dokumentiert fuer Gen2.
SHELLY_SCRIPT_TEMPLATE = Template('''
let t = null;

function arm() {
  if (t !== null) { Timer.clear(t); }
  t = Timer.set($off_after_ms, false, function() {
    t = null;
    Shelly.call("Switch.Set", {id: ${switch_id}, on: false});
    print("heater ${switch_id} is auto deactivated");
  }, null);
}

function disarm() {
  if (t !== null) { Timer.clear(t); t = null; }
}

Shelly.addStatusHandler(function(e) {
  if (e.component !== "switch:${switch_id}") return;
  if (e.delta.output === true) {
    arm();
  } else if (e.delta.output === false) {
    disarm();
  }
});

// Beim Start scharfstellen, falls der Stab bereits laeuft: der StatusHandler
// feuert nur auf Flanken, und ein Script-Neustart loescht seine Timer. Ohne
// diese Zeile haette ein gerade heizender Stab bis zum naechsten Aus/Ein
// keine Sicherheitsabschaltung - und genau das passiert bei jedem Deploy.
let st = Shelly.getComponentStatus("switch:${switch_id}");
if (st !== null && st !== undefined && st.output === true) {
  print("heater ${switch_id} was already on at script start - arming");
  arm();
}
''')


def build_auto_off_script(switch_id: int,
                          off_after_minutes: int = AUTO_OFF_MINUTES) -> str:
    """Rendert das Auto-Off-Script fuer EINEN Schaltkanal."""
    if switch_id not in SWITCH_IDS:
        raise ValueError("switch_id must be one of %s, got %r"
                         % (list(SWITCH_IDS), switch_id))
    if off_after_minutes <= 0:
        raise ValueError("off_after_minutes must be > 0, got %r" % off_after_minutes)
    return SHELLY_SCRIPT_TEMPLATE.substitute(
        switch_id=switch_id,
        off_after_ms=off_after_minutes * 60 * 1000,
    )


class ShellyError(Exception):
    pass


class Shelly3Pro:
    """Shelly Pro 3 ueber die Gen2-RPC-Schnittstelle.

    Alle Requests laufen serialisiert ueber eine Session: requests.Session ist
    nicht thread-safe, und das Geraet vertraegt ohnehin keine parallelen
    RPC-Aufrufe. Derselbe Lock schuetzt den Session-Austausch beim Reconnect.
    """

    def __init__(self, addr: str):
        self.addr = addr.rstrip('/')
        self.__session = Session()
        self.__lock = threading.Lock()

    # ---------- Transport ----------
    def __request(self, method: str, path: str, *, params=None, json_body=None,
                  timeout: int = TIMEOUT_S):
        uri = self.addr + path
        with self.__lock:
            try:
                if method == 'GET':
                    return self.__session.get(uri, params=params, timeout=timeout)
                data = json.dumps(json_body, ensure_ascii=False).encode('utf-8')
                return self.__session.post(uri, data=data, timeout=timeout)
            except Exception as e:
                self.__renew_session_locked()
                raise ShellyError("called %s got %s: %s"
                                  % (uri, type(e).__name__, e)) from e

    def __renew_session_locked(self):
        logging.info("renew session")
        try:
            self.__session.close()
        except Exception as e:
            logging.warning("session close failed: %s", e)
        self.__session = Session()

    def __rpc(self, path: str, *, params=None, json_body=None,
              timeout: int = TIMEOUT_S, what: str = ""):
        """Request + Status-Pruefung + JSON-Parsing in einem Schritt."""
        method = 'GET' if json_body is None else 'POST'
        resp = self.__request(method, path, params=params, json_body=json_body,
                              timeout=timeout)
        if resp.status_code != 200:
            raise ShellyError("%s got %d %s"
                              % (what or path, resp.status_code, resp.text))
        try:
            return resp.json()
        except Exception as e:
            raise ShellyError("%s unparsable: %s (%s)"
                              % (what or path, resp.text[:200], e)) from e

    # ---------- Geraet ----------
    def device_info(self) -> dict:
        return self.__rpc('/rpc/Shelly.GetDeviceInfo', what="Shelly.GetDeviceInfo")

    # ---------- Schalten ----------
    def query(self, switch_id: int) -> bool:
        data = self.__rpc('/rpc/Switch.GetStatus', params={'id': switch_id},
                          what="Switch.GetStatus(%d)" % switch_id)
        try:
            return bool(data['output'])
        except KeyError as e:
            raise ShellyError("Switch.GetStatus(%d): no 'output' in %s"
                              % (switch_id, data)) from e

    def switch(self, switch_id: int, on: bool):
        self.__rpc('/rpc/Switch.Set',
                   params={'id': switch_id, 'on': 'true' if on else 'false'},
                   what="Switch.Set(%d, %s)" % (switch_id, on))

    # ---------- Scripting ----------
    def install_auto_off(self, switch_id: int, off_after_minutes: int = AUTO_OFF_MINUTES) -> int:
        return self.upload_script(name="auto_off_" + str(switch_id), code=build_auto_off_script(switch_id, off_after_minutes),)

    def install_all_auto_off(self, off_after_minutes: int = AUTO_OFF_MINUTES) -> dict:
        """Alle drei Kanaele. Gibt {switch_id: script_id} zurueck."""
        return {sw: self.install_auto_off(sw, off_after_minutes) for sw in SWITCH_IDS}

    def list_scripts(self) -> dict:
        """{name: {"id": int, "enable": bool, "running": bool}}

        Script.List ist die einzige verlaessliche Quelle fuer die Existenz eines
        Scripts. Script.GetStatus antwortet auf eine unbekannte id mit HTTP 500
        (nicht 404, am Geraet nachgemessen) - ein transienter 500 waere damit von
        "gibt es nicht" ununterscheidbar und wuerde ein Duplikat anlegen.
        """
        data = self.__rpc('/rpc/Script.List', what="Script.List")
        out = {}
        for s in data.get('scripts', []):
            out[s['name']] = {"id": int(s['id']),
                              "enable": bool(s.get('enable', False)),
                              "running": bool(s.get('running', False))}
        return out

    def upload_script(self, name: str, code: str) -> int:
        """Laedt Code hoch - egal ob das Script schon existiert oder nicht.

        Identifiziert wird ueber den NAMEN; die Script-ID vergibt das Geraet.
        Gibt die verwendete Script-ID zurueck.
        """
        existing = self.list_scripts().get(name)

        if existing is not None:
            script_id = existing['id']
            self.__rpc('/rpc/Script.Stop', params={'id': script_id},
                       what="Script.Stop(%d)" % script_id)
            logging.debug("shelly script %d (%s) stopped", script_id, name)
        else:
            created = self.__rpc('/rpc/Script.Create', json_body={"name": name},
                                 timeout=TIMEOUT_UPLOAD_S, what="Script.Create(%s)" % name)
            try:
                script_id = int(created['id'])
            except (KeyError, TypeError, ValueError) as e:
                raise ShellyError("Script.Create(%s) gave no usable id: %s"
                                  % (name, created)) from e
            logging.info("shelly script '%s' created as id %d", name, script_id)

        # Frueher stand dieser Block im else-Zweig: ein bereits vorhandenes
        # Script wurde nur gestoppt und neu gestartet, der neue Code kam nie
        # auf das Geraet. Der Upload muss in BEIDEN Faellen laufen.
        self.__rpc('/rpc/Script.PutCode',
                   json_body={"id": script_id, "code": code, "append": False},
                   timeout=TIMEOUT_UPLOAD_S,
                   what="Script.PutCode(%d)" % script_id)
        logging.info("shelly script %d (%s) uploaded, %d bytes",
                     script_id, name, len(code))

        self.verify_script(script_id, code)
        self.enable_script(script_id)
        self.start_script(script_id)
        return script_id

    def verify_script(self, script_id: int, expected_code: str) -> bool:
        """Liest den Code zurueck und vergleicht ihn.

        Bewusst nicht fatal: liefert die Firmware Script.GetCode anders als
        erwartet, wird das nur geloggt - ein erfolgreicher Upload soll daran
        nicht scheitern.
        """
        try:
            data = self.__rpc('/rpc/Script.GetCode', params={'id': script_id},
                              timeout=TIMEOUT_UPLOAD_S,
                              what="Script.GetCode(%d)" % script_id)
            on_device = data['data']
        except (ShellyError, KeyError, TypeError) as e:
            logging.debug("cannot verify shelly script %d: %s", script_id, e)
            return False
        if on_device.strip() == expected_code.strip():
            logging.info("shelly script %d verified", script_id)
            return True
        logging.warning("shelly script %d MISMATCH after upload "
                        "(device %d bytes, expected %d bytes)",
                        script_id, len(on_device), len(expected_code))
        return False

    def enable_script(self, script_id: int):
        """Setzt 'Run on startup'."""
        try:
            self.__rpc('/rpc/Script.SetConfig',
                       params={'id': script_id,
                               'config': json.dumps({'enable': True})},
                       timeout=TIMEOUT_UPLOAD_S,
                       what="Script.SetConfig(%d)" % script_id)
            logging.debug("shelly script %d enabled", script_id)
        except ShellyError as e:
            logging.warning("could not enable shelly script %d: %s", script_id, e)

    def start_script(self, script_id: int):
        """Startet das Script, falls es nicht laeuft."""
        status = self.__rpc('/rpc/Script.GetStatus', params={'id': script_id},
                            what="Script.GetStatus(%d)" % script_id)
        if status.get('running'):
            logging.debug("shelly script %d already running", script_id)
            return
        self.__rpc('/rpc/Script.Start', params={'id': script_id}, what="Script.Start(%d)" % script_id)
        logging.info("shelly script %d started", script_id)