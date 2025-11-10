# utils.py
"""
Utility Functions
Helper functions for data processing, validation, and formatting
"""

from datetime import datetime, date, time, timedelta
from typing import Dict, Any, Optional, List
import hashlib
import base64
import json
import os
from loguru import logger

# ========================
# Date & Time Utilities
# ========================

def parse_isup_time(time_bytes: bytes) -> datetime:
    """Parse ISUP protocol time format (BCD encoded)"""
    try:
        year = 2000 + int.from_bytes(time_bytes[0:1], 'big')
        month = int.from_bytes(time_bytes[1:2], 'big')
        day = int.from_bytes(time_bytes[2:3], 'big')
        hour = int.from_bytes(time_bytes[3:4], 'big')
        minute = int.from_bytes(time_bytes[4:5], 'big')
        second = int.from_bytes(time_bytes[5:6], 'big')

        return datetime(year, month, day, hour, minute, second)
    except Exception as e:
        logger.error(f"Error parsing ISUP time: {e}")
        return datetime.now()

def format_time_hhmm(dt: datetime) -> str:
    """Format datetime to HH:MM"""
    return dt.strftime("%H:%M")

def format_date(dt: datetime) -> str:
    """Format datetime to YYYY-MM-DD"""
    return dt.strftime("%Y-%m-%d")

def get_date_range(days: int = 7) -> tuple:
    """Get date range from today back N days"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date

def is_working_day(dt: datetime, weekend_days: str = "6,7") -> bool:
    """Check if date is a working day (not weekend)"""
    weekday = dt.isoweekday()  # Monday=1, Sunday=7
    weekend = [int(d) for d in weekend_days.split(',')]
    return weekday not in weekend

def calculate_work_hours(check_in: datetime, check_out: datetime) -> float:
    """Calculate total work hours between check-in and check-out"""
    if check_out < check_in:
        return 0.0
    delta = check_out - check_in
    return round(delta.total_seconds() / 3600, 2)

def calculate_late_minutes(check_in: datetime, expected_time: str) -> int:
    """Calculate late minutes based on expected start time (HH:MM format)"""
    try:
        expected_hour, expected_minute = map(int, expected_time.split(':'))
        expected_dt = check_in.replace(hour=expected_hour, minute=expected_minute, second=0, microsecond=0)

        if check_in > expected_dt:
            delta = check_in - expected_dt
            return int(delta.total_seconds() / 60)
        return 0
    except Exception:
        return 0

# ========================
# Data Validation
# ========================

def validate_employee_no(employee_no: str) -> bool:
    """Validate employee number format"""
    if not employee_no:
        return False
    # Must be alphanumeric and between 1-50 characters
    return employee_no.isalnum() and 1 <= len(employee_no) <= 50

def validate_ip_address(ip: str) -> bool:
    """Validate IP address format"""
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
    except:
        return False

def validate_phone(phone: str) -> bool:
    """Validate phone number (simple validation)"""
    if not phone:
        return True  # Optional field
    # Remove common separators
    clean = phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
    return clean.isdigit() and 7 <= len(clean) <= 15

def validate_email(email: str) -> bool:
    """Validate email address (simple validation)"""
    if not email:
        return True  # Optional field
    return '@' in email and '.' in email.split('@')[1]

# ========================
# Data Formatting
# ========================

def format_employee_data(employee) -> Dict[str, Any]:
    """Format employee object to dictionary"""
    return {
        'id': employee.id,
        'employee_no': employee.employee_no,
        'name': employee.name,
        'surname': employee.surname,
        'full_name': employee.full_name,
        'department': employee.department,
        'position': employee.position,
        'branch_id': employee.branch_id,
        'phone': employee.phone,
        'email': employee.email,
        'card_no': employee.card_no,
        'face_registered': employee.face_registered,
        'is_active': employee.is_active,
        'created_at': employee.created_at.isoformat() if employee.created_at else None
    }

def format_attendance_record(record) -> Dict[str, Any]:
    """Format attendance record to dictionary"""
    return {
        'id': record.id,
        'employee_no': record.employee_no,
        'device_id': record.device_id,
        'check_time': record.check_time.isoformat() if record.check_time else None,
        'check_type': record.check_type,
        'verify_mode': record.verify_mode,
        'temperature': record.temperature,
        'event_type': record.event_type
    }

def format_device_data(device) -> Dict[str, Any]:
    """Format device object to dictionary"""
    return {
        'id': device.id,
        'device_id': device.device_id,
        'serial_number': device.serial_number,
        'model': device.model,
        'ip_address': device.ip_address,
        'branch_id': device.branch_id,
        'location': device.location,
        'status': device.status,
        'last_seen': device.last_seen.isoformat() if device.last_seen else None,
        'firmware_version': device.firmware_version
    }

# ========================
# Password & Security
# ========================

def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == password_hash

def generate_pin_code(length: int = 4) -> str:
    """Generate random PIN code"""
    import random
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

# ========================
# Image & Face Data
# ========================

def encode_face_image(image_bytes: bytes) -> str:
    """Encode face image to base64"""
    return base64.b64encode(image_bytes).decode('utf-8')

def decode_face_image(base64_str: str) -> bytes:
    """Decode base64 face image"""
    return base64.b64decode(base64_str)

def save_face_image(image_bytes: bytes, employee_no: str, face_path: str = "data/faces") -> str:
    """Save face image to file"""
    os.makedirs(face_path, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{employee_no}_{timestamp}.jpg"
    filepath = os.path.join(face_path, filename)

    with open(filepath, 'wb') as f:
        f.write(image_bytes)

    return filepath

# ========================
# ISUP Protocol Utilities
# ========================

def parse_isup_packet(data: bytes) -> Dict[str, Any]:
    """Parse ISUP protocol packet"""
    if len(data) < 8:
        return None

    try:
        # ISUP packet structure
        header = data[0:4]  # 4 bytes header (STX, LEN)
        command = int.from_bytes(data[4:6], 'big')  # 2 bytes command
        length = int.from_bytes(data[6:8], 'big')   # 2 bytes length
        payload = data[8:-2]  # Payload (excluding ETX and checksum)

        return {
            'command': command,
            'length': length,
            'payload': payload,
            'raw': data
        }
    except Exception as e:
        logger.error(f"Error parsing ISUP packet: {e}")
        return None

def create_isup_response(command: int, payload: bytes = b'') -> bytes:
    """Create ISUP protocol response packet"""
    stx = b'\x40\x40'  # Start of text
    cmd_bytes = command.to_bytes(2, 'big')
    length = len(payload)
    len_bytes = length.to_bytes(2, 'big')
    etx = b'\x23\x23'  # End of text

    # Calculate checksum (simple XOR)
    packet = stx + cmd_bytes + len_bytes + payload + etx
    checksum = 0
    for byte in packet:
        checksum ^= byte

    return packet + checksum.to_bytes(1, 'big')

def get_verify_mode_name(mode: int) -> str:
    """Get verification mode name from code"""
    modes = {
        0: 'password',
        1: 'card',
        2: 'fingerprint',
        3: 'face',
        4: 'face+card',
        5: 'face+password',
        6: 'card+password',
        7: 'card+fingerprint',
        15: 'unknown'
    }
    return modes.get(mode, 'unknown')

def get_event_type_name(event_type: int) -> str:
    """Get event type name from code"""
    events = {
        0: 'check_in',
        1: 'check_out',
        2: 'break_start',
        3: 'break_end',
        4: 'overtime_in',
        5: 'overtime_out'
    }
    return events.get(event_type, 'check_in')

# ========================
# JSON & File Operations
# ========================

def save_to_ndjson(data: Dict[str, Any], filename: str):
    """Append data to NDJSON file (newline-delimited JSON)"""
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')

def read_ndjson(filename: str) -> List[Dict[str, Any]]:
    """Read NDJSON file"""
    if not os.path.exists(filename):
        return []

    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data.append(json.loads(line.strip()))
            except:
                continue
    return data

def ensure_dir(directory: str):
    """Ensure directory exists"""
    os.makedirs(directory, exist_ok=True)

# ========================
# Statistics Helpers
# ========================

def calculate_attendance_stats(records: List) -> Dict[str, Any]:
    """Calculate attendance statistics from records"""
    if not records:
        return {
            'total': 0,
            'by_verify_mode': {},
            'by_hour': {}
        }

    by_verify_mode = {}
    by_hour = {}

    for record in records:
        # Count by verification mode
        mode = record.verify_mode if hasattr(record, 'verify_mode') else 'unknown'
        by_verify_mode[mode] = by_verify_mode.get(mode, 0) + 1

        # Count by hour
        if hasattr(record, 'check_time') and record.check_time:
            hour = record.check_time.hour
            by_hour[hour] = by_hour.get(hour, 0) + 1

    return {
        'total': len(records),
        'by_verify_mode': by_verify_mode,
        'by_hour': by_hour
    }

def calculate_late_percentage(employees_count: int, late_count: int) -> float:
    """Calculate late percentage"""
    if employees_count == 0:
        return 0.0
    return round((late_count / employees_count) * 100, 2)

# ========================
# CSV Export Helpers
# ========================

def create_csv_row(data: Dict[str, Any], headers: List[str]) -> str:
    """Create CSV row from dictionary"""
    values = [str(data.get(h, '')) for h in headers]
    # Escape commas and quotes
    values = [f'"{v}"' if ',' in v or '"' in v else v for v in values]
    return ','.join(values)

def export_to_csv(records: List[Dict[str, Any]], headers: List[str], filename: str):
    """Export records to CSV file"""
    with open(filename, 'w', encoding='utf-8') as f:
        # Write header
        f.write(','.join(headers) + '\n')

        # Write rows
        for record in records:
            row = create_csv_row(record, headers)
            f.write(row + '\n')

# ========================
# Logging Helpers
# ========================

def log_attendance_event(employee_no: str, device_ip: str, event_type: str):
    """Log attendance event"""
    logger.info(f"Attendance: {employee_no} - {event_type} at {device_ip}")

def log_device_status(device_id: str, status: str):
    """Log device status change"""
    logger.info(f"Device {device_id}: {status}")

def log_error(module: str, message: str, details: Any = None):
    """Log error with details"""
    logger.error(f"[{module}] {message}")
    if details:
        logger.error(f"Details: {details}")

# ========================
# Testing & Debug
# ========================

def generate_test_employee() -> Dict[str, Any]:
    """Generate test employee data"""
    import random
    emp_no = f"EMP{random.randint(1000, 9999)}"
    return {
        'employee_no': emp_no,
        'name': f"Test User {random.randint(1, 100)}",
        'surname': 'Testov',
        'department': 'IT',
        'position': 'Developer',
        'card_no': f"{random.randint(100000, 999999)}",
        'phone': f"+998901234567"
    }

if __name__ == "__main__":
    # Test utilities
    print("Testing utilities...")

    # Test date parsing
    now = datetime.now()
    print(f"Current time: {format_time_hhmm(now)}")
    print(f"Current date: {format_date(now)}")

    # Test validation
    print(f"Valid employee no: {validate_employee_no('EMP001')}")
    print(f"Valid IP: {validate_ip_address('192.168.1.1')}")

    # Test password hashing
    password = "test123"
    hashed = hash_password(password)
    print(f"Password verified: {verify_password(password, hashed)}")

    print(" Utilities test completed")
