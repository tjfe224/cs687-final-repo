from fastapi import FastAPI
import time
import os

app = FastAPI()

start_time = time.time()

@app.get("/")
def read_root():
    # basic request
    return {"message": "hello from py-light", "uptime_sec": time.time() - start_time}

@app.get("/heavy-init")
def heavy_init():
    # simulate some new heavy work
    time.sleep(1.5)
    return {"message": "heavy init simulated"}
