import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify
import requests
import PyPDF2
from twilio.rest import Client

# ===============================
# FLASK APP
# ===============================
app = Flask(__name__)

# ===============================
# RULES PROCESSOR
# ===============================
class RulesProcessor:
    def __init__(self):
        self.pdf_path = "data/rules/all rules.pdf"
        self.rules_data = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if Path(self.pdf_path).exists():
            try:
                with open(self.pdf_path, "rb") as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    text = "".join(page.extract_text() for page in pdf_reader.pages)
                    return {
                        "lock_rules": {}, 
                        "office_hours": {
                            "monday_thursday": "8:00am-5:00pm",
                            "friday": "8:00am-4:30pm",
                            "saturday": "9:00am-12:00pm",
                            "sunday": "CLOSED"
                        },
                        "transfer_rules": {},
                        "pdf_text": text
                    }
            except Exception as e:
                print(f"❌ PDF load error: {e}")
        return {"lock_rules": {}, "office_hours": {}, "transfer_rules": {}, "pdf_text": ""}

# ===============================
# SMP API TOOL
# ===============================
class SMPAPITool:
    def __init__(self):
        self.koyeb_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"

    def _send_koyeb_webhook(self, url: str, payload: dict, method: str = "POST") -> dict:
        try:
            headers = {"Content-Type": "application/json"}
            if method.upper() == "POST":
                r = requests.post(url, json=payload, headers=headers, timeout=10)
            else:
                r = requests.get(url, params=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "create_booking_quote":
            url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
            payload = kwargs
            response = self._send_koyeb_webhook(url, payload, "POST")
            if not response.get("success"):
                response = self._send_koyeb_webhook(url, payload, "GET")
            return response
        elif action == "get_pricing":
            url = f"{self.koyeb_url}/api/wasteking-get-price"
            payload = kwargs
            return self._send_koyeb_webhook(url, payload, "POST")
        return {"success": False, "error": "Unknown action"}

# ===============================
# SMS TOOL
# ===============================
class SMSTool:
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            raise ValueError("Twilio credentials not set in environment variables")
        self.client = Client(self.account_sid, self.auth_token)

    def send_sms(self, to_number: str, message: str) -> Dict[str, Any]:
        try:
            msg = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=to_number
            )
            print(f"✅ SMS sent to {to_number}: SID {msg.sid}")
            return {"success": True, "sid": msg.sid}
        except Exception as e:
            print(f"❌ SMS failed to {to_number}: {e}")
            return {"success": False, "error": str(e)}

# ===============================
# DATETIME TOOL
# ===============================
class DateTimeTool:
    def _run(self) -> Dict[str, Any]:
        now = datetime.now()
        day = now.weekday()  # 0=Mon,6=Sun
        hour = now.hour
        is_business_hours = (
            (day < 4 and 8 <= hour < 17) or
            (day == 4 and 8 <= hour < 16) or
            (day == 5 and 9 <= hour < 12)
        )
        return {"current_time": now.isoformat(), "is_business_hours": is_business_hours}

# ===============================
# CENTRALIZED BOOKING PROCESSOR
# ===============================
class BookingProcessor:
    def __init__(self, smp_tool: SMPAPITool, sms_tool: SMSTool):
        self.smp_tool = smp_tool
        self.sms_tool = sms_tool

    def create_booking(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        required_fields = ['postcode', 'service', 'type', 'firstName', 'phone']
        missing = [f for f in required_fields if not customer_data.get(f)]
        if missing:
            return {"success": False, "error": f"Missing fields: {', '.join(missing)}"}

        payload = customer_data.copy()
        response = self.smp_tool._run("create_booking_quote", **payload)
        if response.get("success"):
            payment_link = response.get("payment_link")
            phone = customer_data["phone"]
            self.sms_tool.send_sms(phone, f"Your booking is confirmed. Pay here: {payment_link}")
            print(f"✅ Booking Ref: {response.get('booking_ref')}, Payment link sent to {phone}")
            return response
        return response

# ===============================
# AGENTS
# ===============================
class GenericAgent:
    def __init__(self, service_name: str, booking_processor: BookingProcessor):
        self.service_name = service_name
        self.booking_processor = booking_processor

    def process_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Example: after all info collected, create booking
        data['service'] = self.service_name
        return self.booking_processor.create_booking(data)

# ===============================
# SYSTEM INITIALIZATION
# ===============================
smp_tool = SMPAPITool()
sms_tool = SMSTool()
booking_processor = BookingProcessor(smp_tool, sms_tool)

agents = {
    "skip": GenericAgent("skip", booking_processor),
    "grab": GenericAgent("grab", booking_processor),
    "man_and_van": GenericAgent("man_and_van", booking_processor)
}

rules_processor = RulesProcessor()
datetime_tool = DateTimeTool()

# ===============================
# FLASK ROUTES
# ===============================
@app.route("/api/booking", methods=["POST"])
def booking_endpoint():
    data = request.json
    service = data.get("service")
    agent = agents.get(service)
    if not agent:
        return jsonify({"success": False, "error": f"Unknown service {service}"})
    result = agent.process_customer(data)
    return jsonify(result)

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ===============================
# RUN APP
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
