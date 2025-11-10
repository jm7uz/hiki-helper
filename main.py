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
        # TODO: Add to database
        # TODO: Sync with terminals
        
        # Temporary: save to file
        with open('employees.json', 'a') as f:
            json.dump(employee.dict(), f)
            f.write('\n')
        
        logger.info(f"Employee added: {employee.employee_no} - {employee.name}")
        
        return {
            "status": "success",
            "employee_no": employee.employee_no,
            "message": "Employee added successfully"
        }
    
    except Exception as e:
        logger.error(f"Add employee error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/employees")
async def get_employees():
    """Get all employees"""
    try:
        employees = []
        if os.path.exists('employees.json'):
            with open('employees.json', 'r') as f:
                for line in f:
                    if line.strip():
                        employees.append(json.loads(line))
        
        return {
            "total": len(employees),
            "employees": employees
        }
    
    except Exception as e:
        logger.error(f"Get employees error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/employees/{employee_no}")
async def delete_employee(employee_no: str):
    """Delete employee"""
    # TODO: Remove from database
    # TODO: Remove from terminals
    
    return {
        "status": "success",
        "employee_no": employee_no,
        "message": "Employee deleted"
    }

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
    # TODO: Implement terminal sync via SDK
    
    return {
        "status": "success",
        "device_ip": device_ip,
        "message": "Sync initiated"
    }

@app.post("/api/terminal/command")
async def send_terminal_command(command: Dict):
    """Send command to terminal"""
    # TODO: Implement command sending
    
    return {
        "status": "success",
        "command": command,
        "message": "Command sent"
    }

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
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

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