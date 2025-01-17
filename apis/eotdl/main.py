from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, datasets, tags

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(tags.router)


@app.get("/", name="home", include_in_schema=False)
async def root():
    return {
        'name': 'eotdl',
        'version': '0.0.1',
        'description': 'Earth Observation Training Data Lab',
        'contact': 'it@earthpulse.es'
    }