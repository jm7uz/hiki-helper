# database.py
"""
Database Helper Functions
Provides database connection, session management, and common CRUD operations
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
import os
from contextlib import contextmanager

from models import (
    Database, Base,
    Branch, Device, Employee, FaceData,
    AttendanceRecord, WorkSchedule, AttendanceSummary,
    SystemLog, User
)

# Global database instance
_db_instance = None

def get_database():
    """Get or create database instance"""
    global _db_instance
    if _db_instance is None:
        database_url = os.getenv(
            'DATABASE_URL',
            'postgresql://attendance_user:attendance_pass@localhost:5432/attendance_db'
        )
        _db_instance = Database(database_url)
    return _db_instance

def init_database():
    """Initialize database tables and sample data"""
    db = get_database()
    db.create_tables()
    db.init_data()
    return db

@contextmanager
def get_session():
    """Context manager for database sessions"""
    db = get_database()
    session = db.get_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# ========================
# Branch Operations
# ========================

def create_branch(session: Session, name: str, code: str, **kwargs) -> Branch:
    """Create new branch"""
    branch = Branch(name=name, code=code, **kwargs)
    session.add(branch)
    session.commit()
    session.refresh(branch)
    return branch

def get_branch_by_code(session: Session, code: str) -> Optional[Branch]:
    """Get branch by code"""
    return session.query(Branch).filter(Branch.code == code).first()

def get_all_branches(session: Session) -> List[Branch]:
    """Get all branches"""
    return session.query(Branch).all()

# ========================
# Device Operations
# ========================

def create_device(session: Session, device_id: str, ip_address: str, **kwargs) -> Device:
    """Create new device"""
    device = Device(device_id=device_id, ip_address=ip_address, **kwargs)
    session.add(device)
    session.commit()
    session.refresh(device)
    return device

def get_device_by_ip(session: Session, ip_address: str) -> Optional[Device]:
    """Get device by IP address"""
    return session.query(Device).filter(Device.ip_address == ip_address).first()

def get_device_by_device_id(session: Session, device_id: str) -> Optional[Device]:
    """Get device by device ID"""
    return session.query(Device).filter(Device.device_id == device_id).first()

def update_device_status(session: Session, device_id: str, status: str) -> Optional[Device]:
    """Update device status and last seen time"""
    device = get_device_by_device_id(session, device_id)
    if device:
        device.status = status
        device.last_seen = datetime.now()
        session.commit()
        session.refresh(device)
    return device

def get_all_devices(session: Session, branch_id: Optional[int] = None) -> List[Device]:
    """Get all devices, optionally filtered by branch"""
    query = session.query(Device)
    if branch_id:
        query = query.filter(Device.branch_id == branch_id)
    return query.all()

# ========================
# Employee Operations
# ========================

def create_employee(session: Session, employee_no: str, name: str, **kwargs) -> Employee:
    """Create new employee"""
    employee = Employee(employee_no=employee_no, name=name, **kwargs)
    # Set full_name if not provided
    if not employee.full_name:
        employee.full_name = f"{name} {kwargs.get('surname', '')}".strip()
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee

def get_employee_by_no(session: Session, employee_no: str) -> Optional[Employee]:
    """Get employee by employee number"""
    return session.query(Employee).filter(Employee.employee_no == employee_no).first()

def get_employee_by_card(session: Session, card_no: str) -> Optional[Employee]:
    """Get employee by card number"""
    return session.query(Employee).filter(Employee.card_no == card_no).first()

def update_employee(session: Session, employee_no: str, **kwargs) -> Optional[Employee]:
    """Update employee information"""
    employee = get_employee_by_no(session, employee_no)
    if employee:
        for key, value in kwargs.items():
            if hasattr(employee, key):
                setattr(employee, key, value)
        session.commit()
        session.refresh(employee)
    return employee

def delete_employee(session: Session, employee_no: str) -> bool:
    """Delete employee (soft delete by setting is_active=False)"""
    employee = get_employee_by_no(session, employee_no)
    if employee:
        employee.is_active = False
        employee.termination_date = datetime.now()
        session.commit()
        return True
    return False

def get_all_employees(session: Session, branch_id: Optional[int] = None, active_only: bool = True) -> List[Employee]:
    """Get all employees, optionally filtered by branch and active status"""
    query = session.query(Employee)
    if branch_id:
        query = query.filter(Employee.branch_id == branch_id)
    if active_only:
        query = query.filter(Employee.is_active == True)
    return query.all()

# ========================
# Face Data Operations
# ========================

def create_face_data(session: Session, employee_id: int, face_template: str, **kwargs) -> FaceData:
    """Create face data for employee"""
    face_data = FaceData(employee_id=employee_id, face_template=face_template, **kwargs)
    session.add(face_data)
    session.commit()
    session.refresh(face_data)
    return face_data

def get_employee_face_data(session: Session, employee_id: int) -> List[FaceData]:
    """Get all face data for employee"""
    return session.query(FaceData).filter(FaceData.employee_id == employee_id).all()

# ========================
# Attendance Operations
# ========================

def create_attendance_record(session: Session, employee_id: int, employee_no: str,
                            device_id: int, check_time: datetime, **kwargs) -> AttendanceRecord:
    """Create attendance record"""
    record = AttendanceRecord(
        employee_id=employee_id,
        employee_no=employee_no,
        device_id=device_id,
        check_time=check_time,
        **kwargs
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record

def get_attendance_by_employee(session: Session, employee_no: str,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> List[AttendanceRecord]:
    """Get attendance records for employee"""
    query = session.query(AttendanceRecord).filter(AttendanceRecord.employee_no == employee_no)

    if start_date:
        query = query.filter(AttendanceRecord.check_time >= start_date)
    if end_date:
        query = query.filter(AttendanceRecord.check_time <= end_date)

    return query.order_by(desc(AttendanceRecord.check_time)).all()

def get_attendance_today(session: Session, branch_id: Optional[int] = None) -> List[AttendanceRecord]:
    """Get today's attendance records"""
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())

    query = session.query(AttendanceRecord).filter(
        and_(
            AttendanceRecord.check_time >= today_start,
            AttendanceRecord.check_time <= today_end
        )
    )

    if branch_id:
        query = query.join(Device).filter(Device.branch_id == branch_id)

    return query.order_by(desc(AttendanceRecord.check_time)).all()

def get_recent_attendance(session: Session, limit: int = 100) -> List[AttendanceRecord]:
    """Get recent attendance records"""
    return session.query(AttendanceRecord)\
        .order_by(desc(AttendanceRecord.check_time))\
        .limit(limit)\
        .all()

# ========================
# Work Schedule Operations
# ========================

def create_work_schedule(session: Session, name: str, code: str, **kwargs) -> WorkSchedule:
    """Create work schedule"""
    schedule = WorkSchedule(name=name, code=code, **kwargs)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule

def get_work_schedule_by_code(session: Session, code: str) -> Optional[WorkSchedule]:
    """Get work schedule by code"""
    return session.query(WorkSchedule).filter(WorkSchedule.code == code).first()

def get_all_work_schedules(session: Session) -> List[WorkSchedule]:
    """Get all work schedules"""
    return session.query(WorkSchedule).all()

# ========================
# Attendance Summary Operations
# ========================

def create_or_update_attendance_summary(session: Session, employee_id: int,
                                       date: datetime, **kwargs) -> AttendanceSummary:
    """Create or update attendance summary for employee on specific date"""
    summary = session.query(AttendanceSummary).filter(
        and_(
            AttendanceSummary.employee_id == employee_id,
            func.date(AttendanceSummary.date) == date.date()
        )
    ).first()

    if summary:
        # Update existing summary
        for key, value in kwargs.items():
            if hasattr(summary, key):
                setattr(summary, key, value)
    else:
        # Create new summary
        summary = AttendanceSummary(employee_id=employee_id, date=date, **kwargs)
        session.add(summary)

    session.commit()
    session.refresh(summary)
    return summary

def get_attendance_summary(session: Session, employee_id: int,
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None) -> List[AttendanceSummary]:
    """Get attendance summary for employee"""
    query = session.query(AttendanceSummary).filter(AttendanceSummary.employee_id == employee_id)

    if start_date:
        query = query.filter(func.date(AttendanceSummary.date) >= start_date.date())
    if end_date:
        query = query.filter(func.date(AttendanceSummary.date) <= end_date.date())

    return query.order_by(desc(AttendanceSummary.date)).all()

# ========================
# System Log Operations
# ========================

def create_system_log(session: Session, level: str, module: str, message: str, **kwargs) -> SystemLog:
    """Create system log entry"""
    log = SystemLog(level=level, module=module, message=message, **kwargs)
    session.add(log)
    session.commit()
    return log

def get_recent_logs(session: Session, level: Optional[str] = None, limit: int = 100) -> List[SystemLog]:
    """Get recent system logs"""
    query = session.query(SystemLog)
    if level:
        query = query.filter(SystemLog.level == level)
    return query.order_by(desc(SystemLog.created_at)).limit(limit).all()

# ========================
# User Operations (Admin Panel)
# ========================

def create_user(session: Session, username: str, email: str, password_hash: str, **kwargs) -> User:
    """Create admin user"""
    user = User(username=username, email=email, password_hash=password_hash, **kwargs)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

def get_user_by_username(session: Session, username: str) -> Optional[User]:
    """Get user by username"""
    return session.query(User).filter(User.username == username).first()

def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """Get user by email"""
    return session.query(User).filter(User.email == email).first()

# ========================
# Statistics & Reporting
# ========================

def get_attendance_statistics(session: Session, start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """Get attendance statistics"""
    query = session.query(AttendanceRecord)

    if start_date:
        query = query.filter(AttendanceRecord.check_time >= start_date)
    if end_date:
        query = query.filter(AttendanceRecord.check_time <= end_date)

    total_records = query.count()

    # Count by verification mode
    verify_mode_stats = session.query(
        AttendanceRecord.verify_mode,
        func.count(AttendanceRecord.id)
    ).group_by(AttendanceRecord.verify_mode).all()

    return {
        'total_records': total_records,
        'verify_mode_stats': {mode: count for mode, count in verify_mode_stats if mode}
    }

def get_employee_count(session: Session, branch_id: Optional[int] = None) -> int:
    """Get employee count"""
    query = session.query(Employee).filter(Employee.is_active == True)
    if branch_id:
        query = query.filter(Employee.branch_id == branch_id)
    return query.count()

def get_device_count(session: Session, status: Optional[str] = None) -> int:
    """Get device count"""
    query = session.query(Device)
    if status:
        query = query.filter(Device.status == status)
    return query.count()

# ========================
# Bulk Operations
# ========================

def bulk_create_employees(session: Session, employees: List[Dict[str, Any]]) -> List[Employee]:
    """Bulk create employees"""
    employee_objects = []
    for emp_data in employees:
        employee = Employee(**emp_data)
        if not employee.full_name:
            employee.full_name = f"{emp_data.get('name', '')} {emp_data.get('surname', '')}".strip()
        employee_objects.append(employee)

    session.bulk_save_objects(employee_objects, return_defaults=True)
    session.commit()
    return employee_objects

def bulk_create_attendance_records(session: Session, records: List[Dict[str, Any]]) -> int:
    """Bulk create attendance records"""
    record_objects = [AttendanceRecord(**record) for record in records]
    session.bulk_save_objects(record_objects)
    session.commit()
    return len(record_objects)

# ========================
# Migration & Data Import
# ========================

def import_employees_from_json(session: Session, json_file: str) -> int:
    """Import employees from JSON file"""
    import json

    count = 0
    with open(json_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                emp_data = json.loads(line.strip())

                # Check if employee already exists
                existing = get_employee_by_no(session, emp_data['employee_no'])
                if existing:
                    continue

                # Create employee
                create_employee(
                    session,
                    employee_no=emp_data['employee_no'],
                    name=emp_data['name'],
                    surname=emp_data.get('surname', ''),
                    department=emp_data.get('department', ''),
                    position=emp_data.get('position', ''),
                    card_no=emp_data.get('card_no'),
                    phone=emp_data.get('phone'),
                    email=emp_data.get('email')
                )
                count += 1
            except Exception as e:
                print(f"Error importing employee: {e}")
                continue

    return count

def import_attendance_from_json(session: Session, json_file: str) -> int:
    """Import attendance records from JSON file"""
    import json

    count = 0
    with open(json_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line.strip())

                # Get employee and device
                employee = get_employee_by_no(session, event.get('employee_no'))
                if not employee:
                    continue

                device = get_device_by_ip(session, event.get('device_ip'))
                if not device:
                    continue

                # Create attendance record
                create_attendance_record(
                    session,
                    employee_id=employee.id,
                    employee_no=event.get('employee_no'),
                    device_id=device.id,
                    check_time=datetime.fromisoformat(event.get('timestamp')),
                    verify_mode=event.get('verify_mode', 'unknown'),
                    event_type=event.get('event_type'),
                    temperature=event.get('temperature'),
                    raw_data=event
                )
                count += 1
            except Exception as e:
                print(f"Error importing attendance: {e}")
                continue

    return count

# ========================
# Health Check
# ========================

def check_database_health(session: Session) -> Dict[str, Any]:
    """Check database health and connectivity"""
    try:
        # Try a simple query
        session.query(func.now()).first()

        return {
            'status': 'healthy',
            'tables': {
                'branches': session.query(Branch).count(),
                'devices': session.query(Device).count(),
                'employees': session.query(Employee).count(),
                'attendance_records': session.query(AttendanceRecord).count(),
                'work_schedules': session.query(WorkSchedule).count(),
            }
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }

if __name__ == "__main__":
    # Test database operations
    print("Testing database connection...")

    # Initialize database
    db = init_database()
    print(" Database initialized")

    # Test session
    with get_session() as session:
        health = check_database_health(session)
        print(f" Database health: {health}")
