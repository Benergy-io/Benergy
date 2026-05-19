from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Benergy backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}
