import uvicorn
import asyncio
import json
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

    control_queue = asyncio.Queue()

    # Stream originale dal browser
    browser_stream = websocket_stream(websocket)

    # Stream combinato: merge tra browser e control queue
    async def combined_stream():
        browser_task = asyncio.create_task(browser_stream.__anext__())
        queue_task = asyncio.create_task(control_queue.get())

        while True:
            done, _ = await asyncio.wait(
                [browser_task, queue_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if browser_task in done:
                try:
                    data = browser_task.result()
                    yield data
                except StopAsyncIteration:
                    break
                browser_task = asyncio.create_task(browser_stream.__anext__())

            if queue_task in done:
                data = queue_task.result()
                yield json.dumps(data)
                queue_task = asyncio.create_task(control_queue.get())

    agent = OpenAIVoiceReactAgent(
        model="gpt-realtime",
        tools=TOOLS,
        instructions=INSTRUCTIONS,
    )

    is_speaking = False

    async def log_and_send(text):
        nonlocal is_speaking

        text_json = json.loads(text)

        if "response.audio.delta" in text or "response.created" in text:
            is_speaking = True
        elif "response.audio.done" in text or "response.done" in text:
            is_speaking = False

        if "speech_started" in text and is_speaking:
            print("🛑 Utente parla — interrompo generazione in corso")
            is_speaking = False
            await control_queue.put({"type": "response.cancel"})
            await websocket.send_text(json.dumps({"type": "client.stop_audio"}))
        print("Inviando chunk al browser:", text[:100])  # solo primi 100 caratteri
        await websocket.send_text(text)

    await agent.aconnect(combined_stream(), log_and_send)


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
