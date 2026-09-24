from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from generator import generate, modify
from database import init_db, save_topology, get_topology, save_feedback
from schemas import GenerateRequest, ModifyRequest, FeedbackRequest

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize the database
    init_db()
    yield
    # Shutdown: clean up if needed

app = FastAPI(title="Juniper Topology Generator", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/generate")
def generate_topology(req: GenerateRequest):
    if not req.scenario.strip():
        raise HTTPException(status_code=400, detail="Scenario cannot be empty")
    try:
        topo = generate(req.scenario)
        topo_json = topo.model_dump_json()
        topo_id = save_topology(req.scenario, topo_json)
        return {"id": topo_id, "topology": topo.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/modify")
def modify_topology(req: ModifyRequest):
    existing = get_topology(req.id)
    if not existing:
        raise HTTPException(status_code=404, detail="Topology not found")
    try:
        topo = modify(existing, req.instruction)
        topo_json = topo.model_dump_json()
        new_id = save_topology(f"[MODIFIED] {req.instruction}", topo_json)
        return {"id": new_id, "topology": topo.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
def feedback(req: FeedbackRequest):
    save_feedback(req.id, req.good)
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
