# api.py
"""
Extended API Routes
Additional endpoints for advanced features
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel

from database import (
    get_session,
    get_attendance_by_employee,
    get_attendance_today,
    get_attendance_summary,
    create_or_update_attendance_summary,
    get_all_branches,
    get_branch_by_code,
    get_all_work_schedules,
    get_work_schedule_by_code,
    get_employee_count,
    get_device_count,
    get_attendance_statistics
)
from utils import (
    format_date,
    calculate_work_hours,
    calculate_late_minutes,
    calculate_attendance_stats
)

# Create router
router = APIRouter(prefix="/api/v2", tags=["Extended API"])

# Pydantic models
class AttendanceSummaryResponse(BaseModel):
    employee_no: str
    date: str
    first_check_in: Optional[str]
    last_check_out: Optional[str]
    total_hours: float
    late_minutes: int
    status: str

class BranchStats(BaseModel):
    branch_id: int
    branch_name: str
    employee_count: int
    device_count: int
    today_attendance: int

# ========================
# Branch Management
# ========================

@router.get("/branches")
async def get_branches():
    """Get all branches"""
    try:
        with get_session() as session:
            branches = get_all_branches(session)
            return {
                "total": len(branches),
                "branches": [
                    {
                        "id": b.id,
                        "name": b.name,
                        "code": b.code,
                        "city": b.city,
                        "address": b.address,
                        "phone": b.phone,
                        "manager": b.manager_name
                    }
                    for b in branches
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/branches/{branch_code}/stats")
async def get_branch_stats(branch_code: str):
    """Get statistics for specific branch"""
    try:
        with get_session() as session:
            branch = get_branch_by_code(session, branch_code)
            if not branch:
                raise HTTPException(status_code=404, detail="Branch not found")

            emp_count = get_employee_count(session, branch_id=branch.id)
            dev_count = get_device_count(session)

            # Get today's attendance for branch
            today_records = get_attendance_today(session, branch_id=branch.id)

            return {
                "branch_code": branch_code,
                "branch_name": branch.name,
                "employee_count": emp_count,
                "device_count": dev_count,
                "today_attendance": len(today_records)
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# Work Schedules
# ========================

@router.get("/schedules")
async def get_schedules():
    """Get all work schedules"""
    try:
        with get_session() as session:
            schedules = get_all_work_schedules(session)
            return {
                "total": len(schedules),
                "schedules": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "code": s.code,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "break_start": s.break_start,
                        "break_end": s.break_end,
                        "late_tolerance": s.late_tolerance,
                        "overtime_allowed": s.overtime_allowed
                    }
                    for s in schedules
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# Attendance Summary
# ========================

@router.get("/attendance/summary/{employee_no}")
async def get_employee_summary(
    employee_no: str,
    days: int = Query(default=7, ge=1, le=90)
):
    """Get attendance summary for employee"""
    try:
        with get_session() as session:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Get attendance records
            records = get_attendance_by_employee(
                session,
                employee_no,
                start_date=start_date,
                end_date=end_date
            )

            # Calculate summary statistics
            summary = {
                "employee_no": employee_no,
                "period": {
                    "start": format_date(start_date),
                    "end": format_date(end_date),
                    "days": days
                },
                "total_records": len(records),
                "attendance_by_day": {}
            }

            # Group by date
            from collections import defaultdict
            by_date = defaultdict(list)
            for record in records:
                date_key = record.check_time.date().isoformat()
                by_date[date_key].append(record)

            # Calculate daily stats
            for date_key, day_records in by_date.items():
                day_records.sort(key=lambda r: r.check_time)
                first_check = day_records[0].check_time
                last_check = day_records[-1].check_time

                summary["attendance_by_day"][date_key] = {
                    "check_in": first_check.isoformat(),
                    "check_out": last_check.isoformat(),
                    "total_hours": calculate_work_hours(first_check, last_check),
                    "records": len(day_records)
                }

            return summary

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# Advanced Statistics
# ========================

@router.get("/statistics/detailed")
async def get_detailed_statistics(
    days: int = Query(default=7, ge=1, le=90)
):
    """Get detailed system statistics"""
    try:
        with get_session() as session:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Get attendance statistics
            att_stats = get_attendance_statistics(session, start_date, end_date)

            # Get employee and device counts
            total_employees = get_employee_count(session)
            total_devices = get_device_count(session)
            online_devices = get_device_count(session, status='online')

            return {
                "period": {
                    "start": format_date(start_date),
                    "end": format_date(end_date),
                    "days": days
                },
                "employees": {
                    "total": total_employees
                },
                "devices": {
                    "total": total_devices,
                    "online": online_devices,
                    "offline": total_devices - online_devices
                },
                "attendance": att_stats,
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/statistics/by-date")
async def get_statistics_by_date(date: str):
    """Get statistics for specific date (YYYY-MM-DD)"""
    try:
        # Parse date
        target_date = datetime.strptime(date, "%Y-%m-%d")

        with get_session() as session:
            # Get attendance for specific date
            start_of_day = target_date.replace(hour=0, minute=0, second=0)
            end_of_day = target_date.replace(hour=23, minute=59, second=59)

            att_stats = get_attendance_statistics(session, start_of_day, end_of_day)

            return {
                "date": date,
                "statistics": att_stats
            }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# Reporting
# ========================

@router.get("/reports/late-arrivals")
async def get_late_arrivals(
    date: Optional[str] = None,
    threshold_minutes: int = Query(default=15, ge=1, le=120)
):
    """Get late arrival report"""
    try:
        # Parse date or use today
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            target_date = datetime.now()

        with get_session() as session:
            # Get today's attendance
            records = get_attendance_today(session)

            # Filter late arrivals (assuming 9:00 AM start time)
            late_arrivals = []
            for record in records:
                late_min = calculate_late_minutes(record.check_time, "09:00")
                if late_min >= threshold_minutes:
                    late_arrivals.append({
                        "employee_no": record.employee_no,
                        "check_in": record.check_time.isoformat(),
                        "late_minutes": late_min,
                        "verify_mode": record.verify_mode
                    })

            return {
                "date": format_date(target_date),
                "threshold_minutes": threshold_minutes,
                "total_late": len(late_arrivals),
                "late_arrivals": late_arrivals
            }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reports/absent-employees")
async def get_absent_employees(date: Optional[str] = None):
    """Get absent employees report"""
    try:
        # Parse date or use today
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        else:
            target_date = datetime.now()

        with get_session() as session:
            from database import get_all_employees

            # Get all active employees
            all_employees = get_all_employees(session, active_only=True)

            # Get attendance for date
            records = get_attendance_today(session)
            present_employees = set(r.employee_no for r in records)

            # Find absent employees
            absent = [
                {
                    "employee_no": emp.employee_no,
                    "name": emp.full_name,
                    "department": emp.department,
                    "position": emp.position
                }
                for emp in all_employees
                if emp.employee_no not in present_employees
            ]

            return {
                "date": format_date(target_date),
                "total_employees": len(all_employees),
                "present": len(present_employees),
                "absent": len(absent),
                "absent_employees": absent
            }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# Data Export
# ========================

@router.get("/export/attendance-report")
async def export_attendance_report(
    start_date: str,
    end_date: str,
    format: str = Query(default="csv", regex="^(csv|json)$")
):
    """Export attendance report for date range"""
    try:
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        if start > end:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        with get_session() as session:
            from database import get_recent_attendance

            # Get attendance records
            records = get_recent_attendance(session, limit=10000)

            # Filter by date range
            filtered = [
                r for r in records
                if start <= r.check_time <= end
            ]

            if format == "csv":
                from utils import export_to_csv
                import tempfile
                import os

                # Create temp file
                fd, path = tempfile.mkstemp(suffix='.csv')
                headers = ['employee_no', 'check_time', 'verify_mode', 'temperature']

                data = [
                    {
                        'employee_no': r.employee_no,
                        'check_time': r.check_time.isoformat(),
                        'verify_mode': r.verify_mode,
                        'temperature': r.temperature or ''
                    }
                    for r in filtered
                ]

                export_to_csv(data, headers, path)

                # Read file
                with open(path, 'r') as f:
                    csv_content = f.read()

                os.close(fd)
                os.unlink(path)

                from fastapi.responses import Response
                return Response(
                    content=csv_content,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename=attendance_{start_date}_{end_date}.csv"
                    }
                )
            else:  # JSON
                from utils import format_attendance_record
                return {
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_records": len(filtered),
                    "records": [format_attendance_record(r) for r in filtered]
                }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Info endpoint
@router.get("/info")
async def api_info():
    """Get API information"""
    return {
        "api_version": "2.0",
        "description": "Extended API for Hikvision Attendance System",
        "endpoints": {
            "branches": "Branch management",
            "schedules": "Work schedule management",
            "attendance": "Advanced attendance queries",
            "statistics": "Detailed statistics",
            "reports": "Attendance reports",
            "export": "Data export functionality"
        }
    }
