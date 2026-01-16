from mcp_server import MCPServer
from heater import Heater



class HeaterMCPServer(MCPServer):

    def __init__(self,port: int, heater: Heater):
        super().__init__("heater", port)
        self.heater = heater

        @self.mcp.tool(name="get_heater_power", description="Current total heater energy consumption in Watt")
        def get_heater_power() -> int:
            return self.heater.power

        @self.mcp.tool(name="get_single_rod_power", description="Power consumption of a single heating rod in Watt")
        def get_heating_rod_power() -> int:
            return self.heater.HEATER_ROD_POWER

        @self.mcp.tool(name="get_active_heating_rods", description="Number of currently active heating rods")
        def get_active_heating_rods() -> int:
            return self.heater.heating_rods_active

        @self.mcp.tool(name="set_active_heating_rods", description="Set the number of active heating rods (control the heater)")
        def set_active_heating_rods(new_num: int) -> str:
            self.heater.set_heating_rods_active(new_num)
            return f"Active heating rods set to {new_num}"


# npx @modelcontextprotocol/inspector