# models.py
"""
Database Models for Hikvision Attendance System
PostgreSQL + SQLAlchemy ORM
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text, LargeBinary, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func
from datetime import datetime
import os
from typing import Optional

Base = declarative_base()

# Database Models

class Branch(Base):
    """Filiallar jadvali"""
    __tablename__ = 'branches'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    address = Column(String(255))
    city = Column(String(50))
    phone = Column(String(20))
    manager_name = Column(String(100))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    devices = relationship("Device", back_populates="branch")
    employees = relationship("Employee", back_populates="branch")

class Device(Base):
    """Terminal qurilmalar jadvali"""
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, nullable=False)
    serial_number = Column(String(50), unique=True)
    model = Column(String(50))
    ip_address = Column(String(15), unique=True, nullable=False)
    port = Column(Integer, default=80)
    username = Column(String(50), default='admin')
    password = Column(String(100))  # Should be encrypted
    branch_id = Column(Integer, ForeignKey('branches.id'))
    location = Column(String(100))  # Specific location within branch
    status = Column(String(20), default='offline')  # online/offline/error
    last_seen = Column(DateTime)
    firmware_version = Column(String(50))
    isup_enabled = Column(Boolean, default=True)
    isup_port = Column(Integer, default=7660)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    branch = relationship("Branch", back_populates="devices")
    attendance_records = relationship("AttendanceRecord", back_populates="device")

class Employee(Base):
    """Hodimlar jadvali"""
    __tablename__ = 'employees'
    
    id = Column(Integer, primary_key=True, index=True)
    employee_no = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100))
    full_name = Column(String(200))
    department = Column(String(100))
    position = Column(String(100))
    branch_id = Column(Integer, ForeignKey('branches.id'))
    phone = Column(String(20))
    email = Column(String(100))
    card_no = Column(String(50), unique=True, nullable=True)
    face_registered = Column(Boolean, default=False)
    fingerprint_registered = Column(Boolean, default=False)
    pin_code = Column(String(20))  # Should be hashed
    hire_date = Column(DateTime)
    termination_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    access_level = Column(Integer, default=1)  # 1=normal, 2=supervisor, 3=admin
    work_schedule_id = Column(Integer, ForeignKey('work_schedules.id'))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    branch = relationship("Branch", back_populates="employees")
    attendance_records = relationship("AttendanceRecord", back_populates="employee")
    face_data = relationship("FaceData", back_populates="employee")
    work_schedule = relationship("WorkSchedule", back_populates="employees")

class FaceData(Base):
    """Yuz ma'lumotlari jadvali"""
    __tablename__ = 'face_data'
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False)
    face_image = Column(LargeBinary)  # Binary image data
    face_template = Column(Text)  # Base64 encoded template
    quality_score = Column(Float)  # Face quality score
    device_id = Column(Integer, ForeignKey('devices.id'))
    is_primary = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    employee = relationship("Employee", back_populates="face_data")

class AttendanceRecord(Base):
    """Davomat yozuvlari jadvali"""
    __tablename__ = 'attendance_records'
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False)
    employee_no = Column(String(50), index=True)  # Denormalized for speed
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    check_time = Column(DateTime, nullable=False, index=True)
    check_type = Column(String(20))  # checkIn/checkOut/break/overtime
    verify_mode = Column(String(20))  # face/card/fingerprint/password
    temperature = Column(Float, nullable=True)  # If device supports
    mask_worn = Column(Boolean, nullable=True)  # If device supports
    photo = Column(LargeBinary, nullable=True)  # Capture photo
    event_type = Column(Integer)  # Raw event type from device
    is_manual = Column(Boolean, default=False)  # Manual entry
    manual_reason = Column(String(200))  # Reason for manual entry
    synced = Column(Boolean, default=False)  # Synced with central server
    raw_data = Column(JSON)  # Store raw event data
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    employee = relationship("Employee", back_populates="attendance_records")
    device = relationship("Device", back_populates="attendance_records")

class WorkSchedule(Base):
    """Ish jadvallari"""
    __tablename__ = 'work_schedules'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True)
    start_time = Column(String(5))  # HH:MM format
    end_time = Column(String(5))
    break_start = Column(String(5))
    break_end = Column(String(5))
    late_tolerance = Column(Integer, default=5)  # Minutes
    early_leave_tolerance = Column(Integer, default=5)
    overtime_allowed = Column(Boolean, default=True)
    weekend_days = Column(String(20), default='6,7')  # Saturday, Sunday
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    employees = relationship("Employee", back_populates="work_schedule")

class AttendanceSummary(Base):
    """Kunlik davomat xulosasi"""
    __tablename__ = 'attendance_summary'
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    first_check_in = Column(DateTime)
    last_check_out = Column(DateTime)
    total_hours = Column(Float)
    overtime_hours = Column(Float)
    late_minutes = Column(Integer)
    early_leave_minutes = Column(Integer)
    status = Column(String(20))  # present/absent/late/half-day/holiday/weekend
    break_duration = Column(Integer)  # Minutes
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class SystemLog(Base):
    """Tizim loglari"""
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20))  # INFO/WARNING/ERROR/CRITICAL
    module = Column(String(50))
    message = Column(Text)
    details = Column(JSON)
    user_id = Column(Integer, nullable=True)
    ip_address = Column(String(15))
    created_at = Column(DateTime, default=func.now())

class User(Base):
    """Tizim foydalanuvchilari (admin panel uchun)"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default='viewer')  # admin/manager/operator/viewer
    branch_id = Column(Integer, ForeignKey('branches.id'), nullable=True)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

# Database connection and session
class Database:
    """Database connection manager"""
    
    def __init__(self, database_url: Optional[str] = None):
        if not database_url:
            database_url = os.getenv(
                'DATABASE_URL',
                'postgresql://user:password@localhost/attendance_db'
            )
        
        self.engine = create_engine(
            database_url,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            echo=False  # Set to True for SQL logging
        )
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
    
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(bind=self.engine)
        print("Database tables created successfully")
    
    def drop_tables(self):
        """Drop all tables"""
        Base.metadata.drop_all(bind=self.engine)
        print("Database tables dropped")
    
    def get_session(self):
        """Get database session"""
        return self.SessionLocal()
    
    def init_data(self):
        """Initialize with sample data"""
        session = self.get_session()
        
        try:
            # Add sample branch
            if not session.query(Branch).first():
                branch = Branch(
                    name="Bosh ofis",
                    code="HQ001",
                    address="Tashkent, Yunusabad",
                    city="Tashkent"
                )
                session.add(branch)
                session.commit()
                print("Sample branch added")
            
            # Add sample work schedule
            if not session.query(WorkSchedule).first():
                schedule = WorkSchedule(
                    name="Standard 9-6",
                    code="STD001",
                    start_time="09:00",
                    end_time="18:00",
                    break_start="13:00",
                    break_end="14:00"
                )
                session.add(schedule)
                session.commit()
                print("Sample work schedule added")
            
        except Exception as e:
            print(f"Error initializing data: {e}")
            session.rollback()
        finally:
            session.close()

# Utility functions
def get_db():
    """Dependency for FastAPI"""
    db = Database()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()

if __name__ == "__main__":
    # Test database connection
    db = Database()
    
    # Create tables
    db.create_tables()
    
    # Initialize sample data
    db.init_data()
    
    print("Database setup completed")