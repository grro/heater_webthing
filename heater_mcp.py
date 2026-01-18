import logging
from heater import Heater
from mcplib.server import MCPServer

class HeaterMCPServer(MCPServer):
    """
    MCP Server for controlling a multi-rod water heater.
    Designed to balance electrical load with available PV energy surplus.
    """

    def __init__(self, port: int, heater: Heater):
        super().__init__("pv_heater", port)
        self.heater = heater

        @self.mcp.tool(name="get_heater_status",
                       description="Returns current power (W), active rods, and rod capacity.")
        def get_heater_status() -> str:
            """
            Provides a real-time status report of the heating system.
            Use this to check the current load and physical limits of the heater.
            """
            return (
                f"Heater Status Overview:\n"
                f"- Current Power Draw: {self.heater.power} W\n"
                f"- Active Rods: {self.heater.heating_rods_active}\n"
                f"- Power per Rod: {self.heater.HEATER_ROD_POWER} W\n"
                f"- Hardware Limit: 3 rods total"
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
                # 1. Validation check
                if not (0 <= new_num <= self.heater.HEATER_ROD_POWER):
                    return f"Error: Invalid number of rods ({new_num}). Please choose a value between 0 and {self.heater.HEATER_ROD_POWER}."

                # 2. Skip if already set to the same value
                old_num = self.heater.heating_rods_active
                if old_num == new_num:
                    return f"No change required. Heater is already at {new_num} rods ({self.heater.power} W)."

                # 3. Apply change
                self.heater.set_heating_rods_active(new_num)

                return (f"Success: Active rods updated from {old_num} to {new_num}. "
                        f"Current heater consumption is now {self.heater.power} W.")

            except Exception as e:
                logging.warning(f"Hardware communication error setting rods to {new_num}: {e}", exc_info=True)
                return f"Error: Hardware communication failed. {str(e)}"