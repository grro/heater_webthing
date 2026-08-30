from webthing import (SingleThing, Property, Thing, Value, WebThingServer)
import sys
import logging
from heater import Heater
from heater_webthing import HeaterThing
from heater_mcp import HeaterMCPServer
from heater_web import HeaterHttpServer




def run_server(description: str, port: int, addr: str, directory: str):
    heater = Heater(addr, directory)

    mcp_server = HeaterMCPServer(port+1, heater)
    http_server = HeaterHttpServer(port+2, heater)
    server = WebThingServer(SingleThing(HeaterThing(description, heater)), port=port, disable_host_validation=True)
    try:
        logging.info('starting the server http://localhost:' + str(port) + " (addr=" + addr + ")")
        heater.start()
        mcp_server.start()
        http_server.start()
        server.start()
    except KeyboardInterrupt:
        logging.info('stopping the server')
        heater.stop()
        mcp_server.stop()
        http_server.stop()
        server.stop()
        logging.info('done')


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
    logging.getLogger('tornado.access').setLevel(logging.ERROR)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    run_server("description", int(sys.argv[1]), sys.argv[2], sys.argv[3])
