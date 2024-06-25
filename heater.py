import json
from requests import Session
from datetime import datetime, timedelta
from typing import List, Optional
from threading import Thread
from redzoo.math.display import duration
from time import sleep
from string import Template
from threading import RLock
from redzoo.database.simple import SimpleDB
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




class HeatingRod:

    def __init__(self, shelly: Shelly3Pro, id: int, directory: str):
        self.__shelly = shelly
        self.last_activation_time = datetime.now()
        self.last_deactivation_time = datetime.now()
        self.id = id
        self.is_activated = False
        self.__heating_secs_per_day = SimpleDB("heater_" + str(id), sync_period_sec=60, directory=directory)
        self.deactivate()

    def sync(self):
        try:
            new_is_activated = self.__shelly.query(self.id)
            if new_is_activated == False and self.is_activated == True:
                self.deactivate(reason="due to sync")
            elif new_is_activated == True and self.is_activated == False:
                self.activate(reason="due to sync")
        except Exception as e:
            logging.warning("sync failed: " + str(e))

    def activate(self, reason: str = None):
        self.last_activation_time = datetime.now()
        if not self.is_activated:
            info = ""
            if reason is not None:
                info = "(" + reason + ")"
            logging.info(self.__str__() + " activated " + info)
        self.__shelly.switch(self.id, True)
        self.is_activated = True

    def deactivate(self, reason: str = None):
        try:
            if self.is_activated:
                self.last_deactivation_time = datetime.now()
                heating_time = (datetime.now() - self.last_activation_time)
                day = datetime.now().strftime('%j')
                self.__heating_secs_per_day.put(day, self.__heating_secs_per_day.get(day, 0) + heating_time.total_seconds(), ttl_sec=366*24*60*60)
                info = "heating time " + duration(heating_time.total_seconds(), 1)
                if reason is not None:
                    info = reason + "; " + info
                logging.info(self.__str__() + " deactivated (" + info + ")")
            self.__shelly.switch(self.id, False)
            self.is_activated = False
        except Exception as e:
            logging.warning("error occurred deactivating " + str(e))

    def heating_secs_of_day(self, day_of_year: int) -> Optional[int]:
        secs = self.__heating_secs_per_day.get(str(day_of_year), -1)
        if secs > 0:
            return secs
        else:
            return None

    def __str__(self):
        return "heating rod " + str(self.id)



class Heater:

    def __init__(self, addr: str, directory: str, power_step: int = 500):
        self.__lock = RLock()
        self.__is_running = True
        self.__listener = lambda: None    # "empty" listener
        self.power_step = power_step
        self.__shelly = Shelly3Pro(addr)
        self.__heating_rods = [HeatingRod(self.__shelly, 0, directory), HeatingRod(self.__shelly, 1, directory), HeatingRod(self.__shelly, 2, directory)]
        self.__last_time_decreased = datetime.now() - timedelta(minutes=10)
        self.__last_time_increased = datetime.now() - timedelta(minutes=10)

    def set_listener(self, listener):
        self.__listener = listener

    def __heater_consumption_per_day(self, day_of_year: int) -> int:
        secs_list = [heating_rod.heating_secs_of_day(day_of_year) for heating_rod in self.__heating_rods]
        heater_secs_today = sum([secs for secs in secs_list if secs is not None])
        heater_hours_today = heater_secs_today / (60*60)
        power = int(heater_hours_today * self.power_step)
        return power

    @property
    def heater_consumption_today(self) -> int:
        today = int(datetime.now().strftime('%j'))
        return self.__heater_consumption_per_day(today)

    @property
    def __heater_consumption_list_current_year(self) -> List[int]:
        current_day = int(datetime.now().strftime('%j'))
        consumption_per_day = [self.__heater_consumption_per_day(day_of_year) for day_of_year in range(0, current_day+1)]
        return [consumption for consumption in consumption_per_day if consumption is not None]

    @property
    def heater_consumption_current_year(self) -> int:
        return sum(self.__heater_consumption_list_current_year)

    @property
    def heater_consumption_estimated_year(self) -> int:
        consumptions_per_day = self.__heater_consumption_list_current_year
        if len(consumptions_per_day) > 0:
            return int(sum(consumptions_per_day) * 365 / len(consumptions_per_day))
        else:
            return 0

    @property
    def num_heating_rods_active(self) -> int:
        return len([heating_rod for heating_rod in self.__heating_rods if heating_rod.is_activated])

    @property
    def __sorted_heating_rods(self) -> List[HeatingRod]:
        heating_rod_list = list(self.__heating_rods)
        for i in range(0, datetime.now().day):
            heater = heating_rod_list.pop(0)
            heating_rod_list.append(heater)
        return heating_rod_list

    def get_heating_rod(self, id: int) -> HeatingRod:
        for heater in self.__heating_rods:
            if heater.id == id:
                return heater
        return None

    @property
    def power(self) -> int:
        return self.num_heating_rods_active * self.power_step

    @property
    def max_power(self) -> int:
        return 3 * self.power_step

    def set_power(self, new_power: int):
        if new_power <= 0:
            num_required_rods = 0
        else:
            num_required_rods = int(new_power / self.power_step)

        if num_required_rods > self.num_heating_rods_active:
            self.increase()
        elif num_required_rods < self.num_heating_rods_active:
            self.decrease()

    def increase(self):
        with self.__lock:
            if datetime.now() > (self.__last_time_increased + timedelta(minutes=1 + self.num_heating_rods_active)):
                self.__last_time_increased = datetime.now()
                for heating_rod in [heating_rod for heating_rod in self.__sorted_heating_rods if not heating_rod.is_activated]:
                    heating_rod.activate()          # increase heater power (1 heater only)
                    break
            else:
                logging.debug("reject increase (last increase=" + self.__last_time_increased.strftime("%H:%M:%S") + "; " + str((datetime.now() - self.__last_time_increased).total_seconds()) + " sec ago)")

    def decrease(self, reason: str = None):
        with self.__lock:
            if datetime.now() > (self.__last_time_decreased + timedelta(seconds=10)):
                self.__last_time_decreased = datetime.now()
                for heating_rod in [heating_rod for heating_rod in self.__sorted_heating_rods if heating_rod.is_activated]:
                    heating_rod.deactivate(reason)        # decrease heater power consumption (1 heater only)
                    break
            else:
                logging.debug("reject decrease (last decrease=" + self.__last_time_decreased.strftime("%H:%M:%S") + "; " + str((datetime.now() - self.__last_time_decreased).total_seconds()) + " sec ago)")

    def __sync(self):
        for heating_rods in self.__heating_rods:
            heating_rods.sync()
        self.__listener()

    def stop(self):
        self.__is_running = False

    def start(self):
        Thread(target=self.__register_scripts, daemon=True).start()
        Thread(target=self.__measure, daemon=True).start()
        Thread(target=self.__statistics, daemon=True).start()
        Thread(target=self.__auto_decrease, daemon=True).start()
        Thread(target=self.__auto_restart_scripts, daemon=True).start()

    def __measure(self):
        while self.__is_running:
            try:
                self.__sync()
            except Exception as e:
                logging.warning("error occurred on sync " + str(e))
            sleep(59)

    def __statistics(self):
        last_day_reported = -1
        while self.__is_running:
            try:
                now = datetime.now()
                current_day = int(now.strftime("%d"))
                if current_day != last_day_reported and now.hour >= 19:
                    last_day_reported = current_day
                    logging.info("heater consumption today:          " + str(round(self.heater_consumption_today/1000,1)) + " kWh")
                    logging.info("heater consumption current year:   " + str(round(self.heater_consumption_current_year/1000,1)) + " kWh")
                    logging.info("heater consumption estimated year: " + str(round(self.heater_consumption_estimated_year/1000,1)) + " kWh")
            except Exception as e:
                logging.warning("error occurred on statistics " + str(e))
            sleep(10 * 60)

    def __auto_decrease(self):
        while self.__is_running:
            try:
                auto_decrease_time_min = 17
                if datetime.now() > (self.__last_time_decreased + timedelta(minutes=auto_decrease_time_min)):
                   self.decrease(reason="due to auto decrease each " + str(auto_decrease_time_min) + " min")
            except Exception as e:
                logging.warning("error occurred on __auto_decrease " + str(e))
            sleep(60)

    def __auto_restart_scripts(self):
        while self.__is_running:
            try:
                for id in range (0, 3):
                    self.__shelly.restart_script(id+1)
            except Exception as e:
                logging.warning("error occurred on __auto_restart_scripts " + str(e))
            sleep(7 * 60 * 60)

    def __register_scripts(self):
        for id in range (0, 3):
            self.__shelly.upload_script(id+1, SHELLY_SCRIPT_TEMPLATE.substitute({"id": id}))

