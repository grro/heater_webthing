import logging
from datetime import datetime, timedelta
from typing import List, Optional
from threading import Thread
from redzoo.math.display import duration
from time import sleep
from threading import RLock
from redzoo.database.simple import SimpleDB
from shelly import Shelly3Pro, SHELLY_SCRIPT_TEMPLATE





class HeatingRod:

    def __init__(self, shelly: Shelly3Pro, id: int, directory: str):
        self.__shelly = shelly
        self.last_activation_time = datetime.now()
        self.last_deactivation_time = datetime.now()
        self.id = id
        self.is_activated = False
        self.__heating_secs_per_day = SimpleDB("heater_" + str(id), sync_period_sec=60, directory=directory)
        self.deactivate()
        self.__minute_of_day_active = [False] * 24*60
        Thread(target=self.__record_loop, daemon=True).start()

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

    def __record_loop(self):
        while True:
            try:
                now = datetime.now()
                minutes_of_day = now.hour*60 + now.minute
                self.__minute_of_day_active[minutes_of_day] = self.is_activated
            except Exception as e:
                logging.warning(str(e))
            sleep(35)

    def consumed_power(self, window_size_minutes: int) -> int:
        now = datetime.now()
        minutes_of_day = now.hour*60 + now.minute
        if minutes_of_day > window_size_minutes:
            watt_minutes= 0
            for minute in (minutes_of_day-window_size_minutes, minutes_of_day):
                if self.__minute_of_day_active[minute]:
                    watt_minutes += 1
            if watt_minutes > 0:
                return round(60 * window_size_minutes / watt_minutes)
        return 0



    def __str__(self):
        return "heating rod " + str(self.id)



class Heater:

    def __init__(self, addr: str, directory: str, heating_rod_power: int = 510):
        self.__lock = RLock()
        self.__is_running = True
        self.__listener = lambda: None    # "empty" listener
        self.heating_rod_power = heating_rod_power
        self.__shelly = Shelly3Pro(addr)
        self.__heating_rods = [HeatingRod(self.__shelly, 0, directory), HeatingRod(self.__shelly, 1, directory), HeatingRod(self.__shelly, 2, directory)]
        self.last_time_heating = datetime.now()
        self.__last_time_auto_decreased = datetime.now()
        self.last_time_power_updated = datetime.now()

    def set_listener(self, listener):
        self.__listener = listener

    def __heater_consumption_per_day(self, day_of_year: int) -> int:
        secs_list = [heating_rod.heating_secs_of_day(day_of_year) for heating_rod in self.__heating_rods]
        heater_secs_today = sum([secs for secs in secs_list if secs is not None])
        heater_hours_today = heater_secs_today / (60*60)
        return int(heater_hours_today * self.heating_rod_power)

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
    def heating_rods_active(self) -> int:
        return len([heating_rod for heating_rod in self.__heating_rods if heating_rod.is_activated])

    @property
    def power(self) -> int:
        return self.heating_rod_power * len([heating_rod for heating_rod in self.__heating_rods if heating_rod.is_activated])

    def consumed_power(self, window_size_minutes: int) -> int:
        return sum([heating_rod.consumed_power(window_size_minutes) for heating_rod in self.__heating_rods])

    def set_heating_rods_active(self, new_num: int, reason: str = None):
        # increase
        if self.heating_rods_active < new_num:
            if new_num <= self.heating_rods:
                for heating_rod in [heating_rod for heating_rod in self.__sorted_heating_rods if not heating_rod.is_activated]:
                    heating_rod.activate()          # increase heater power (1 heater only)
                    self.last_time_power_updated = datetime.now()
                    logging.info(str(self.heating_rods_active) + " rods active")
                    break
        # decrease
        elif new_num < self.heating_rods_active:
            if new_num >= 0:
                for heating_rod in [heating_rod for heating_rod in self.__sorted_heating_rods if heating_rod.is_activated]:
                    heating_rod.deactivate(reason)        # decrease heater power consumption (1 heater only)
                    self.last_time_power_updated = datetime.now()
                    logging.info(str(self.heating_rods_active) + " rods active")
                    break

        if self.heating_rods_active > 0:
            self.last_time_heating = datetime.now()


    @property
    def __sorted_heating_rods(self) -> List[HeatingRod]:
        heating_rod_list = list(self.__heating_rods)
        for i in range(0, datetime.now().day):
            heater = heating_rod_list.pop(0)
            heating_rod_list.append(heater)
        return heating_rod_list

    def get_heating_rod(self, id: int) -> Optional[HeatingRod]:
        for heater in self.__heating_rods:
            if heater.id == id:
                return heater
        return None

    @property
    def heating_rods(self) -> int:
        return len(self.__heating_rods)

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
        reported_date = datetime.now() - timedelta(days=1)
        while self.__is_running:
            try:
                now = datetime.now()
                if now > (reported_date + timedelta(hours=3)):
                    reported_date = now
                    logging.info("heater consumption today:          " + str(round(self.heater_consumption_today)) + " Watt")
                    logging.info("heater consumption current year:   " + str(round(self.heater_consumption_current_year/1000,1)) + " kWh")
                    logging.info("heater consumption estimated year: " + str(round(self.heater_consumption_estimated_year/1000,1)) + " kWh")
            except Exception as e:
                logging.warning("error occurred on statistics " + str(e))
            sleep(10 * 60)

    def __auto_decrease(self):
        auto_decrease_time_min = 23
        while self.__is_running:
            try:
                if self.heating_rods_active > 0:
                    if datetime.now() > (self.__last_time_auto_decreased + timedelta(minutes=auto_decrease_time_min)):
                        self.__last_time_auto_decreased = datetime.now()
                        self.set_heating_rods_active(self.heating_rods_active - 1, reason="due to auto decrease each " + str(auto_decrease_time_min) + " min")
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

