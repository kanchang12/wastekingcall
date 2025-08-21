import json
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage

class ConversationMemory:
    def __init__(self, db_path: str = "data/conversations.db", window_size: int = 10):
        self.db_path = db_path
        self.window_size = window_size
        self.memory = ConversationBufferWindowMemory(k=window_size, return_messages=True)
        self._init_db()
    
    def _init_db(self):
        '''Initialize conversation database'''
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_memory (
                conversation_id TEXT,
                message_id INTEGER,
                message_type TEXT,
                content TEXT,
                timestamp TEXT,
                metadata TEXT,
                PRIMARY KEY (conversation_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                summary TEXT,
                last_updated TEXT,
                message_count INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_message(self, conversation_id: str, message_type: str, content: str, metadata: Dict = None):
        '''Add message to memory and database'''
        # Add to LangChain memory
        if message_type == "human":
            self.memory.chat_memory.add_user_message(content)
        else:
            self.memory.chat_memory.add_ai_message(content)
        
        # Add to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get next message ID
        cursor.execute(
            "SELECT COALESCE(MAX(message_id), 0) + 1 FROM conversation_memory WHERE conversation_id = ?",
            (conversation_id,)
        )
        message_id = cursor.fetchone()[0]
        
        cursor.execute('''
            INSERT INTO conversation_memory 
            (conversation_id, message_id, message_type, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            conversation_id,
            message_id,
            message_type,
            content,
            datetime.now().isoformat(),
            json.dumps(metadata or {})
        ))
        
        conn.commit()
        conn.close()
    
    def get_conversation_history(self, conversation_id: str, limit: int = None) -> List[Dict]:
        '''Get conversation history from database'''
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT message_type, content, timestamp, metadata 
            FROM conversation_memory 
            WHERE conversation_id = ? 
            ORDER BY message_id
        '''
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query, (conversation_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "type": row[0],
                "content": row[1], 
                "timestamp": row[2],
                "metadata": json.loads(row[3]) if row[3] else {}
            }
            for row in rows
        ]
    
    def clear_conversation(self, conversation_id: str):
        '''Clear conversation from memory and database'''
        self.memory.clear()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_memory WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conversation_id,))
        conn.commit()
        conn.close()
    
    def get_conversation_summary(self, conversation_id: str) -> Optional[str]:
        '''Get conversation summary'''
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT summary FROM conversation_summaries WHERE conversation_id = ?", (conversation_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def update_conversation_summary(self, conversation_id: str, summary: str):
        '''Update conversation summary'''
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversation_summaries 
            (conversation_id, summary, last_updated, message_count)
            VALUES (?, ?, ?, ?)
        ''', (
            conversation_id,
            summary,
            datetime.now().isoformat(),
            len(self.memory.chat_memory.messages)
        ))
        
        conn.commit()
        conn.close()
