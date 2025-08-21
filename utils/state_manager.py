import json
import sqlite3
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class ConversationState:
    conversation_id: str
    customer_data: Dict[str, Any] = field(default_factory=dict)
    active_services: List[str] = field(default_factory=list)
    current_agent: Optional[str] = None
    office_hours_checked: bool = False
    pricing_given: bool = False
    booking_ref: Optional[str] = None
    conversation_stage: str = "initial"
    business_rules_applied: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

class StateManager:
    def __init__(self, db_path: str = "data/conversations.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        '''Initialize state database'''
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_states (
                conversation_id TEXT PRIMARY KEY,
                customer_data TEXT,
                active_services TEXT,
                current_agent TEXT,
                office_hours_checked BOOLEAN,
                pricing_given BOOLEAN,
                booking_ref TEXT,
                conversation_stage TEXT,
                business_rules_applied TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_state(self, conversation_id: str) -> ConversationState:
        '''Get conversation state'''
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM conversation_states WHERE conversation_id = ?", (conversation_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return ConversationState(
                conversation_id=row[0],
                customer_data=json.loads(row[1]) if row[1] else {},
                active_services=json.loads(row[2]) if row[2] else [],
                current_agent=row[3],
                office_hours_checked=bool(row[4]),
                pricing_given=bool(row[5]),
                booking_ref=row[6],
                conversation_stage=row[7] or "initial",
                business_rules_applied=json.loads(row[8]) if row[8] else [],
                created_at=row[9],
                updated_at=row[10]
            )
        else:
            return ConversationState(conversation_id=conversation_id)
    
    def save_state(self, state: ConversationState):
        '''Save conversation state'''
        state.updated_at = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversation_states 
            (conversation_id, customer_data, active_services, current_agent, 
             office_hours_checked, pricing_given, booking_ref, conversation_stage,
             business_rules_applied, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            state.conversation_id,
            json.dumps(state.customer_data),
            json.dumps(state.active_services),
            state.current_agent,
            state.office_hours_checked,
            state.pricing_given,
            state.booking_ref,
            state.conversation_stage,
            json.dumps(state.business_rules_applied),
            state.created_at,
            state.updated_at
        ))
        
        conn.commit()
        conn.close()
    
    def update_customer_data(self, conversation_id: str, field: str, value: Any):
        '''Update specific customer data field'''
        state = self.get_state(conversation_id)
        state.customer_data[field] = value
        self.save_state(state)
    
    def add_active_service(self, conversation_id: str, service: str):
        '''Add active service'''
        state = self.get_state(conversation_id)
        if service not in state.active_services:
            state.active_services.append(service)
            self.save_state(state)
    
    def set_current_agent(self, conversation_id: str, agent: str):
        '''Set current agent'''
        state = self.get_state(conversation_id)
        state.current_agent = agent
        self.save_state(state)
    
    def mark_office_hours_checked(self, conversation_id: str):
        '''Mark office hours as checked'''
        state = self.get_state(conversation_id)
        state.office_hours_checked = True
        self.save_state(state)
    
    def mark_pricing_given(self, conversation_id: str):
        '''Mark pricing as given'''
        state = self.get_state(conversation_id)
        state.pricing_given = True
        self.save_state(state)
    
    def set_booking_ref(self, conversation_id: str, booking_ref: str):
        '''Set booking reference'''
        state = self.get_state(conversation_id)
        state.booking_ref = booking_ref
        self.save_state(state)
    
    def add_business_rule_applied(self, conversation_id: str, rule: str):
        '''Add business rule to applied list'''
        state = self.get_state(conversation_id)
        if rule not in state.business_rules_applied:
            state.business_rules_applied.append(rule)
            self.save_state(state)
    
    def get_missing_mandatory_data(self, conversation_id: str) -> List[str]:
        '''Get list of missing mandatory customer data'''
        state = self.get_state(conversation_id)
        mandatory_fields = ["name", "postcode", "waste_type"]
        
        missing = []
        for field in mandatory_fields:
            if field not in state.customer_data or not state.customer_data[field]:
                missing.append(field)
        
        return missing
