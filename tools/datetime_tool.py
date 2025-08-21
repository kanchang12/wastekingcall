from datetime import datetime, timedelta
from typing import Dict, Any
from langchain.tools import BaseTool

class DateTimeTool(BaseTool):
    name: str = "datetime"
    description: str = "Get current date/time and check office hours"
    
    def _run(self, action: str = "get_current") -> Dict[str, Any]:
        now = datetime.now()
        
        office_hours_info = self._check_office_hours(now)
        
        return {
            "current_date": now.strftime("%Y-%m-%d"),
            "current_time": now.strftime("%H:%M"),
            "current_day": now.strftime("%A"),
            "tomorrow_date": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
            "office_hours": office_hours_info["status"],
            "office_hours_details": office_hours_info
        }
    
    def _check_office_hours(self, dt: datetime) -> Dict[str, Any]:
        weekday = dt.weekday()
        hour = dt.hour + (dt.minute / 60.0)
        
        if weekday < 4:  # Monday-Thursday
            is_open = 8 <= hour < 17
            hours = "8:00am-5:00pm"
        elif weekday == 4:  # Friday
            is_open = 8 <= hour < 16.5
            hours = "8:00am-4:30pm"
        elif weekday == 5:  # Saturday
            is_open = 9 <= hour < 12
            hours = "9:00am-12:00pm"
        else:  # Sunday
            is_open = False
            hours = "Closed"
        
        return {
            "status": "open" if is_open else "closed",
            "hours": hours,
            "day": dt.strftime("%A"),
            "current_time": dt.strftime("%H:%M")
        }
