# main.py
"""
Hikvision Attendance System - Main Server
ISUP Protocol + FastAPI Backend
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile, Form
from fastapi.responses import JSONResponse, Response
from contextlib import asynccontextmanager
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel
from pathlib import Path
import json
import os

# Import our ISUP handler
from isup_handler import ISUPServer, ISUPProtocolHandler

# Import database functions
from database import (
    get_session, init_database,
    create_employee, get_employee_by_no, get_all_employees, delete_employee,
    create_device, get_device_by_ip, update_device_status, get_all_devices,
    create_attendance_record, get_attendance_by_employee, get_attendance_today,
    get_recent_attendance, check_database_health
)
from utils import (
    validate_employee_no, validate_ip_address,
    format_employee_data, format_attendance_record, format_device_data,
    log_attendance_event, log_device_status, log_error
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global ISUP server instance
isup_server: Optional[ISUPServer] = None

# Pydantic models for API
class Employee(BaseModel):
    employee_no: str
    name: str
    department: Optional[str] = None
    card_no: Optional[str] = None
    face_data: Optional[str] = None  # Base64 encoded

class AttendanceRecord(BaseModel):
    employee_no: str
    timestamp: str
    event_type: str
    verify_method: str
    device_ip: str

class DeviceInfo(BaseModel):
    ip: str
    port: int = 80
    username: str = "admin"
    password: str

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("Server will continue without database")

    global isup_server
    isup_host = os.getenv('ISUP_HOST', '0.0.0.0')
    isup_port = int(os.getenv('ISUP_PORT', '7660'))
    isup_server = ISUPServer(host=isup_host, port=isup_port)

    # Start ISUP server in background thread
    server_thread = threading.Thread(target=isup_server.start, daemon=True)
    server_thread.start()
    logger.info("ISUP Server started in background")

    yield

    # Shutdown
    if isup_server:
        isup_server.stop()
    logger.info("ISUP Server stopped")

# Create FastAPI app
app = FastAPI(
    title="Hikvision Attendance System",
    version="1.0.0",
    lifespan=lifespan
)

# Root endpoint
@app.get("/")
async def root():
    """System status"""
    return {
        "status": "running",
        "isup_server": {
            "host": os.getenv('ISUP_HOST', '0.0.0.0'),
            "port": int(os.getenv('ISUP_PORT', '7660')),
            "protocol": "ISUP 5.0"
        },
        "api_version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

# Device management endpoints
@app.post("/api/devices", summary="Register terminal device")
async def add_device(
    device_id: str = Form(..., description="Device ID/Serial Number"),
    ip_address: str = Form(..., description="Device IP address"),
    username: str = Form("admin", description="Device username"),
    password: str = Form("", description="Device password"),
    model: str = Form(None, description="Device model"),
    location: str = Form(None, description="Device location")
):
    """Register new terminal device"""

    print(f"\n{'='*80}")
    print("📱 REGISTERING NEW TERMINAL")
    print(f"{'='*80}")
    print(f"Device ID: {device_id}")
    print(f"IP Address: {ip_address}")
    print(f"Model: {model or 'N/A'}")
    print(f"Location: {location or 'N/A'}")
    print(f"{'-'*80}")

    try:
        # Validate IP
        if not validate_ip_address(ip_address):
            print(f"❌ FAILED: Invalid IP address")
            raise HTTPException(status_code=400, detail="Invalid IP address format")

        # Test connection
        print(f"\n🔌 Testing connection to {ip_address}...")
        from hikvision_sdk import HikvisionDevice

        device = HikvisionDevice(ip_address, username, password)
        if not device.test_connection():
            print(f"❌ FAILED: Cannot connect to device")
            raise HTTPException(
                status_code=400,
                detail=f"Cannot connect to device at {ip_address}. Check IP, username, password."
            )

        print(f"✅ Connection successful")

        # Save to database
        print(f"\n💾 Saving to database...")
        with get_session() as session:
            # Check if device already exists
            existing = get_device_by_ip(session, ip_address)
            if existing:
                print(f"⚠️  Device already exists, updating...")
                existing.device_id = device_id
                existing.username = username
                existing.password = password
                existing.model = model
                existing.location = location
                existing.status = 'online'
                session.commit()
                session.refresh(existing)
                db_device = existing
            else:
                db_device = create_device(
                    session,
                    device_id=device_id,
                    ip_address=ip_address,
                    username=username,
                    password=password,
                    model=model,
                    location=location,
                    status='online'
                )

        print(f"✅ Device registered with ID: {db_device.id}")
        print(f"{'='*80}")
        print(f"✅ TERMINAL REGISTERED SUCCESSFULLY")
        print(f"{'='*80}\n")

        return {
            "status": "success",
            "device_id": db_device.id,
            "ip_address": ip_address,
            "message": "Terminal registered successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        print(f"{'='*80}\n")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/devices")
async def get_devices():
    """Get all devices from database"""
    try:
        with get_session() as session:
            db_devices = get_all_devices(session)
            devices = [format_device_data(dev) for dev in db_devices]

        return {
            "total": len(devices),
            "devices": devices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/devices/{device_ip}")
async def get_device(device_ip: str):
    """Get specific device info"""
    try:
        with get_session() as session:
            device = get_device_by_ip(session, device_ip)
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")

            return format_device_data(device)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Employee management endpoints
@app.post("/api/employees",
         summary="Add new employee",
         description="Add employee with face image (JPG/PNG). Face image will be saved and synced with terminals.")
async def add_employee(
    employee_no: str = Form(..., description="Employee number (required)"),
    name: str = Form(..., description="Employee name (required)"),
    surname: str = Form(None, description="Employee surname"),
    department: str = Form(None, description="Department"),
    position: str = Form(None, description="Position"),
    card_no: str = Form(None, description="Card number"),
    phone: str = Form(None, description="Phone number"),
    email: str = Form(None, description="Email address"),
    face_image: UploadFile = File(None, description="Face image (JPG/PNG)")
):
    """Add new employee with optional face image"""

    # Console output - START
    print("\n" + "="*80)
    print("🚀 ADDING NEW EMPLOYEE")
    print("="*80)
    print(f"Employee No: {employee_no}")
    print(f"Name: {name} {surname or ''}")
    print(f"Department: {department or 'N/A'}")
    print(f"Position: {position or 'N/A'}")
    print(f"Card: {card_no or 'N/A'}")
    print(f"Face Image: {'Yes' if face_image else 'No'}")
    print("-"*80)

    result = {
        "status": "pending",
        "employee_no": employee_no,
        "steps": []
    }

    try:
        # Step 1: Validate employee number
        print("📝 Step 1: Validating employee number...")
        if not validate_employee_no(employee_no):
            print("❌ FAILED: Invalid employee number format")
            raise HTTPException(status_code=400, detail="Invalid employee number format (must be alphanumeric, 1-50 chars)")
        print("✅ Valid employee number")
        result["steps"].append({"step": "validate_employee_no", "status": "success"})

        # Step 2: Validate face image if provided
        face_image_path = None
        face_image_data = None

        if face_image and face_image.filename:
            print(f"\n📸 Step 2: Processing face image: {face_image.filename}")

            # Check file extension
            file_ext = face_image.filename.split('.')[-1].lower()
            if file_ext not in ['jpg', 'jpeg', 'png']:
                print(f"❌ FAILED: Invalid file type '.{file_ext}'")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type. Only JPG and PNG are allowed. Got: {file_ext}"
                )
            print(f"✅ Valid image format: {file_ext.upper()}")

            # Read image data
            face_image_data = await face_image.read()
            file_size_kb = len(face_image_data) / 1024
            print(f"📊 Image size: {file_size_kb:.2f} KB")

            # Save face image
            try:
                from utils import save_face_image
                face_image_path = save_face_image(face_image_data, employee_no)
                print(f"✅ Face image saved: {face_image_path}")
                result["steps"].append({"step": "save_face_image", "status": "success", "path": face_image_path})
            except Exception as e:
                print(f"⚠️  WARNING: Failed to save image: {e}")
                result["steps"].append({"step": "save_face_image", "status": "warning", "error": str(e)})
        else:
            print("\n⏭️  Step 2: Skipped (no face image provided)")
            result["steps"].append({"step": "face_image", "status": "skipped"})

        # Step 3: Add to database
        print(f"\n💾 Step 3: Saving to database...")
        with get_session() as session:
            # Check if employee already exists
            existing = get_employee_by_no(session, employee_no)
            if existing:
                print(f"❌ FAILED: Employee {employee_no} already exists")
                raise HTTPException(status_code=409, detail=f"Employee {employee_no} already exists")

            # Create employee in database
            from database import create_employee as db_create_employee
            db_employee = db_create_employee(
                session,
                employee_no=employee_no,
                name=name,
                surname=surname or '',
                department=department or '',
                position=position or '',
                card_no=card_no if card_no else None,  # NULL if empty
                phone=phone if phone else None,
                email=email if email else None,
                face_registered=bool(face_image_data)
            )

            print(f"✅ Employee saved to database with ID: {db_employee.id}")
            result["steps"].append({"step": "save_to_database", "status": "success", "db_id": db_employee.id})
            result["employee_id"] = db_employee.id

        # Step 4: Sync with terminals via HTTP API
        print(f"\n📡 Step 4: Syncing with terminals via HTTP API...")

        # Get all devices from database
        terminal_sync_results = []

        with get_session() as session:
            from database import get_all_devices
            db_devices = get_all_devices(session)

            if db_devices:
                print(f"Found {len(db_devices)} terminal(s) in database:")

                from hikvision_sdk import sync_employee_to_device

                for device in db_devices:
                    print(f"\n  📱 Terminal: {device.ip_address} ({device.device_id})")

                    # Prepare employee data
                    employee_data = {
                        'employee_no': employee_no,
                        'name': f"{name} {surname or ''}".strip(),
                        'card_no': card_no
                    }

                    # Sync to device
                    success, message = sync_employee_to_device(
                        device.ip_address,
                        employee_data,
                        face_image_path
                    )

                    terminal_sync_results.append({
                        "terminal": device.ip_address,
                        "device_id": device.device_id,
                        "success": success,
                        "message": message
                    })

                # Summary
                success_count = sum(1 for r in terminal_sync_results if r["success"])
                failed_count = len(terminal_sync_results) - success_count

                print(f"\n📊 Sync Summary:")
                print(f"  ✅ Successful: {success_count}")
                print(f"  ❌ Failed: {failed_count}")

                result["steps"].append({
                    "step": "sync_terminals",
                    "status": "success" if success_count > 0 else "failed",
                    "terminals": len(db_devices),
                    "successful": success_count,
                    "failed": failed_count,
                    "details": terminal_sync_results
                })
            else:
                print("⚠️  WARNING: No terminals in database")
                print("   Add terminals using: POST /api/devices")
                result["steps"].append({
                    "step": "sync_terminals",
                    "status": "warning",
                    "message": "No terminals configured in database"
                })

        # Success
        result["status"] = "success"
        result["message"] = f"Employee {employee_no} added successfully"

        print("\n" + "="*80)
        print("✅ SUCCESS: Employee added successfully!")
        print("="*80 + "\n")

        logger.info(f"✅ Employee added: {employee_no} - {name}")

        return result

    except HTTPException as http_ex:
        result["status"] = "failed"
        result["error"] = http_ex.detail
        print("\n" + "="*80)
        print(f"❌ FAILED: {http_ex.detail}")
        print("="*80 + "\n")
        raise

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print("\n" + "="*80)
        print(f"❌ ERROR: {str(e)}")
        print("="*80 + "\n")
        log_error("add_employee", str(e), {"employee_no": employee_no, "name": name})
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.get("/api/employees")
async def get_employees():
    """Get all employees"""
    try:
        with get_session() as session:
            db_employees = get_all_employees(session, active_only=True)
            employees = [format_employee_data(emp) for emp in db_employees]

        return {
            "total": len(employees),
            "employees": employees
        }

    except Exception as e:
        log_error("get_employees", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/employees/{employee_no}")
async def delete_employee_endpoint(employee_no: str):
    """Delete employee"""
    try:
        # Remove from database (soft delete)
        with get_session() as session:
            success = delete_employee(session, employee_no)
            if not success:
                raise HTTPException(status_code=404, detail="Employee not found")

            logger.info(f"Employee deleted from database: {employee_no}")

        # Remove from terminals (via HTTP API)
        print(f"\n{'='*80}")
        print(f"🗑️  DELETING EMPLOYEE FROM TERMINALS")
        print(f"{'='*80}")

        with get_session() as session:
            from database import get_all_devices
            from hikvision_sdk import delete_employee_from_device

            db_devices = get_all_devices(session)

            if db_devices:
                for device in db_devices:
                    print(f"\n  📱 Terminal: {device.ip_address}")
                    success, message = delete_employee_from_device(device.ip_address, employee_no)
                    print(f"  Result: {message}")

        print(f"{'='*80}\n")

        return {
            "status": "success",
            "employee_no": employee_no,
            "message": "Employee deleted successfully from database and terminals"
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("delete_employee", str(e), {"employee_no": employee_no})
        raise HTTPException(status_code=500, detail=str(e))

# Sync endpoints
@app.post("/api/sync/employee/{employee_no}", summary="Sync single employee to terminals")
async def sync_employee_to_terminals(employee_no: str):
    """Sync existing employee to all terminals"""

    print(f"\n{'='*80}")
    print(f"🔄 SYNCING EMPLOYEE TO TERMINALS")
    print(f"{'='*80}")
    print(f"Employee No: {employee_no}")
    print(f"{'-'*80}")

    try:
        # Get employee from database
        print(f"\n📋 Step 1: Loading employee from database...")
        with get_session() as session:
            employee = get_employee_by_no(session, employee_no)
            if not employee:
                print(f"❌ FAILED: Employee not found")
                raise HTTPException(status_code=404, detail=f"Employee {employee_no} not found")

            print(f"✅ Found: {employee.full_name}")

            # Get face image if exists
            face_image_path = None
            face_images = list(Path("data/faces").glob(f"{employee_no}_*.jpg"))
            if not face_images:
                face_images = list(Path("data/faces").glob(f"{employee_no}_*.png"))

            if face_images:
                face_image_path = str(face_images[0])
                print(f"📸 Face image: {face_image_path}")
            else:
                print(f"⚠️  No face image found")

        # Sync to terminals
        print(f"\n📡 Step 2: Syncing to terminals...")

        terminal_results = []

        with get_session() as session:
            from database import get_all_devices
            from hikvision_sdk import sync_employee_to_device

            db_devices = get_all_devices(session)

            if not db_devices:
                print(f"❌ FAILED: No terminals in database")
                raise HTTPException(status_code=400, detail="No terminals configured. Add terminals first using POST /api/devices")

            print(f"Found {len(db_devices)} terminal(s):")

            for device in db_devices:
                print(f"\n  📱 Terminal: {device.ip_address} ({device.device_id})")

                employee_data = {
                    'employee_no': employee.employee_no,
                    'name': employee.full_name,
                    'card_no': employee.card_no
                }

                success, message = sync_employee_to_device(
                    device.ip_address,
                    employee_data,
                    face_image_path
                )

                terminal_results.append({
                    "terminal": device.ip_address,
                    "device_id": device.device_id,
                    "success": success,
                    "message": message
                })

        # Summary
        success_count = sum(1 for r in terminal_results if r["success"])
        failed_count = len(terminal_results) - success_count

        print(f"\n{'='*80}")
        print(f"📊 SYNC SUMMARY")
        print(f"{'='*80}")
        print(f"Employee: {employee.full_name} ({employee_no})")
        print(f"✅ Successful: {success_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"{'='*80}\n")

        return {
            "status": "success" if success_count > 0 else "failed",
            "employee_no": employee_no,
            "employee_name": employee.full_name,
            "terminals_total": len(db_devices),
            "terminals_successful": success_count,
            "terminals_failed": failed_count,
            "details": terminal_results
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print(f"{'='*80}\n")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/all-employees", summary="Sync all employees to terminals")
async def sync_all_employees_to_terminals():
    """Sync all active employees to all terminals"""

    print(f"\n{'='*80}")
    print(f"🔄 SYNCING ALL EMPLOYEES TO TERMINALS")
    print(f"{'='*80}")

    try:
        # Get all employees
        with get_session() as session:
            employees = get_all_employees(session, active_only=True)
            employee_count = len(employees)

            if employee_count == 0:
                print(f"⚠️  No employees found")
                return {
                    "status": "warning",
                    "message": "No employees to sync",
                    "employees_total": 0
                }

            print(f"Found {employee_count} employee(s)")

            # Get terminals
            db_devices = get_all_devices(session)

            if not db_devices:
                print(f"❌ No terminals configured")
                raise HTTPException(status_code=400, detail="No terminals configured")

            print(f"Found {len(db_devices)} terminal(s)")
            print(f"{'-'*80}")

        # Sync each employee
        from pathlib import Path
        from hikvision_sdk import sync_employee_to_device

        sync_results = []

        for idx, employee in enumerate(employees, 1):
            print(f"\n[{idx}/{employee_count}] Syncing: {employee.full_name} ({employee.employee_no})")

            # Find face image
            face_image_path = None
            face_images = list(Path("data/faces").glob(f"{employee.employee_no}_*.jpg"))
            if not face_images:
                face_images = list(Path("data/faces").glob(f"{employee.employee_no}_*.png"))
            if face_images:
                face_image_path = str(face_images[0])

            employee_data = {
                'employee_no': employee.employee_no,
                'name': employee.full_name,
                'card_no': employee.card_no
            }

            terminal_results = []

            with get_session() as session:
                db_devices = get_all_devices(session)

                for device in db_devices:
                    success, message = sync_employee_to_device(
                        device.ip_address,
                        employee_data,
                        face_image_path
                    )

                    terminal_results.append({
                        "terminal": device.ip_address,
                        "success": success
                    })

            success_count = sum(1 for r in terminal_results if r["success"])

            sync_results.append({
                "employee_no": employee.employee_no,
                "employee_name": employee.full_name,
                "terminals_successful": success_count,
                "terminals_failed": len(terminal_results) - success_count
            })

        # Final summary
        total_success = sum(r["terminals_successful"] for r in sync_results)
        total_failed = sum(r["terminals_failed"] for r in sync_results)

        print(f"\n{'='*80}")
        print(f"📊 FINAL SUMMARY")
        print(f"{'='*80}")
        print(f"Total Employees: {employee_count}")
        print(f"Total Terminals: {len(db_devices)}")
        print(f"✅ Successful Syncs: {total_success}")
        print(f"❌ Failed Syncs: {total_failed}")
        print(f"{'='*80}\n")

        return {
            "status": "success",
            "employees_total": employee_count,
            "terminals_total": len(db_devices),
            "syncs_successful": total_success,
            "syncs_failed": total_failed,
            "details": sync_results
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print(f"{'='*80}\n")
        raise HTTPException(status_code=500, detail=str(e))

# Attendance endpoints
@app.get("/api/attendance/events")
async def get_attendance_events():
    """Get all attendance events"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    events = isup_server.get_events()
    
    return {
        "total": len(events),
        "events": events[-100:]  # Last 100 events
    }

@app.get("/api/attendance/today")
async def get_today_attendance():
    """Get today's attendance"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    today = datetime.now().date().isoformat()
    events = isup_server.get_events()
    
    today_events = [
        e for e in events 
        if e.get('timestamp', '').startswith(today)
    ]
    
    return {
        "date": today,
        "total": len(today_events),
        "events": today_events
    }

@app.get("/api/attendance/employee/{employee_no}")
async def get_employee_attendance(employee_no: str):
    """Get attendance for specific employee"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    events = isup_server.get_events()
    
    employee_events = [
        e for e in events 
        if e.get('employee_no') == employee_no
    ]
    
    return {
        "employee_no": employee_no,
        "total": len(employee_events),
        "events": employee_events
    }

# Statistics endpoint
@app.get("/api/statistics")
async def get_statistics():
    """Get system statistics"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    events = isup_server.get_events()
    devices = isup_server.get_devices()
    
    # Calculate stats
    today = datetime.now().date().isoformat()
    today_events = [e for e in events if e.get('timestamp', '').startswith(today)]
    
    unique_employees = set(e.get('employee_no') for e in events if e.get('employee_no'))
    
    stats = {
        "devices": {
            "total": len(devices),
            "online": len([d for d in devices.values() if d.get('last_seen')])
        },
        "attendance": {
            "total_events": len(events),
            "today_events": len(today_events),
            "unique_employees": len(unique_employees)
        },
        "system": {
            "uptime": datetime.now().isoformat(),
            "isup_port": 7660,
            "api_port": 8000
        }
    }
    
    return stats

# Terminal communication endpoints
@app.post("/api/terminal/sync/{device_ip}")
async def sync_terminal(device_ip: str):
    """Sync data with specific terminal"""
    try:
        # Validate IP address
        if not validate_ip_address(device_ip):
            raise HTTPException(status_code=400, detail="Invalid IP address format")

        # Check if device exists in ISUP server
        if not isup_server:
            raise HTTPException(status_code=503, detail="ISUP server not running")

        devices = isup_server.get_devices()
        if device_ip not in devices:
            raise HTTPException(status_code=404, detail="Device not found")

        # Get all employees to sync
        with get_session() as session:
            employees = get_all_employees(session, active_only=True)
            employee_count = len(employees)

            logger.info(f"Syncing {employee_count} employees with terminal {device_ip}")

            # TODO: Implement actual SDK integration to send employee data
            # For now, we prepare the data and log the action
            for emp in employees:
                logger.debug(f"Preparing sync for {emp.employee_no} to {device_ip}")
                # Future: Send via Hikvision SDK
                # sdk.add_employee(device_ip, emp.employee_no, emp.name, emp.card_no, emp.face_data)

        log_device_status(device_ip, f"Sync completed with {employee_count} employees")

        return {
            "status": "success",
            "device_ip": device_ip,
            "employees_synced": employee_count,
            "message": f"Sync initiated for {employee_count} employees (SDK integration pending)"
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("sync_terminal", str(e), {"device_ip": device_ip})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/terminal/command")
async def send_terminal_command(command: Dict):
    """Send command to terminal"""
    try:
        # Validate required fields
        if 'device_ip' not in command or 'command_type' not in command:
            raise HTTPException(status_code=400, detail="Missing required fields: device_ip, command_type")

        device_ip = command['device_ip']
        command_type = command['command_type']

        # Validate IP
        if not validate_ip_address(device_ip):
            raise HTTPException(status_code=400, detail="Invalid IP address format")

        # Check if device exists
        if not isup_server:
            raise HTTPException(status_code=503, detail="ISUP server not running")

        devices = isup_server.get_devices()
        if device_ip not in devices:
            raise HTTPException(status_code=404, detail="Device not found")

        logger.info(f"Sending command '{command_type}' to terminal {device_ip}")

        # TODO: Implement actual command sending via SDK
        # Supported commands: reboot, get_status, clear_data, update_time, etc.
        # For now, we log the command
        log_device_status(device_ip, f"Command sent: {command_type}")

        return {
            "status": "success",
            "device_ip": device_ip,
            "command": command,
            "message": f"Command '{command_type}' sent successfully (SDK integration pending)"
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("send_terminal_command", str(e), command)
        raise HTTPException(status_code=500, detail=str(e))

# File operations
@app.get("/api/export/attendance")
async def export_attendance():
    """Export attendance data"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    events = isup_server.get_events()
    
    # Create CSV format
    csv_data = "Employee No,Timestamp,Event Type,Verify Method,Device IP\n"
    for event in events:
        csv_data += f"{event.get('employee_no','')},{event.get('timestamp','')},{event.get('event_type','')},{event.get('verify_method','')},{event.get('device_ip','')}\n"
    
    return JSONResponse(
        content={"data": csv_data},
        headers={
            "Content-Disposition": "attachment; filename=attendance_export.csv"
        }
    )

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "isup_server": "running" if isup_server else "stopped"
    }

    # Check database health
    try:
        with get_session() as session:
            db_health = check_database_health(session)
            health_status["database"] = db_health
    except Exception as e:
        health_status["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    return health_status

# Debug endpoints (remove in production)
@app.get("/api/debug/raw-events")
async def get_raw_events():
    """Get raw event data for debugging"""
    try:
        events = []
        if os.path.exists('attendance_events.json'):
            with open('attendance_events.json', 'r') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        
        return {
            "total": len(events),
            "events": events[-50:]  # Last 50
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/debug/clear-events")
async def clear_events():
    """Clear all events (debug only)"""
    if isup_server:
        isup_server.handler.events = []
    
    # Clear files
    for file in ['attendance_events.json', 'employees.json']:
        if os.path.exists(file):
            os.remove(file)
    
    return {"status": "cleared"}

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

if __name__ == "__main__":
    import uvicorn
    
    # Run server
    uvicorn.run(
        app,
        host="10.100.104.129",
        port=8000,
        reload=False,  # Set to True for development
        log_level="info"
    )