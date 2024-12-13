from webthing import (SingleThing, Property, Thing, Value, WebThingServer)
import sys
import logging
import tornado.ioloop
from heater import Heater




class HeaterThing(Thing):

    # regarding capabilities refer https://iot.mozilla.org/schemas
    # there is also another schema registry http://iotschema.org/docs/full.html not used by webthing

    def __init__(self, description: str, heater: Heater):
        Thing.__init__(
            self,
            'urn:dev:ops:heater-1',
            'Heater',
            ['MultiLevelSensor'],
            description
        )
        self.ioloop = tornado.ioloop.IOLoop.current()
        self.heater = heater
        self.heater.set_listener(self.on_value_changed)

        self.power = Value(heater.power)
        self.add_property(
            Property(self,
                     'power',
                     self.power,
                     metadata={
                         'title': 'power',
                         "type": "number",
                         'description': 'the heater power (watt)',
                         'readOnly': True,
                     }))

        self.heating_rod_power = Value(heater.heating_rod_power)
        self.add_property(
            Property(self,
                     'heating_rod_power',
                     self.heating_rod_power,
                     metadata={
                         'title': 'heating_rod_power',
                         "type": "number",
                         'description': 'the power of a heating rod (watt) ',
                         'readOnly': True,
                     }))

        self.heating_rods = Value(heater.heating_rods)
        self.add_property(
            Property(self,
                     'heating_rods',
                     self.heating_rods,
                     metadata={
                         'title': 'heating_rods',
                         "type": "number",
                         'description': 'the number of heater rods',
                         'readOnly': True,
                     }))

        self.heating_rods_active = Value(heater.heating_rods_active, heater.set_heating_rods_active)
        self.add_property(
            Property(self,
                     'heating_rods_active',
                     self.heating_rods_active,
                     metadata={
                         'title': 'heating_rods_active',
                         "type": "number",
                         'description': 'num heating rods active',
                         'readOnly': False,
                     }))


        self.heating_rod0_activated = Value(heater.get_heating_rod(0))
        self.add_property(
            Property(self,
                     'heating_rod0_activated',
                     self.heating_rod0_activated,
                     metadata={
                         'title': 'heating_rod0_activated',
                         "type": "boolean",
                         'description': 'true, if heating rod 0 is activated',
                         'readOnly': True,
                     }))

        self.heating_rod1_activated = Value(heater.get_heating_rod(1))
        self.add_property(
            Property(self,
                     'heating_rod1_activated',
                     self.heating_rod1_activated,
                     metadata={
                         'title': 'heating_rod1_activated',
                         "type": "boolean",
                         'description': 'true, if heating rod 1 is activated',
                         'readOnly': True,
                     }))

        self.heating_rod2_activated = Value(heater.get_heating_rod(2))
        self.add_property(
            Property(self,
                     'heating_rod2_activated',
                     self.heating_rod2_activated,
                     metadata={
                         'title': 'heating_rod2_activated',
                         "type": "boolean",
                         'description': 'true, if heating rod 2 is activated',
                         'readOnly': True,
                     }))

        self.heater_consumption_today = Value(heater.heater_consumption_today)
        self.add_property(
            Property(self,
                     'heater_consumption_today',
                     self.heater_consumption_today,
                     metadata={
                         'title': 'heater_consumption_today',
                         "type": "number",
                         'description': 'heater power consumption current day',
                         'readOnly': True,
                     }))

        self.heater_consumption_current_year = Value(heater.heater_consumption_current_year)
        self.add_property(
            Property(self,
                     'heater_consumption_current_year',
                     self.heater_consumption_current_year,
                     metadata={
                         'title': 'heater_consumption_current_year',
                         "type": "number",
                         'description': 'heater power consumption current year',
                         'readOnly': True,
                     }))

        self.heater_consumption_estimated_year = Value(heater.heater_consumption_estimated_year)
        self.add_property(
            Property(self,
                     'heater_consumption_estimated_year',
                     self.heater_consumption_estimated_year,
                     metadata={
                         'title': 'heater_consumption_estimated_year',
                         "type": "number",
                         'description': 'heater power consumption current year estimated',
                         'readOnly': True,
                     }))


        self.last_time_power_updated = Value(heater.last_time_power_updated.strftime("%Y-%m-%dT%H:%M"))
        self.add_property(
            Property(self,
                     'last_time_power_updated',
                     self.last_time_power_updated,
                     metadata={
                         'title': 'last_time_power_updated',
                         "type": "string",
                         'description': 'the last time power updated ISO8601 string (UTC)',
                         'readOnly': True,
                     }))


        self.last_time_heating = Value(heater.last_time_heating.strftime("%Y-%m-%dT%H:%M"))
        self.add_property(
            Property(self,
                     'last_time_heating',
                     self.last_time_heating,
                     metadata={
                         'title': 'last_time_heating',
                         "type": "string",
                         'description': 'the last time heater active ISO8601 string (UTC)',
                         'readOnly': True,
                     }))


    def on_value_changed(self):
        self.ioloop.add_callback(self._on_value_changed)

    def _on_value_changed(self):
        self.power.notify_of_external_update(self.heater.power)
        self.heating_rod_power.notify_of_external_update(self.heater.heating_rod_power)
        self.heating_rods.notify_of_external_update(self.heater.heating_rods)
        self.heating_rods_active.notify_of_external_update(self.heater.heating_rods_active)
        self.heating_rod0_activated.notify_of_external_update(self.heater.get_heating_rod(0).is_activated)
        self.heating_rod1_activated.notify_of_external_update(self.heater.get_heating_rod(1).is_activated)
        self.heating_rod2_activated.notify_of_external_update(self.heater.get_heating_rod(2).is_activated)
        self.heater_consumption_today.notify_of_external_update(self.heater.heater_consumption_today)
        self.heater_consumption_today.notify_of_external_update(self.heater.heater_consumption_today)
        self.last_time_power_updated.notify_of_external_update(self.heater.last_time_power_updated.strftime("%Y-%m-%dT%H:%M"))
        self.heater_consumption_current_year.notify_of_external_update(self.heater.heater_consumption_current_year)
        self.heater_consumption_estimated_year.notify_of_external_update(self.heater.heater_consumption_estimated_year)
        self.last_time_heating.notify_of_external_update(self.heater.last_time_heating.strftime("%Y-%m-%dT%H:%M"))


def run_server(description: str, port: int, addr: str, directory: str):
    heater = Heater(addr, directory)
    server = WebThingServer(SingleThing(HeaterThing(description, heater)), port=port, disable_host_validation=True)
    try:
        logging.info('starting the server http://localhost:' + str(port) + " (addr=" + addr + ")")
        heater.start()
        server.start()
    except KeyboardInterrupt:
        logging.info('stopping the server')
        heater.stop()
        server.stop()
        logging.info('done')


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
    logging.getLogger('tornado.access').setLevel(logging.ERROR)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    run_server("description", int(sys.argv[1]), sys.argv[2], sys.argv[3])
