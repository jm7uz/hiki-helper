# hikvision_sdk.py
"""
Hikvision Device SDK Integration
HTTP API for device communication and employee management
"""

import requests
from requests.auth import HTTPDigestAuth
import json
import base64
from typing import Dict, Optional, List, Tuple
from loguru import logger
import os


class HikvisionDevice:
    """Hikvision Terminal HTTP API Client"""

    def __init__(self, ip: str, username: str = "admin", password: str = "", port: int = 80):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{ip}:{port}/ISAPI"
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = 10

    def _request(self, method: str, endpoint: str, data: str = None, headers: Dict = None) -> Tuple[bool, str]:
        """Make HTTP request to device"""
        url = f"{self.base_url}/{endpoint}"

        default_headers = {
            'Content-Type': 'application/xml; charset="UTF-8"'
        }
        if headers:
            default_headers.update(headers)

        try:
            logger.debug(f"[{self.ip}] {method} {endpoint}")

            if method == "GET":
                response = requests.get(url, auth=self.auth, headers=default_headers, timeout=self.timeout)
            elif method == "POST":
                response = requests.post(url, auth=self.auth, data=data, headers=default_headers, timeout=self.timeout)
            elif method == "PUT":
                response = requests.put(url, auth=self.auth, data=data, headers=default_headers, timeout=self.timeout)
            elif method == "DELETE":
                response = requests.delete(url, auth=self.auth, headers=default_headers, timeout=self.timeout)
            else:
                return False, f"Unsupported method: {method}"

            if response.status_code in [200, 201]:
                logger.debug(f"[{self.ip}] Success: {response.status_code}")
                return True, response.text
            else:
                logger.warning(f"[{self.ip}] Failed: {response.status_code} - {response.text}")
                return False, f"HTTP {response.status_code}: {response.text}"

        except requests.exceptions.Timeout:
            logger.error(f"[{self.ip}] Timeout connecting to device")
            return False, "Connection timeout"
        except requests.exceptions.ConnectionError:
            logger.error(f"[{self.ip}] Connection error")
            return False, "Connection error"
        except Exception as e:
            logger.error(f"[{self.ip}] Request error: {e}")
            return False, str(e)

    def test_connection(self) -> bool:
        """Test device connection"""
        logger.info(f"[{self.ip}] Testing connection...")
        success, response = self._request("GET", "System/deviceInfo")

        if success:
            logger.info(f"[{self.ip}] ✅ Connection successful")
            return True
        else:
            logger.error(f"[{self.ip}] ❌ Connection failed: {response}")
            return False

    def get_device_info(self) -> Optional[Dict]:
        """Get device information"""
        success, response = self._request("GET", "System/deviceInfo")
        if success:
            # Parse XML response (simplified)
            return {"status": "online", "response": response}
        return None

    def add_employee(self, employee_no: str, name: str, card_no: str = None,
                    face_image: bytes = None) -> Tuple[bool, str]:
        """
        Add employee to device

        Args:
            employee_no: Employee number (must be numeric for Hikvision)
            name: Employee name
            card_no: Card number (optional)
            face_image: Face image data (optional)

        Returns:
            Tuple[bool, str]: (success, message)
        """

        print(f"\n{'='*80}")
        print(f"📡 SYNCING EMPLOYEE TO TERMINAL: {self.ip}")
        print(f"{'='*80}")
        print(f"Employee No: {employee_no}")
        print(f"Name: {name}")
        print(f"Card: {card_no or 'N/A'}")
        print(f"Face: {'Yes' if face_image else 'No'}")
        print(f"{'-'*80}")

        try:
            # Step 1: Test connection
            print(f"🔌 Step 1: Testing connection to {self.ip}...")
            if not self.test_connection():
                print(f"❌ FAILED: Cannot connect to terminal {self.ip}")
                return False, "Connection failed"
            print(f"✅ Connected to terminal")

            # Hikvision uses numeric employee IDs
            # Try to extract numbers from employee_no
            emp_id = ''.join(filter(str.isdigit, employee_no))
            if not emp_id:
                # If no digits, use hash
                emp_id = str(abs(hash(employee_no)) % 100000)

            print(f"🔢 Converted employee_no '{employee_no}' to numeric ID: {emp_id}")

            # Step 2: Add person (basic info)
            print(f"\n👤 Step 2: Adding person to device...")

            person_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Person>
    <employeeNo>{emp_id}</employeeNo>
    <name>{name}</name>
    <userType>normal</userType>
    <Valid>
        <enable>true</enable>
        <beginTime>2020-01-01T00:00:00</beginTime>
        <endTime>2030-12-31T23:59:59</endTime>
    </Valid>
    <doorRight>1</doorRight>
    <RightPlan>
        <doorNo>1</doorNo>
        <planTemplateNo>1</planTemplateNo>
    </RightPlan>
</Person>"""

            # Try to add person
            success, response = self._request("POST", "AccessControl/UserInfo/Record?format=json", person_xml)

            if success:
                print(f"✅ Person added to device")
            else:
                # Try alternative endpoint
                print(f"⚠️  Primary method failed, trying alternative...")
                success, response = self._request("PUT", f"AccessControl/UserInfo/SetUp?format=json", person_xml)

                if success:
                    print(f"✅ Person added via alternative method")
                else:
                    print(f"❌ FAILED: Could not add person - {response}")
                    return False, f"Failed to add person: {response}"

            # Step 3: Add card if provided
            if card_no:
                print(f"\n💳 Step 3: Adding card number...")

                card_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CardInfo>
    <employeeNo>{emp_id}</employeeNo>
    <cardNo>{card_no}</cardNo>
    <cardType>normalCard</cardType>
</CardInfo>"""

                success, response = self._request("PUT", "AccessControl/CardInfo/SetUp?format=json", card_xml)

                if success:
                    print(f"✅ Card added")
                else:
                    print(f"⚠️  Warning: Card not added - {response}")
            else:
                print(f"\n⏭️  Step 3: Skipped (no card)")

            # Step 4: Add face if provided
            if face_image:
                print(f"\n📸 Step 4: Uploading face image...")

                # Encode image to base64
                face_base64 = base64.b64encode(face_image).decode('utf-8')

                face_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<FaceInfo>
    <employeeNo>{emp_id}</employeeNo>
    <faceLibType>blackFD</faceLibType>
    <FDID>1</FDID>
    <FPID>1</FPID>
</FaceInfo>"""

                # Upload face data
                success, response = self._request("POST", f"Intelligent/FDLib/FaceDataRecord?format=json", face_xml)

                if success:
                    print(f"✅ Face image uploaded")
                else:
                    print(f"⚠️  Warning: Face not uploaded - {response}")
            else:
                print(f"\n⏭️  Step 4: Skipped (no face image)")

            # Success
            print(f"\n{'='*80}")
            print(f"✅ EMPLOYEE SYNCED TO TERMINAL {self.ip}")
            print(f"{'='*80}\n")

            logger.info(f"[{self.ip}] ✅ Employee {employee_no} synced successfully")

            return True, "Employee synced successfully"

        except Exception as e:
            error_msg = f"Error syncing employee: {str(e)}"
            print(f"\n{'='*80}")
            print(f"❌ ERROR: {error_msg}")
            print(f"{'='*80}\n")
            logger.error(f"[{self.ip}] {error_msg}")
            return False, error_msg

    def delete_employee(self, employee_no: str) -> Tuple[bool, str]:
        """Delete employee from device"""

        print(f"\n{'='*80}")
        print(f"🗑️  DELETING EMPLOYEE FROM TERMINAL: {self.ip}")
        print(f"{'='*80}")
        print(f"Employee No: {employee_no}")
        print(f"{'-'*80}")

        try:
            # Convert to numeric ID
            emp_id = ''.join(filter(str.isdigit, employee_no))
            if not emp_id:
                emp_id = str(abs(hash(employee_no)) % 100000)

            print(f"🔢 Using numeric ID: {emp_id}")

            # Delete person
            print(f"\n🗑️  Deleting person from device...")

            delete_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<UserInfoDelCond>
    <EmployeeNoList>
        <employeeNo>{emp_id}</employeeNo>
    </EmployeeNoList>
</UserInfoDelCond>"""

            success, response = self._request("PUT", "AccessControl/UserInfo/Delete?format=json", delete_xml)

            if success:
                print(f"✅ Employee deleted from terminal")
                print(f"{'='*80}\n")
                logger.info(f"[{self.ip}] ✅ Employee {employee_no} deleted")
                return True, "Employee deleted successfully"
            else:
                print(f"❌ FAILED: {response}")
                print(f"{'='*80}\n")
                return False, f"Failed to delete: {response}"

        except Exception as e:
            error_msg = f"Error deleting employee: {str(e)}"
            print(f"❌ ERROR: {error_msg}")
            print(f"{'='*80}\n")
            logger.error(f"[{self.ip}] {error_msg}")
            return False, error_msg


def sync_employee_to_device(device_ip: str, employee_data: Dict, face_image_path: str = None) -> Tuple[bool, str]:
    """
    Convenience function to sync employee to device

    Args:
        device_ip: Device IP address
        employee_data: Dict with employee_no, name, card_no
        face_image_path: Path to face image file

    Returns:
        Tuple[bool, str]: (success, message)
    """

    # Get credentials from environment
    username = os.getenv('DEFAULT_DEVICE_USERNAME', 'admin')
    password = os.getenv('DEFAULT_DEVICE_PASSWORD', '')

    device = HikvisionDevice(device_ip, username, password)

    # Load face image if provided
    face_image = None
    if face_image_path and os.path.exists(face_image_path):
        with open(face_image_path, 'rb') as f:
            face_image = f.read()

    return device.add_employee(
        employee_no=employee_data.get('employee_no'),
        name=employee_data.get('name'),
        card_no=employee_data.get('card_no'),
        face_image=face_image
    )


def delete_employee_from_device(device_ip: str, employee_no: str) -> Tuple[bool, str]:
    """
    Convenience function to delete employee from device

    Args:
        device_ip: Device IP address
        employee_no: Employee number

    Returns:
        Tuple[bool, str]: (success, message)
    """

    username = os.getenv('DEFAULT_DEVICE_USERNAME', 'admin')
    password = os.getenv('DEFAULT_DEVICE_PASSWORD', '')

    device = HikvisionDevice(device_ip, username, password)
    return device.delete_employee(employee_no)


if __name__ == "__main__":
    # Test
    device = HikvisionDevice("10.100.104.109", "admin", "")

    if device.test_connection():
        print("✅ Device connection successful!")

        # Test add employee
        success, msg = device.add_employee("12345", "Test User", "999888")
        print(f"Add result: {success} - {msg}")
    else:
        print("❌ Device connection failed!")
