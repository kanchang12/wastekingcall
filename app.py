# app.py - MINIMAL CHANGES to your existing file
# CHANGES: Updated to use fixed agents with proper routing and hardcoded supplier phone

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
from tools.smp_api_tool import SMPAPITool  # CHANGE: This will use the fixed version with hardcoded phone
from tools.sms_tool import SMSTool
from tools.datetime_tool import DateTimeTool
from utils.state_manager import StateManager
from utils.rules_processor import RulesProcessor
from config.settings import settings

app = Flask(__name__)

# CHANGE: Add conversation context tracking to prevent data contamination
conversation_contexts = {}

# Initialize components
def initialize_system():
    '''Initialize the complete multi-agent system'''
    
    print("Loading rules from PDF...")
    
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
    
    # Initialize agents - using fixed versions
    agents = {
        'skip_hire': SkipHireAgent(llm, tools),
        'mav': ManVanAgent(llm, tools),  # CHANGE: Fixed version with strict restrictions
        'grab_hire': GrabHireAgent(llm, tools),  # CHANGE: Fixed version handles ALL except mav/skip
        'pricing': PricingAgent(llm, tools)
    }
    
    print(f"Initialized {len(agents)} agents")
    print("✅ Grab Hire: Handles ALL services except mav and skip")
    print("✅ Man & Van: Light items only (strict heavy item restrictions)")
    print("✅ Skip Hire: Traditional skip services")
    print("✅ SMP API Tool: Using hardcoded supplier phone +447394642517")
    
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

# CHANGE: Helper function to manage conversation context
def manage_conversation_context(conversation_id, message, data=None):
    """Manage conversation context to prevent data contamination"""
    global conversation_contexts
    
    if conversation_id not in conversation_contexts:
        conversation_contexts[conversation_id] = {}
    
    context = conversation_contexts[conversation_id]
    
    # Check for new postcode - reset context if different
    import re
    postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', message.upper())
    if postcode_match:
        new_postcode = postcode_match.group(1).replace(' ', '')
        if context.get('postcode') and context['postcode'] != new_postcode:
            print(f"🔄 NEW POSTCODE DETECTED: {new_postcode} (clearing old: {context['postcode']})")
            conversation_contexts[conversation_id] = {'postcode': new_postcode}
        else:
            context['postcode'] = new_postcode
    
    # Add any additional data
    if data:
        context.update(data)
    
    # Keep only last 20 conversations to prevent memory issues
    if len(conversation_contexts) > 20:
        oldest_key = next(iter(conversation_contexts))
        del conversation_contexts[oldest_key]
    
    return context

# Initialize system
system = initialize_system()

@app.route('/')
def index():
    '''Main endpoint'''
    return jsonify({
        "message": "WasteKing Multi-Agent AI System - FIXED VERSION",
        "status": "running",
        "system_initialized": system is not None,
        "timestamp": datetime.now().isoformat(),
        "features": [
            "Fixed booking confirmation with automatic supplier calling",
            "Hardcoded supplier phone: +447394642517", 
            "Grab agent handles ALL except mav/skip",
            "Enhanced conversation context management",
            "No data contamination between conversations"
        ],
        "endpoints": [
            "/api/wasteking",
            "/api/health", 
            "/api/agents",
            "/api/conversation-state"
        ]
    })

@app.route('/api/wasteking', methods=['POST'])
def process_customer_message():
    '''Main endpoint for processing customer messages - ENHANCED'''
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
        
        # CHANGE: Manage conversation context to prevent data contamination
        context = manage_conversation_context(
            conversation_id, 
            customer_message, 
            data.get('context', {})
        )
        
        # CHANGE: Add context to the orchestrator call
        print("Calling orchestrator with context...")
        result = system['orchestrator'].process_customer_message(
            message=customer_message,
            conversation_id=conversation_id,
            context=context  # Pass context to prevent data issues
        )
        
        print(f"Orchestrator response: {result['response']}")
        
        # CHANGE: Enhanced response with routing info
        response_data = {
            "success": True,
            "message": result['response'],
            "conversation_id": conversation_id,
            "routing_info": result.get('routing', {}),
            "active_services": result.get('state', {}).get('active_services', []),
            "timestamp": datetime.now().isoformat()
        }
        
        # CHANGE: Add booking/supplier info if available
        if 'booking_ref' in result:
            response_data['booking_ref'] = result['booking_ref']
            response_data['supplier_called'] = result.get('supplier_called', False)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        return jsonify({
            "success": False,
            "message": "I understand. Let me connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    '''Health check endpoint - ENHANCED'''
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_initialized": system is not None,
            "configuration_valid": settings.validate_configuration()['valid'],
            "version": "Fixed WasteKing System v2.0"  # CHANGE: Version indicator
        }
        
        if system:
            health_status.update({
                "agents_loaded": len(system['orchestrator'].agents),
                "tools_loaded": len(system['tools']),
                "database_path": settings.DATABASE_PATH,
                "active_conversations": len(conversation_contexts),  # CHANGE: Show active conversations
                "supplier_phone": "+447394642517"  # CHANGE: Show hardcoded supplier phone
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
    '''Get information about loaded agents - ENHANCED'''
    if not system:
        return jsonify({"error": "System not initialized"}), 500
    
    agent_info = {}
    for name, agent in system['orchestrator'].agents.items():
        agent_info[name] = {
            "type": agent.__class__.__name__,
            "status": "loaded",
            "memory_size": len(agent.memory.chat_memory.messages) if hasattr(agent, 'memory') else 0,
            # CHANGE: Add agent capabilities
            "capabilities": {
                "skip_hire": "Traditional skip services",
                "mav": "Light items only (refuses heavy materials)",
                "grab_hire": "ALL services except mav/skip (heavy materials, large volumes)",
                "pricing": "Pricing calculations"
            }.get(name, "General purpose")
        }
    
    return jsonify({
        "agents": agent_info,
        "total_agents": len(agent_info),
        "routing_logic": "Grab handles everything except mav and skip"  # CHANGE: Show routing logic
    })

@app.route('/api/conversation-state/<conversation_id>', methods=['GET'])
def get_conversation_state(conversation_id):
    '''Get conversation state - ENHANCED'''
    if not system:
        return jsonify({"error": "System not initialized"}), 500
    
    try:
        # CHANGE: Include our conversation context
        our_context = conversation_contexts.get(conversation_id, {})
        
        state = system['state_manager'].get_state(conversation_id)
        return jsonify({
            "conversation_id": state.conversation_id,
            "customer_data": state.customer_data,
            "active_services": state.active_services,
            "current_agent": state.current_agent,
            "conversation_stage": state.conversation_stage,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "context": our_context  # CHANGE: Include our context tracking
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# CHANGE: New endpoint to clear conversation context if needed
@app.route('/api/conversation-state/<conversation_id>', methods=['DELETE'])
def clear_conversation_state(conversation_id):
    '''Clear conversation state'''
    global conversation_contexts
    
    if conversation_id in conversation_contexts:
        del conversation_contexts[conversation_id]
        return jsonify({"success": True, "message": f"Cleared context for {conversation_id}"})
    else:
        return jsonify({"success": False, "message": "Conversation not found"})

@app.after_request
def after_request(response):
    '''Add CORS headers'''
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("Starting WasteKing Multi-Agent AI System - FIXED VERSION...")
    print(f"Configuration valid: {settings.validate_configuration()['valid']}")
    
    if system:
        print("System initialized successfully")
        print(f"Agents loaded: {list(system['orchestrator'].agents.keys())}")
        print("🔧 KEY FIXES APPLIED:")
        print("  ✅ Grab agent handles ALL except mav/skip")
        print("  ✅ Hardcoded supplier phone: +447394642517")
        print("  ✅ Fixed booking confirmation with automatic supplier calling")
        print("  ✅ Enhanced conversation context management")
        print("  ✅ No data contamination between conversations")
    else:
        print("System initialization failed - check configuration")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
