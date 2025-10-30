import json
from requests import Session
from string import Template
import logging


SHELLY_SCRIPT_TEMPLATE = Template('''
    Shelly.addStatusHandler(function(e) {
     if (e.component === "switch:$id") {
        if (e.delta.output === true) {
          print("heater $id is on");
          Timer.set(45*60*1000, false, function (ud) {
                 Shelly.call("Switch.set", {'id': $id, 'on': false});
              }, null);
        } else {
          print("heater $id is off");
        }
      }
    });
''')



class Shelly3Pro:

    def __init__(self, addr: str):
        self.__session = Session()
        self.addr = addr

    def query(self, id: int) -> bool:
        uri = self.addr + '/rpc/Switch.GetStatus?id=' + str(id)
        try:
            resp = self.__session.get(uri, timeout=10)
            try:
                data = resp.json()
                return bool(data['output'])
            except Exception as e:
                raise Exception("called " + uri + " got " + str(resp.status_code) + " " + resp.text + " " + str(e))
        except Exception as e:
            self.__renew_session()
            raise e

    def switch(self, id: int, on: bool):
        uri = self.addr + '/rpc/Switch.Set?id=' + str(id) + '&on=' + ('true' if on else 'false')
        try:
            resp = self.__session.get(uri, timeout=10)
            if resp.status_code != 200:
                raise Exception("called " + uri + " got " + str(resp.status_code) + " " + resp.text)
        except Exception as e:
            self.__renew_session()
            raise Exception("called " + uri + " got " + str(e))

    def upload_script(self, id: int, code: str):
        uri = self.addr + '/rpc/Script.GetStatus?id=' + str(id)
        resp = self.__session.get(uri)
        script_exists = resp.status_code == 200
        if script_exists:
            uri = self.addr + '/rpc/Script.Stop?id=' + str(id)
            resp  = self.__session.get(uri)
            if resp.status_code == 200:
                logging.debug("shelly script " + str(id) + " stopped " + resp.text)
            else:
                logging.warning("could not stop shelly script " + str(id) + " " + resp.text)
        else:
            uri = self.addr + '/rpc/Script.Create?'
            req_data = json.dumps({"id": id, "name": "auto_off_" + str(id-1)}, ensure_ascii=False)
            resp = self.__session.post(uri, data=req_data.encode("utf-8"), timeout=15)
            if resp.status_code == 200:
                logging.debug("shelly script " + str(id) + " created " + resp.text)
            else:
                logging.warning("could not create shelly script " + str(id) + " " + resp.text)

            uri = self.addr + '/rpc/Script.PutCode'
            req_data = json.dumps({"id": id, "code": code, "append": False}, ensure_ascii=False)
            resp = self.__session.post(uri, data=req_data.encode("utf-8"), timeout=15)
            if resp.status_code == 200:
                logging.info("shelly script " + str(id) + " uploaded")
            else:
                logging.warning("could not upload shelly script " + str(id) + " " + resp.text)

        self.enable_script(id)
        self.restart_script(id)

    def enable_script(self, id: int):
        uri = self.addr + '/rpc/Script.SetConfig?id=' + str(id) + "&config={%22enable%22:true}"
        resp = self.__session.get(uri, timeout=15)
        if resp.status_code == 200:
            logging.debug("shelly script " + str(id) + " enabled " + resp.text)
        else:
            logging.debug("could not enable shelly script " + str(id) + " " + resp.text)


    def restart_script(self, id: int):
        uri = self.addr + '/rpc/Script.GetStatus?id=' + str(id)
        try:
            resp = self.__session.get(uri)
            if not resp.json()['running']:
                resp  = self.__session.get(self.addr + '/rpc/Script.Start?id=' + str(id))
                if resp.status_code == 200:
                    logging.info("shelly script " + str(id) + " (re)started")
                else:
                    logging.debug("could not (re)start shelly script " + str(id) + " " + resp.text)
        except Exception as e:
            self.__renew_session()
            logging.warning("called " + uri + " got " + str(e))

    def __renew_session(self):
        logging.info("renew session")
        try:
            self.__session.close()
        except Exception as e:
            logging.warning(str(e))
        self.__session = Session()


