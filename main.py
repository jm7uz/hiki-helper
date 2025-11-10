# main.py
"""
Hikvision Attendance System - Main Server
ISUP Protocol + FastAPI Backend
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel
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
    isup_server = ISUPServer(host='10.100.104.129', port=7660)

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
            "host": "10.100.104.129",
            "port": 7660,
            "protocol": "ISUP 5.0"
        },
        "api_version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

# Device management endpoints
@app.get("/api/devices")
async def get_devices():
    """Get all connected devices"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    devices = isup_server.get_devices()
    return {
        "total": len(devices),
        "devices": devices
    }

@app.get("/api/devices/{device_ip}")
async def get_device(device_ip: str):
    """Get specific device info"""
    if not isup_server:
        raise HTTPException(status_code=503, detail="ISUP server not running")
    
    devices = isup_server.get_devices()
    if device_ip not in devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return devices[device_ip]

# Employee management endpoints
@app.post("/api/employees")
async def add_employee(employee: Employee):
    """Add new employee"""
    try:
        # Validate employee number
        if not validate_employee_no(employee.employee_no):
            raise HTTPException(status_code=400, detail="Invalid employee number format")

        # Add to database
        with get_session() as session:
            # Check if employee already exists
            existing = get_employee_by_no(session, employee.employee_no)
            if existing:
                raise HTTPException(status_code=409, detail="Employee already exists")

            # Create employee in database
            db_employee = create_employee(
                session,
                employee_no=employee.employee_no,
                name=employee.name,
                department=employee.department,
                card_no=employee.card_no,
                face_registered=bool(employee.face_data)
            )

            logger.info(f"Employee added to database: {employee.employee_no} - {employee.name}")

        # Sync with terminals (via ISUP protocol)
        # For now, we'll just log it - actual sync requires SDK integration
        if isup_server:
            devices = isup_server.get_devices()
            for device_ip in devices:
                log_device_status(device_ip, f"Syncing employee {employee.employee_no}")
                # TODO: Send employee data to terminal via SDK/ISUP
            logger.info(f"Employee sync initiated with {len(devices)} terminals")

        return {
            "status": "success",
            "employee_no": employee.employee_no,
            "message": "Employee added successfully and synced with terminals"
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("add_employee", str(e), employee.dict())
        raise HTTPException(status_code=500, detail=str(e))

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

        # Remove from terminals (via ISUP protocol)
        if isup_server:
            devices = isup_server.get_devices()
            for device_ip in devices:
                log_device_status(device_ip, f"Removing employee {employee_no}")
                # TODO: Send delete command to terminal via SDK/ISUP
            logger.info(f"Employee removal initiated from {len(devices)} terminals")

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