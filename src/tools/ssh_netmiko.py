import os
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv

# Try to import netmiko, but don't fail immediately if not installed
try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False

load_dotenv()

logger = logging.getLogger(__name__)

MOCK_SSH = os.getenv("MOCK_SSH", "False").lower() == "true"
DEFAULT_USERNAME = os.getenv("DEFAULT_SSH_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("DEFAULT_SSH_PASSWORD", "cisco")
DEFAULT_SECRET = os.getenv("DEFAULT_SSH_SECRET", "cisco")


class SSHTool:
    """
    Công cụ quản lý kết nối SSH qua Netmiko.
    """
    
    @staticmethod
    def _execute_mock(device_ip: str, commands: List[str]) -> Dict[str, str]:
        """Chạy giả lập lệnh SSH cho mục đích test."""
        import time; time.sleep(1.5) # Fake network delay
        logger.info(f"[MOCK] Kết nối tới {device_ip}")
        results = {}
        for cmd in commands:
            logger.info(f"[MOCK] Running command: {cmd}")
            if "show vlan" in cmd.lower():
                results[cmd] = "VLAN Name Status Ports\n1 default active Gi0/1\n10 ENGINEERING suspended\n"
            elif "show ip int brief" in cmd.lower() or "show ip interface brief" in cmd.lower():
                results[cmd] = "Interface IP-Address OK? Method Status Protocol\nGi0/1 192.168.1.1 YES NVRAM up up\nGi0/2 unassigned YES unset administratively down down\n"
            elif "show log" in cmd.lower() or "show logging" in cmd.lower():
                results[cmd] = "%LINK-3-UPDOWN: Interface GigabitEthernet0/2, changed state to down\n%SPANTREE-2-BLOCK_PVID_LOCAL: Inconsistent local vlan."
            else:
                results[cmd] = f"Command '{cmd}' executed successfully (MOCK output)."
        return results

    @staticmethod
    def execute_commands(device_ip: str, commands: List[str], device_type: str = "cisco_ios", username: str = None, password: str = None, simulation: bool = False) -> Dict[str, str]:
        """
        Thực thi danh sách các lệnh show qua SSH trên thiết bị.
        Trả về dictionary { "command_1": "output_1", "command_2": "output_2" }.
        """
        if MOCK_SSH or not NETMIKO_AVAILABLE or simulation:
            if not NETMIKO_AVAILABLE and not simulation:
                logger.warning("Netmiko is not installed. Falling back to MOCK mode.")
            return SSHTool._execute_mock(device_ip, commands)
        
        user = username or DEFAULT_USERNAME
        pwd = password or DEFAULT_PASSWORD
        
        device = {
            "device_type": device_type,
            "host": device_ip,
            "username": user,
            "password": pwd,
            "secret": DEFAULT_SECRET,
            "timeout": 15,
            "global_delay_factor": 2, # Help with slow emulation instances like GNS3
        }

        results = {}
        connection = None
        try:
            logger.info(f"Đang kết nối SSH tới {device_ip} ({device_type})...")
            connection = ConnectHandler(**device)
            # Enter enable mode if needed
            if not connection.check_enable_mode():
                connection.enable()
                
            for cmd in commands:
                logger.info(f"Đang chạy lệnh trên {device_ip}: '{cmd}'")
                output = connection.send_command(cmd)
                results[cmd] = output
                
        except NetmikoAuthenticationException:
            logger.error(f"Sai tài khoản/mật khẩu khi kết nối {device_ip}")
            results["error"] = "SSH Authentication failed. Check credentials."
        except NetmikoTimeoutException:
            logger.error(f"Timeout khi kết nối {device_ip}. Thiết bị có thể bị down.")
            results["error"] = "SSH Connection timed out. Device unreachable."
        except Exception as e:
            logger.error(f"Lỗi SSH không mong muốn ({device_ip}): {str(e)}")
            results["error"] = f"SSH error: {str(e)}"
        finally:
            if connection:
                connection.disconnect()
                logger.info(f"Đã ngắt kết nối SSH với {device_ip}")
                
        return results

    @staticmethod
    def apply_config(device_ip: str, config_commands: List[str], device_type: str = "cisco_ios", username: str = None, password: str = None, simulation: bool = False) -> str:
        """
        Gửi các lệnh cấu hình (configuration commands) tới thiết bị.
        Returns message kết quả.
        """
        if MOCK_SSH or not NETMIKO_AVAILABLE or simulation:
            logger.info(f"[MOCK] Pushing config to {device_ip}:\n" + "\n".join(config_commands))
            import time; time.sleep(1) # Fake delay
            return "Config applied successfully (MOCK)."
            
        user = username or DEFAULT_USERNAME
        pwd = password or DEFAULT_PASSWORD
        
        device = {
            "device_type": device_type,
            "host": device_ip,
            "username": user,
            "password": pwd,
            "secret": DEFAULT_SECRET,
        }
        
        try:
            logger.info(f"Đang kết nối để đẩy cấu hình tới {device_ip}...")
            # Automatically enters config mode
            with ConnectHandler(**device) as connection:
                if not connection.check_enable_mode():
                    connection.enable()
                output = connection.send_config_set(config_commands)
                logger.info("Đẩy cấu hình thành công.")
                return output
        except Exception as e:
            logger.error(f"Lỗi cấu hình {device_ip}: {str(e)}")
            return f"Error executing config: {str(e)}"
