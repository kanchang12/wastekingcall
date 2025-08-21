import os
from typing import Dict, Any

class Settings:
    def __init__(self):
        self.load_environment_variables()
    
    def load_environment_variables(self):
        '''Load all environment variables'''
        
        # API Configuration
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
        self.WASTEKING_BASE_URL = os.getenv('WASTEKING_BASE_URL', 'https://wk-smp-api-dev.azurewebsites.net/')
        self.WASTEKING_ACCESS_TOKEN = os.getenv('WASTEKING_ACCESS_TOKEN', '')
        
        # Twilio Configuration
        self.TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
        self.TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
        self.TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', '')
        
        # Database Configuration
        self.DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/conversations.db')
        
        # Agent Configuration
        self.MAX_CONVERSATION_MEMORY = int(os.getenv('MAX_CONVERSATION_MEMORY', '50'))
        self.AGENT_TIMEOUT_SECONDS = int(os.getenv('AGENT_TIMEOUT_SECONDS', '30'))
        self.ENABLE_COMPLIANCE_MONITORING = os.getenv('ENABLE_COMPLIANCE_MONITORING', 'true').lower() == 'true'
        
        # Business Rules Configuration
        self.STRICT_RULE_COMPLIANCE = os.getenv('STRICT_RULE_COMPLIANCE', 'true').lower() == 'true'
        self.ENABLE_EXACT_SCRIPT_VALIDATION = os.getenv('ENABLE_EXACT_SCRIPT_VALIDATION', 'true').lower() == 'true'
        self.LOCK_RULE_ENFORCEMENT = os.getenv('LOCK_RULE_ENFORCEMENT', 'true').lower() == 'true'
        
        # Logging Configuration
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FILE = os.getenv('LOG_FILE', 'data/logs/wasteking_ai.log')
        self.ENABLE_STRUCTURED_LOGGING = os.getenv('ENABLE_STRUCTURED_LOGGING', 'true').lower() == 'true'
        
        # Performance Configuration
        self.VECTOR_STORE_CACHE_SIZE = int(os.getenv('VECTOR_STORE_CACHE_SIZE', '1000'))
        self.EMBEDDING_BATCH_SIZE = int(os.getenv('EMBEDDING_BATCH_SIZE', '32'))
        self.AGENT_CONCURRENCY_LIMIT = int(os.getenv('AGENT_CONCURRENCY_LIMIT', '10'))
    
    def get_agent_config(self) -> Dict[str, Any]:
        '''Get agent configuration'''
        return {
            'max_memory': self.MAX_CONVERSATION_MEMORY,
            'timeout': self.AGENT_TIMEOUT_SECONDS,
            'compliance_monitoring': self.ENABLE_COMPLIANCE_MONITORING,
            'strict_compliance': self.STRICT_RULE_COMPLIANCE,
            'script_validation': self.ENABLE_EXACT_SCRIPT_VALIDATION,
            'lock_enforcement': self.LOCK_RULE_ENFORCEMENT
        }
    
    def get_api_config(self) -> Dict[str, Any]:
        '''Get API configuration'''
        return {
            'openai_key': self.OPENAI_API_KEY,
            'wasteking_url': self.WASTEKING_BASE_URL,
            'wasteking_token': self.WASTEKING_ACCESS_TOKEN,
            'twilio_sid': self.TWILIO_ACCOUNT_SID,
            'twilio_token': self.TWILIO_AUTH_TOKEN,
            'twilio_phone': self.TWILIO_PHONE_NUMBER
        }
    
    def get_database_config(self) -> Dict[str, Any]:
        '''Get database configuration'''
        return {
            'path': self.DATABASE_PATH
        }
    
    def validate_configuration(self) -> Dict[str, Any]:
        '''Validate configuration'''
        issues = []
        
        if not self.OPENAI_API_KEY:
            issues.append("OPENAI_API_KEY not set")
        
        if not self.WASTEKING_ACCESS_TOKEN:
            issues.append("WASTEKING_ACCESS_TOKEN not set")
        
        if not self.TWILIO_ACCOUNT_SID or not self.TWILIO_AUTH_TOKEN:
            issues.append("Twilio credentials not set - SMS features disabled")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }

# Global settings instance
settings = Settings()
