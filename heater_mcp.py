from mcp_server import MCPServer
from heater import Heater



class HeaterMCPServer(MCPServer):

    def __init__(self,port: int, heater: Heater):
        super().__init__("heater", port)
        self.heater = heater

        @self.mcp.resource("resource://power", description="Current energy consumption in Watt")
        def get_power() -> int:
            return heater.power

        @self.mcp.resource("resource://heating_rods_active", description="Number of active heating rods")
        def get_heating_rods_active() -> int:
            return heater.heating_rods_active

        @self.mcp.tool("resource://heating_rods_activation", description="set the number of active heating rods")
        def heating_rods_activation(new_num: int) -> None:
            self.heater.set_heating_rods_active(new_num)


# npx @modelcontextprotocol/inspector