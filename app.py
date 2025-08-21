import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from langchain_openai import ChatOpenAI

# Import our agents and components
from agents.orchestrator import AgentOrchestrator
from agents.skip_hire_agent import SkipHireAgent
from agents.man_van_agent import ManVanAgent
from agents.grab_hire_agent import GrabHireAgent
from agents.pricing_agent import PricingAgent
from tools.smp_api_tool import SMPAPITool
from tools.sms_tool import SMSTool
from tools.datetime_tool import DateTimeTool
from utils.state_manager import StateManager
from utils.rules_processor import RulesProcessor
from config.settings import settings

app = Flask(__name__)

# Initialize components
def initialize_system():
    '''Initialize the complete multi-agent system'''
    
    # Validate configuration
    config_validation = settings.validate_configuration()
    if not config_validation['valid']:
        print(f"Configuration issues: {config_validation['issues']}")
    
    # Initialize LLM
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        openai_api_key=settings.OPENAI_API_KEY
    ) if settings.OPENAI_API_KEY else None
    
    if not llm:
        print("Warning: OpenAI API key not set - using fallback responses")
        return None
    
    # Initialize tools
    tools = [
        SMPAPITool(
            base_url=settings.WASTEKING_BASE_URL,
            access_token=settings.WASTEKING_ACCESS_TOKEN
        ),
        SMSTool(
            account_sid=settings.TWILIO_ACCOUNT_SID,
            auth_token=settings.TWILIO_AUTH_TOKEN,
            phone_number=settings.TWILIO_PHONE_NUMBER
        ),
        DateTimeTool()
    ]
    
    print(f"Initialized {len(tools)} tools")
    
    # Initialize agents
    agents = {
        'skip_hire': SkipHireAgent(llm, tools),
        'man_and_van': ManVanAgent(llm, tools),
        'grab_hire': GrabHireAgent(llm, tools),
        'pricing': PricingAgent(llm, tools)
    }
    
    print(f"Initialized {len(agents)} agents")
    
    # Initialize orchestrator
    orchestrator = AgentOrchestrator(llm, agents)
    
    # Initialize supporting components
    state_manager = StateManager(settings.DATABASE_PATH)
    rules_processor = RulesProcessor()
    
    print("System initialization complete")
    
    return {
        'orchestrator': orchestrator,
        'state_manager': state_manager,
        'rules_processor': rules_processor,
        'tools': tools
    }

# Initialize system
system = initialize_system()

@app.route('/')
def index():
    '''Main endpoint'''
    return jsonify({
        "message": "WasteKing Multi-Agent AI System",
        "status": "running",
        "system_initialized": system is not None,
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            "/api/wasteking",
            "/api/health", 
            "/api/agents",
            "/api/conversation-state"
        ]
    })

@app.route('/api/wasteking', methods=['POST'])
def process_customer_message():
    '''Main endpoint for processing customer messages'''
    try:
        if not system:
            return jsonify({
                "success": False,
                "message": "System not properly initialized - check configuration"
            }), 500
        
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('elevenlabs_conversation_id', f"conv_{int(datetime.now().timestamp())}")
        
        print(f"Processing message: {customer_message}")
        print(f"Conversation ID: {conversation_id}")
        
        if not customer_message:
            return jsonify({
                "success": False,
                "message": "No customer message provided"
            }), 400
        
        # Process message through orchestrator
        print("Calling orchestrator...")
        result = system['orchestrator'].process_customer_message(
            message=customer_message,
            conversation_id=conversation_id
        )
        
        print(f"Orchestrator response: {result['response']}")
        
        return jsonify({
            "success": True,
            "message": result['response'],
            "conversation_id": conversation_id,
            "routing_info": result.get('routing', {}),
            "active_services": result.get('state', {}).get('active_services', []),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        return jsonify({
            "success": False,
            "message": "I understand. Let me connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    '''Health check endpoint'''
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_initialized": system is not None,
            "configuration_valid": settings.validate_configuration()['valid']
        }
        
        if system:
            health_status.update({
                "agents_loaded": len(system['orchestrator'].agents),
                "tools_loaded": len(system['tools']),
                "database_path": settings.DATABASE_PATH
            })
        
        return jsonify(health_status)
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/agents', methods=['GET'])
def get_agent_info():
    '''Get information about loaded agents'''
    if not system:
        return jsonify({"error": "System not initialized"}), 500
    
    agent_info = {}
    for name, agent in system['orchestrator'].agents.items():
        agent_info[name] = {
            "type": agent.__class__.__name__,
            "status": "loaded",
            "memory_size": len(agent.memory.chat_memory.messages) if hasattr(agent, 'memory') else 0
        }
    
    return jsonify({
        "agents": agent_info,
        "total_agents": len(agent_info)
    })

@app.route('/api/conversation-state/<conversation_id>', methods=['GET'])
def get_conversation_state(conversation_id):
    '''Get conversation state'''
    if not system:
        return jsonify({"error": "System not initialized"}), 500
    
    try:
        state = system['state_manager'].get_state(conversation_id)
        return jsonify({
            "conversation_id": state.conversation_id,
            "customer_data": state.customer_data,
            "active_services": state.active_services,
            "current_agent": state.current_agent,
            "conversation_stage": state.conversation_stage,
            "created_at": state.created_at,
            "updated_at": state.updated_at
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.after_request
def after_request(response):
    '''Add CORS headers'''
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("Starting WasteKing Multi-Agent AI System...")
    print(f"Configuration valid: {settings.validate_configuration()['valid']}")
    
    if system:
        print("System initialized successfully")
        print(f"Agents loaded: {list(system['orchestrator'].agents.keys())}")
    else:
        print("System initialization failed - check configuration")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
