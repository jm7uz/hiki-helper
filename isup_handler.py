# isup_handler.py
"""
ISUP Protocol Handler for Hikvision Terminals
Handles ISUP 4.0 and 5.0 protocols
"""

import socket
import struct
import threading
import json
from datetime import datetime
from typing import Dict, Tuple, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ISUPProtocolHandler:
    """ISUP Protocol Parser and Handler"""
    
    # ISUP Command codes
    CMD_REGISTER = 0x0001
    CMD_HEARTBEAT = 0x0002
    CMD_ACCESS_EVENT = 0x0010
    CMD_FACE_DATA = 0x0020
    CMD_CARD_EVENT = 0x0030
    CMD_ALARM = 0x0040
    
    # Response codes
    RESP_REGISTER = 0x8001
    RESP_HEARTBEAT = 0x8002
    RESP_ACCESS_EVENT = 0x8010
    RESP_FACE_DATA = 0x8020
    
    def __init__(self, device_id="garanttest1"):
        self.device_id = device_id
        self.events = []
        self.connected_devices = {}
        
    def parse_packet(self, data: bytes) -> Tuple[int, bytes]:
        """Parse ISUP packet and return command and payload"""
        
        # Log raw data for debugging
        logger.debug(f"Raw packet received: {data.hex()}")
        logger.debug(f"Packet length: {len(data)} bytes")
        
        if len(data) < 8:
            logger.warning("Packet too short")
            return 0, b''
        
        # Check for ISUP 5.0 header (0x5A5A5A5A)
        if data[:4] == b'\x5A\x5A\x5A\x5A':
            logger.info("ISUP 5.0 packet detected")
            return self._parse_isup5(data)
        
        # Check for ISUP 4.0 header (ISUP)
        elif data[:4] == b'ISUP':
            logger.info("ISUP 4.0 packet detected")
            return self._parse_isup4(data)
        
        # Check for alternative formats
        else:
            # Try to identify packet by structure
            logger.debug("Unknown packet format, trying alternative parsers")
            return self._parse_alternative(data)
    
    def _parse_isup4(self, data: bytes) -> Tuple[int, bytes]:
        """Parse ISUP 4.0 packet"""
        try:
            # ISUP 4.0 structure:
            # Header: 'ISUP' (4 bytes)
            # Version: 1 byte
            # Command: 1 byte
            # Length: 2 bytes
            # Payload: variable
            
            version = data[4]
            command = data[5]
            length = struct.unpack('>H', data[6:8])[0]
            payload = data[8:8+length] if length > 0 else b''
            
            logger.info(f"ISUP 4.0 - Version: {version}, Command: 0x{command:02X}, Length: {length}")
            
            return command, payload
            
        except Exception as e:
            logger.error(f"ISUP 4.0 parse error: {e}")
            return 0, b''
    
    def _parse_isup5(self, data: bytes) -> Tuple[int, bytes]:
        """Parse ISUP 5.0 packet"""
        try:
            # ISUP 5.0 structure:
            # Header: 0x5A5A5A5A (4 bytes)
            # Version: 2 bytes
            # Command: 2 bytes
            # Length: 4 bytes
            # Reserved: 8 bytes
            # Payload: variable
            
            if len(data) < 20:
                return 0, b''
            
            version = struct.unpack('<H', data[4:6])[0]
            command = struct.unpack('<H', data[6:8])[0]
            length = struct.unpack('<I', data[8:12])[0]
            # Skip reserved bytes
            payload = data[20:20+length] if length > 0 else b''
            
            logger.info(f"ISUP 5.0 - Version: {version}, Command: 0x{command:04X}, Length: {length}")
            
            return command, payload
            
        except Exception as e:
            logger.error(f"ISUP 5.0 parse error: {e}")
            return 0, b''
    
    def _parse_alternative(self, data: bytes) -> Tuple[int, bytes]:
        """Try alternative packet formats"""
        
        # Check if it's a simple registration packet
        if b'REG' in data or b'reg' in data:
            logger.info("Registration packet detected")
            return self.CMD_REGISTER, data
        
        # Check for heartbeat patterns
        if len(data) == 8 or len(data) == 16:
            logger.info("Possible heartbeat packet")
            return self.CMD_HEARTBEAT, data
        
        # Check for JSON format
        try:
            json_data = json.loads(data.decode('utf-8'))
            logger.info(f"JSON packet detected: {json_data}")
            return self.CMD_ACCESS_EVENT, data
        except:
            pass
        
        # Unknown format
        logger.warning(f"Unknown packet format: {data[:20].hex()}")
        return 0, data
    
    def process_command(self, command: int, payload: bytes, client_addr: Tuple) -> bytes:
        """Process command and generate response"""
        
        logger.info(f"Processing command: 0x{command:04X} from {client_addr}")
        
        if command == self.CMD_REGISTER:
            return self.handle_register(payload, client_addr)
        
        elif command == self.CMD_HEARTBEAT:
            return self.handle_heartbeat(payload, client_addr)
        
        elif command == self.CMD_ACCESS_EVENT:
            return self.handle_access_event(payload, client_addr)
        
        elif command == self.CMD_FACE_DATA:
            return self.handle_face_data(payload, client_addr)
        
        else:
            logger.warning(f"Unknown command: 0x{command:04X}")
            return self.create_ack_response(command | 0x8000)
    
    def handle_register(self, payload: bytes, client_addr: Tuple) -> bytes:
        """Handle device registration"""
        
        try:
            # Extract device info from payload
            device_info = self.parse_device_info(payload)
            
            # Store device info
            self.connected_devices[client_addr[0]] = {
                'address': client_addr,
                'registered_at': datetime.now().isoformat(),
                'device_info': device_info,
                'last_seen': datetime.now().isoformat()
            }
            
            logger.info(f"Device registered: {client_addr[0]} - {device_info}")
            
            # Create registration response
            return self.create_register_response()
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return self.create_error_response()
    
    def handle_heartbeat(self, payload: bytes, client_addr: Tuple) -> bytes:
        """Handle heartbeat"""
        
        # Update last seen
        if client_addr[0] in self.connected_devices:
            self.connected_devices[client_addr[0]]['last_seen'] = datetime.now().isoformat()
        
        logger.debug(f"Heartbeat from {client_addr[0]}")
        
        # Return heartbeat response with server time
        return self.create_heartbeat_response()
    
    def handle_access_event(self, payload: bytes, client_addr: Tuple) -> bytes:
        """Handle access/attendance event"""
        
        try:
            # Parse attendance event
            event = self.parse_attendance_event(payload)
            event['device_ip'] = client_addr[0]
            event['timestamp'] = datetime.now().isoformat()
            
            # Store event
            self.events.append(event)
            
            # Log event
            logger.info(f"Attendance Event: Employee {event.get('employee_no')} at {event['timestamp']}")
            
            # Save to file (temporary storage)
            with open('attendance_events.json', 'a') as f:
                json.dump(event, f)
                f.write('\n')
            
            # Return acknowledgment
            return self.create_event_response()
            
        except Exception as e:
            logger.error(f"Access event error: {e}")
            return self.create_error_response()
    
    def handle_face_data(self, payload: bytes, client_addr: Tuple) -> bytes:
        """Handle face data transfer"""
        
        logger.info(f"Face data received: {len(payload)} bytes from {client_addr[0]}")
        
        # TODO: Process and store face data
        
        return self.create_face_response()
    
    def parse_device_info(self, payload: bytes) -> Dict:
        """Parse device information from registration packet"""
        
        device_info = {}
        
        try:
            # Try to parse as structured data
            if len(payload) >= 32:
                device_info['device_id'] = payload[0:16].decode('utf-8', errors='ignore').strip('\x00')
                device_info['device_type'] = payload[16:32].decode('utf-8', errors='ignore').strip('\x00')
            else:
                # Parse as string
                device_info['raw'] = payload.decode('utf-8', errors='ignore')
        except:
            device_info['raw'] = payload.hex()
        
        return device_info
    
    def parse_attendance_event(self, payload: bytes) -> Dict:
        """Parse attendance event from payload"""
        
        event = {}
        
        try:
            # Try structured parsing first
            if len(payload) >= 20:
                # Common structure:
                # Employee No: 16 bytes
                # Card No: 16 bytes
                # Event Type: 1 byte
                # Verify Mode: 1 byte
                
                event['employee_no'] = payload[0:16].decode('utf-8', errors='ignore').strip('\x00')
                
                if len(payload) >= 32:
                    event['card_no'] = payload[16:32].decode('utf-8', errors='ignore').strip('\x00')
                
                if len(payload) > 32:
                    event['event_type'] = payload[32] if len(payload) > 32 else 0
                    event['verify_mode'] = payload[33] if len(payload) > 33 else 0
                    
                    # Verify mode: 1=Face, 2=Card, 3=Fingerprint, 4=Password
                    verify_modes = {1: 'face', 2: 'card', 3: 'fingerprint', 4: 'password'}
                    event['verify_method'] = verify_modes.get(event['verify_mode'], 'unknown')
            else:
                # Fallback to raw parsing
                event['raw_data'] = payload.hex()
        
        except Exception as e:
            logger.error(f"Event parse error: {e}")
            event['error'] = str(e)
            event['raw'] = payload.hex()
        
        return event
    
    def create_register_response(self) -> bytes:
        """Create registration acknowledgment"""
        
        # ISUP 5.0 format
        response = b'\x5A\x5A\x5A\x5A'  # Header
        response += struct.pack('<H', 5)  # Version 5
        response += struct.pack('<H', self.RESP_REGISTER)  # Command
        response += struct.pack('<I', 8)  # Length
        response += b'\x00' * 8  # Reserved
        response += struct.pack('<I', 0)  # Status OK
        response += struct.pack('<I', int(datetime.now().timestamp()))  # Server time
        
        return response
    
    def create_heartbeat_response(self) -> bytes:
        """Create heartbeat response"""
        
        response = b'\x5A\x5A\x5A\x5A'
        response += struct.pack('<H', 5)
        response += struct.pack('<H', self.RESP_HEARTBEAT)
        response += struct.pack('<I', 4)
        response += b'\x00' * 8
        response += struct.pack('<I', int(datetime.now().timestamp()))
        
        return response
    
    def create_event_response(self) -> bytes:
        """Create event acknowledgment"""
        
        response = b'\x5A\x5A\x5A\x5A'
        response += struct.pack('<H', 5)
        response += struct.pack('<H', self.RESP_ACCESS_EVENT)
        response += struct.pack('<I', 1)
        response += b'\x00' * 8
        response += b'\x00'  # Success
        
        return response
    
    def create_face_response(self) -> bytes:
        """Create face data acknowledgment"""
        
        response = b'\x5A\x5A\x5A\x5A'
        response += struct.pack('<H', 5)
        response += struct.pack('<H', self.RESP_FACE_DATA)
        response += struct.pack('<I', 1)
        response += b'\x00' * 8
        response += b'\x00'  # Success
        
        return response
    
    def create_error_response(self) -> bytes:
        """Create error response"""
        
        response = b'\x5A\x5A\x5A\x5A'
        response += struct.pack('<H', 5)
        response += struct.pack('<H', 0x8000)  # General error
        response += struct.pack('<I', 1)
        response += b'\x00' * 8
        response += b'\x01'  # Error code
        
        return response
    
    def create_ack_response(self, command: int) -> bytes:
        """Create generic acknowledgment"""
        
        response = b'\x5A\x5A\x5A\x5A'
        response += struct.pack('<H', 5)
        response += struct.pack('<H', command)
        response += struct.pack('<I', 0)
        response += b'\x00' * 8
        
        return response


class ISUPServer:
    """ISUP Server implementation"""
    
    def __init__(self, host='10.100.104.129', port=7660):
        self.host = host
        self.port = port
        self.running = False
        self.handler = ISUPProtocolHandler()
        self.clients = []
        
    def start(self):
        """Start ISUP server"""
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        
        self.running = True
        
        logger.info(f"ISUP Server started on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                logger.info(f"New connection from {address}")
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()
                
                self.clients.append((client_socket, address))
                
            except Exception as e:
                logger.error(f"Server error: {e}")
                if not self.running:
                    break
    
    def handle_client(self, client_socket: socket.socket, address: Tuple):
        """Handle individual client connection"""
        
        logger.info(f"Handling client: {address}")
        
        try:
            while self.running:
                # Receive data
                data = client_socket.recv(4096)
                
                if not data:
                    logger.info(f"Client {address} disconnected")
                    break
                
                logger.debug(f"Received {len(data)} bytes from {address}")
                
                # Parse packet
                command, payload = self.handler.parse_packet(data)
                
                if command > 0:
                    # Process command and get response
                    response = self.handler.process_command(command, payload, address)
                    
                    # Send response
                    if response:
                        client_socket.send(response)
                        logger.debug(f"Sent response: {len(response)} bytes")
                else:
                    # Send generic ACK for unknown packets
                    logger.warning("Unknown packet, sending generic ACK")
                    client_socket.send(b'\x00')
                    
        except socket.timeout:
            logger.debug(f"Client {address} timeout")
        except Exception as e:
            logger.error(f"Client handler error for {address}: {e}")
        finally:
            client_socket.close()
            self.clients = [(s, a) for s, a in self.clients if a != address]
            logger.info(f"Client {address} handler stopped")
    
    def stop(self):
        """Stop server"""
        self.running = False
        self.server_socket.close()
        logger.info("ISUP Server stopped")
    
    def get_events(self):
        """Get collected events"""
        return self.handler.events
    
    def get_devices(self):
        """Get connected devices"""
        return self.handler.connected_devices


if __name__ == "__main__":
    # Test server
    server = ISUPServer()
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop()