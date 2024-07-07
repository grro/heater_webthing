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
            'HeaterSwitch',
            ['MultiLevelSensor'],
            description
        )
        self.ioloop = tornado.ioloop.IOLoop.current()
        self.heater = heater
        self.heater.set_listener(self.on_value_changed)

        self.power = Value(heater.power, heater.set_power)
        self.add_property(
            Property(self,
                     'power',
                     self.power,
                     metadata={
                         'title': 'power',
                         "type": "integer",
                         'description': 'the heater power (watt)',
                         'readOnly': False,
                     }))

        self.power_step = Value(heater.power_step)
        self.add_property(
            Property(self,
                     'power_step',
                     self.power_step,
                     metadata={
                         'title': 'power_step',
                         "type": "integer",
                         'description': 'the heater power step (watt) ',
                         'readOnly': True,
                     }))

        self.num_rods = Value(heater.num_rods)
        self.add_property(
            Property(self,
                     'num_rods',
                     self.num_rods,
                     metadata={
                         'title': 'num_rods',
                         "type": "integer",
                         'description': 'the number of heater rods',
                         'readOnly': True,
                     }))

        self.max_power = Value(heater.max_power)
        self.add_property(
            Property(self,
                     'max_power',
                     self.max_power,
                     metadata={
                         'title': 'max_power',
                         "type": "integer",
                         'description': 'the maximum heater power (watt) ',
                         'readOnly': True,
                     }))

        self.num_heating_rods_active = Value(heater.num_heating_rods_active)
        self.add_property(
            Property(self,
                     'num_heating_rods_active',
                     self.num_heating_rods_active,
                     metadata={
                         'title': 'num_heating_rods_active',
                         "type": "integer",
                         'description': 'num heating rods active',
                         'readOnly': True,
                     }))


        self.num_heating_rod0_activated = Value(heater.get_heating_rod(0))
        self.add_property(
            Property(self,
                     'num_heating_rod0_activated',
                     self.num_heating_rod0_activated,
                     metadata={
                         'title': 'num_heating_rod0_activated',
                         "type": "boolean",
                         'description': 'true, if heating rod 0 is activated',
                         'readOnly': True,
                     }))

        self.num_heating_rod1_activated = Value(heater.get_heating_rod(1))
        self.add_property(
            Property(self,
                     'num_heating_rod1_activated',
                     self.num_heating_rod1_activated,
                     metadata={
                         'title': 'num_heating_rod1_activated',
                         "type": "boolean",
                         'description': 'true, if heating rod 1 is activated',
                         'readOnly': True,
                     }))

        self.num_heating_rod2_activated = Value(heater.get_heating_rod(2))
        self.add_property(
            Property(self,
                     'num_heating_rod2_activated',
                     self.num_heating_rod2_activated,
                     metadata={
                         'title': 'num_heating_rod2_activated',
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
                         "type": "integer",
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
                         "type": "integer",
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
                         "type": "integer",
                         'description': 'heater power consumption current year estimated',
                         'readOnly': True,
                     }))

    def on_value_changed(self):
        self.ioloop.add_callback(self._on_value_changed)

    def _on_value_changed(self):
        self.power.notify_of_external_update(self.heater.power)
        self.power_step.notify_of_external_update(self.heater.power_step)
        self.max_power.notify_of_external_update(self.heater.max_power)
        self.num_rods.notify_of_external_update(self.heater.num_rods)
        self.num_heating_rods_active.notify_of_external_update(self.heater.num_heating_rods_active)
        self.num_heating_rod0_activated.notify_of_external_update(self.heater.get_heating_rod(0).is_activated)
        self.num_heating_rod1_activated.notify_of_external_update(self.heater.get_heating_rod(1).is_activated)
        self.num_heating_rod2_activated.notify_of_external_update(self.heater.get_heating_rod(2).is_activated)
        self.heater_consumption_today.notify_of_external_update(self.heater.heater_consumption_today)
        self.heater_consumption_today.notify_of_external_update(self.heater.heater_consumption_today)
        self.heater_consumption_current_year.notify_of_external_update(self.heater.heater_consumption_current_year)
        self.heater_consumption_estimated_year.notify_of_external_update(self.heater.heater_consumption_estimated_year)


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
