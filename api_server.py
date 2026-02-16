"""
A&I ARMOUR - FastAPI Server
REST API + WebSocket for real-time dashboard updates
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncio
import json
from datetime import datetime
import uvicorn

from backend import (
    AIArmourSystem, 
    AgentType,
    Lead, 
    LeadStatus,
    Invoice,
    Installation
)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="A&I ARMOUR API", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the AI system
ai_system = AIArmourSystem()

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

# ============================================================================
# PYDANTIC MODELS (Request/Response)
# ============================================================================

class CommandRequest(BaseModel):
    command: str
    context: Optional[Dict] = {}

class LeadCreate(BaseModel):
    name: str
    email: str
    company: Optional[str] = None
    phone: Optional[str] = None
    source: str
    estimated_value: float

class InvoiceCreate(BaseModel):
    client_name: str
    amount: float
    items: List[Dict]
    due_days: int = 30

class InstallationCreate(BaseModel):
    client_name: str
    address: str
    scheduled_date: str
    contractor_id: str
    box_serial_numbers: List[str]
    notes: Optional[str] = ""

# ============================================================================
# WEBSOCKET FOR REAL-TIME UPDATES
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time dashboard updates"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Keep connection alive and send updates
            data = await websocket.receive_text()
            
            # Echo back for now (in production, process commands)
            await websocket.send_text(f"Received: {data}")
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)

async def broadcast_update(message: Dict):
    """Broadcast update to all connected dashboards"""
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except:
            active_connections.remove(connection)

# ============================================================================
# REST API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Serve the dashboard"""
    return FileResponse("dashboard.html")

@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get current dashboard metrics"""
    return ai_system.get_dashboard_data()

@app.post("/api/command")
async def execute_command(request: CommandRequest):
    """Execute a manual command to AI agents"""
    result = await ai_system.manual_command(request.command)
    
    # Broadcast update to dashboard
    await broadcast_update({
        "type": "command_executed",
        "command": request.command,
        "result": result,
        "timestamp": datetime.now().isoformat()
    })
    
    return result

@app.get("/api/agents/status")
async def get_agents_status():
    """Get status of all AI agents"""
    return {
        agent_type.value: {
            "active": agent.is_active,
            "type": agent_type.value
        }
        for agent_type, agent in ai_system.agents.items()
    }

# ============================================================================
# SALES ENDPOINTS
# ============================================================================

@app.post("/api/leads")
async def create_lead(lead_data: LeadCreate):
    """Create new lead and let AI agent process it"""
    lead = Lead(
        id=f"LEAD-{datetime.now().timestamp()}",
        name=lead_data.name,
        email=lead_data.email,
        company=lead_data.company,
        phone=lead_data.phone,
        status=LeadStatus.WARM,
        source=lead_data.source,
        created_at=datetime.now(),
        last_contact=datetime.now(),
        notes=[],
        estimated_value=lead_data.estimated_value
    )
    
    # Let sales agent process
    sales_agent = ai_system.agents[AgentType.SALES]
    result = await sales_agent.send_quote(lead)
    
    await broadcast_update({
        "type": "new_lead",
        "lead": lead_data.dict(),
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "success", "lead_id": lead.id, "result": result}

@app.get("/api/leads")
async def get_leads():
    """Get all leads"""
    # In production, fetch from database
    return {"leads": [], "count": 0}

@app.post("/api/leads/{lead_id}/follow-up")
async def follow_up_lead(lead_id: str):
    """Trigger AI to follow up with a lead"""
    sales_agent = ai_system.agents[AgentType.SALES]
    result = await sales_agent.execute_task(
        f"Follow up with lead {lead_id}",
        {"lead_id": lead_id}
    )
    return result

# ============================================================================
# FINANCE ENDPOINTS
# ============================================================================

@app.post("/api/invoices")
async def create_invoice(invoice_data: InvoiceCreate):
    """Create and send invoice"""
    invoice = Invoice(
        id=f"INV-{int(datetime.now().timestamp())}",
        client_name=invoice_data.client_name,
        amount=invoice_data.amount,
        status="sent",
        sent_date=datetime.now(),
        due_date=datetime.now() + timedelta(days=invoice_data.due_days),
        paid_date=None,
        items=invoice_data.items
    )
    
    finance_agent = ai_system.agents[AgentType.FINANCE]
    result = await finance_agent.execute_task(
        f"Send invoice {invoice.id}",
        {"invoice": invoice.__dict__}
    )
    
    await broadcast_update({
        "type": "invoice_sent",
        "invoice_id": invoice.id,
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "success", "invoice_id": invoice.id}

@app.get("/api/invoices")
async def get_invoices():
    """Get all invoices"""
    return {"invoices": [], "total": 0, "paid": 0, "pending": 0}

@app.post("/api/invoices/{invoice_id}/payment-reminder")
async def send_payment_reminder(invoice_id: str):
    """Send automated payment reminder"""
    finance_agent = ai_system.agents[AgentType.FINANCE]
    result = await finance_agent.execute_task(
        f"Send payment reminder for {invoice_id}",
        {"invoice_id": invoice_id}
    )
    return result

# ============================================================================
# LOGISTICS ENDPOINTS
# ============================================================================

@app.get("/api/inventory")
async def get_inventory():
    """Get current inventory status"""
    logistics_agent = ai_system.agents[AgentType.LOGISTICS]
    result = await logistics_agent.check_inventory()
    return result

@app.post("/api/inventory/reorder")
async def reorder_inventory(quantity: int = 10):
    """Trigger automatic reorder"""
    logistics_agent = ai_system.agents[AgentType.LOGISTICS]
    result = await logistics_agent.reorder_stock(quantity)
    
    await broadcast_update({
        "type": "inventory_reorder",
        "quantity": quantity,
        "timestamp": datetime.now().isoformat()
    })
    
    return result

# ============================================================================
# INSTALLATION ENDPOINTS
# ============================================================================

@app.post("/api/installations")
async def schedule_installation(install_data: InstallationCreate):
    """Schedule new installation"""
    installation = Installation(
        id=f"INST-{int(datetime.now().timestamp())}",
        client_name=install_data.client_name,
        address=install_data.address,
        scheduled_date=datetime.fromisoformat(install_data.scheduled_date),
        contractor_id=install_data.contractor_id,
        status="scheduled",
        box_serial_numbers=install_data.box_serial_numbers,
        notes=install_data.notes
    )
    
    contractor_agent = ai_system.agents[AgentType.CONTRACTOR]
    result = await contractor_agent.schedule_installation(installation)
    
    await broadcast_update({
        "type": "installation_scheduled",
        "installation_id": installation.id,
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "success", "installation_id": installation.id}

@app.get("/api/installations")
async def get_installations():
    """Get all scheduled installations"""
    return {"installations": [], "upcoming": 8, "completed": 37}

# ============================================================================
# SUPPORT ENDPOINTS
# ============================================================================

@app.post("/api/support/tickets")
async def create_support_ticket(ticket_data: Dict):
    """Create support ticket and let AI handle it"""
    support_agent = ai_system.agents[AgentType.SUPPORT]
    result = await support_agent.process_support_ticket(ticket_data)
    
    await broadcast_update({
        "type": "support_ticket",
        "ticket": ticket_data,
        "timestamp": datetime.now().isoformat()
    })
    
    return result

@app.get("/api/support/system-health")
async def get_system_health():
    """Get health status of deployed AI boxes"""
    support_agent = ai_system.agents[AgentType.SUPPORT]
    result = await support_agent.monitor_systems()
    return result

# ============================================================================
# AUTONOMOUS MODE
# ============================================================================

@app.post("/api/system/start-autonomous")
async def start_autonomous_mode():
    """Start the system in fully autonomous mode"""
    # Run in background task
    asyncio.create_task(ai_system.start_autonomous_mode())
    
    await broadcast_update({
        "type": "system_status",
        "status": "autonomous_mode_started",
        "timestamp": datetime.now().isoformat()
    })
    
    return {"status": "Autonomous mode activated", "message": "System running 24/7"}

@app.get("/api/system/health")
async def system_health():
    """Check system health"""
    return {
        "status": "healthy",
        "agents_online": len(ai_system.agents),
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# EMAIL INTEGRATION (Placeholder)
# ============================================================================

@app.post("/api/email/check")
async def check_emails():
    """Check for new emails and process with AI"""
    # In production: connect to IMAP, fetch emails
    # For now, simulated
    sales_agent = ai_system.agents[AgentType.SALES]
    result = await sales_agent.process_enquiry({
        "from": "client@example.com",
        "subject": "AI Security Enquiry",
        "body": "Interested in your NVIDIA AI boxes"
    })
    return result

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║              A&I ARMOUR API SERVER                        ║
    ║                                                           ║
    ║  Starting server at http://localhost:8000                ║
    ║  Dashboard: http://localhost:8000                        ║
    ║  API Docs: http://localhost:8000/docs                    ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
