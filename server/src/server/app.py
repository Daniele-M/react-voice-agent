import uvicorn
import json
import asyncio

from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from langchain_openai_voice import OpenAIVoiceReactAgent


from server.utils import websocket_stream
from server.prompt import INSTRUCTIONS
from server.tools import TOOLS


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    browser_receive_stream = websocket_stream(websocket)

    agent = OpenAIVoiceReactAgent(
        model="gpt-realtime",
        tools=TOOLS,
        instructions=INSTRUCTIONS,
    )

    agent_task = None

    async def handle_event(event):
        nonlocal agent_task
        if isinstance(event, str):
            event = json.loads(event)

        print("Evento ricevuto:", event.get("type"))
        #if agent_task and not agent_task.done():
        #    agent_task.cancel()

    async def start_agent():
        nonlocal agent_task

        if agent_task and not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                print("Vecchio task dell'agente chiuso")

        agent_task = asyncio.create_task(agent.aconnect(browser_receive_stream, handle_event))
        print("Agente avviato")

    await start_agent()  

    try:
        while True:
           await asyncio.sleep(0.5)  # mantiene la connessione attiva
    finally:
        if agent_task and not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                print("Task dell'agente chiuso in cleanup")      


async def homepage(request):
    with open("src/server/static/index.html") as f:
        html = f.read()
        return HTMLResponse(html)


# catchall route to load files from src/server/static


routes = [Route("/", homepage), WebSocketRoute("/ws", websocket_endpoint)]

app = Starlette(debug=True, routes=routes)

app.mount("/", StaticFiles(directory="src/server/static"), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
