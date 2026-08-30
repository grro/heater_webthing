import asyncio
import logging
import threading
import socket
from threading import Thread
from time import sleep
from typing import List, Dict, Any, Optional, Callable

from fastmcp import FastMCP
from pydantic import AnyUrl, TypeAdapter
from zeroconf import IPVersion, ServiceInfo, Zeroconf

from heater import Heater

logger = logging.getLogger(__name__)


class MDNS:
    def __init__(self):
        self.registered: Dict[str, ServiceInfo] = dict()
        self.zc = Zeroconf(ip_version=IPVersion.V4Only)
        self.service_type = "_mcp._tcp.local."
        self.hostname = socket.gethostname()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            self.local_ip = s.getsockname()[0]
        finally:
            s.close()

    def register_mdns(self, name: str, port: int):
        try:
            service_name = f"{name}.{self.service_type}"
            service_info = ServiceInfo(
                type_=self.service_type,
                name=service_name,
                addresses=[socket.inet_aton(self.local_ip)],
                port=port,
                properties={
                    "version": "1.0",
                    "path": "/sse",
                    "server_type": "fastmcp"
                },
                server=f"{self.hostname}.local.",
            )

            logging.info(f"mDNS: Registering {service_name} at {self.local_ip}:{port}")
            self.zc.register_service(service_info)
            self.registered[name] = service_info
        except Exception as e:
            logging.error(f"mDNS Registration failed: {e}")

    def unregister_mdns(self, name: str):
        service_info = self.registered.get(name)
        if service_info is not None:
            logging.info("mDNS: Unregistering service...")
            self.zc.unregister_service(service_info)
            self.zc.close()


class HeaterMCPServer:

    def __init__(self, port: int, heater: Heater):
        self.heater = heater
        self.name = "pv_heater"
        self.host = "0.0.0.0"
        self.port = port
        self.loop = asyncio.new_event_loop()
        self.is_running = False
        self.mcp = FastMCP(self.name)
        self.mdns = MDNS()

        @self.mcp.tool(name="get_heater_status",
                       description="Returns current power (W), active rods, rod capacity, recent consumption, and last heating time.")
        def get_heater_status() -> str:
            """
            Provides a real-time status report of the heating system.
            Use this to check the current load and physical limits of the heater.
            """
            last_heating = self.heater.last_time_heating.strftime("%Y-%m-%dT%H:%M") if self.heater.last_time_heating else "N/A"
            last_power_update = self.heater.last_time_power_updated.strftime("%Y-%m-%dT%H:%M") if self.heater.last_time_power_updated else "N/A"
            rod0 = "On" if self.heater.get_heating_rod(0).is_activated else "Off"
            rod1 = "On" if self.heater.get_heating_rod(1).is_activated else "Off"
            rod2 = "On" if self.heater.get_heating_rod(2).is_activated else "Off"
            return (
                f"Heater Status Overview:\n"
                f"- Current Power Draw: {self.heater.power} W\n"
                f"- Active Rods: {self.heater.heating_rods_active}\n"
                f"  - Rod 0: {rod0}\n"
                f"  - Rod 1: {rod1}\n"
                f"  - Rod 2: {rod2}\n"
                f"- Power per Rod: {self.heater.HEATER_ROD_POWER} W\n"
                f"- Hardware Limit: 3 rods total\n"
                f"- Consumption (last 15 min): {self.heater.consumed_power(15)} W\n"
                f"- Consumption (last 30 min): {self.heater.consumed_power(30)} W\n"
                f"- Consumption (last 60 min): {self.heater.consumed_power(60)} W\n"
                f"- Consumption (today): {self.heater.heater_consumption_today} W\n"
                f"- Consumption (current year): {self.heater.heater_consumption_current_year} W\n"
                f"- Consumption (estimated year): {self.heater.heater_consumption_estimated_year} W\n"
                f"- Last Time Heating: {last_heating}\n"
                f"- Last Power Update: {last_power_update}"
            )

        @self.mcp.tool(name="set_active_heating_rods",
                       description="Sets the number of active heating rods (Allowed: 0, 1, 2, or 3).")
        def set_active_heating_rods(new_num: int) -> str:
            """
            Adjusts the heater load.
            Each rod increases power consumption by 500W (check status for exact value).

            Args:
                new_num: Number of rods to activate (0 to 3).
            """
            try:
                if not (0 <= new_num <= self.heater.heating_rods):
                    return f"Error: Invalid number of rods ({new_num}). Please choose a value between 0 and {self.heater.heating_rods}."

                old_num = self.heater.heating_rods_active
                if old_num == new_num:
                    return f"No change required. Heater is already at {new_num} rods ({self.heater.power} W)."

                self.heater.set_heating_rods_active(new_num)

                return (f"Success: Active rods updated from {old_num} to {new_num}. "
                        f"Current heater consumption is now {self.heater.power} W.")

            except Exception as e:
                logging.warning(f"Hardware communication error setting rods to {new_num}: {e}", exc_info=True)
                return f"Error: Hardware communication failed. {str(e)}"

    async def __run(self) -> None:
        logger.info(f"MCP Server '{self.name}' running on http://{self.host}:{self.port}/sse")
        await self.mcp.run_async(transport="sse", host=self.host, port=self.port)


    def start(self):
        self.mdns.register_mdns(self.name, self.port)

        def _run_loop():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self.__run())
            finally:
                self.loop.close()

        thread = threading.Thread(target=_run_loop, daemon=True)
        thread.start()


    def stop(self):
        self.mdns.unregister_mdns(self.name)
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.is_running = False
        logging.info("MCP Server stopped")