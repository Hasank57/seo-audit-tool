from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SEO Audit Tool",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Allow all origins for Railway deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "SEO Audit Tool API",
        "docs": "/docs",
        "endpoints": ["/api/seo/analyze", "/api/geo/analyze", "/api/traffic/estimate"]
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "seo-audit-api"}

# Placeholder for future routes
@app.post("/api/seo/analyze")
async def analyze_seo(url: str):
    return {"url": url, "status": "placeholder - will add real logic"}

@app.post("/api/geo/analyze")
async def analyze_geo(domain: str):
    return {"domain": domain, "status": "placeholder - will add real logic"}

@app.post("/api/traffic/estimate")
async def estimate_traffic(url: str):
    return {"url": url, "status": "placeholder - will add real logic"}
