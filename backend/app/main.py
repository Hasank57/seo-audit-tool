from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
import os
import asyncio
import aiohttp
import ssl
from urllib.parse import urlparse
from typing import Dict, List, Optional
import re

app = FastAPI(
    title="SEO Audit Tool",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class SEOAnalysisRequest(BaseModel):
    url: HttpUrl

class GeoAnalysisRequest(BaseModel):
    domain: str

class TrafficEstimateRequest(BaseModel):
    url: HttpUrl

class SEOAnalysisResponse(BaseModel):
    url: str
    score: int
    title: Optional[str]
    meta_description: Optional[str]
    headings: Dict[str, List[str]]
    images_without_alt: int
    internal_links: int
    external_links: int
    has_ssl: bool
    load_time_ms: Optional[float]
    recommendations: List[str]

# Root endpoint - MUST return simple JSON for Railway healthcheck
@app.get("/")
async def root():
    return {
        "message": "SEO Audit Tool API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "seo_analyze": "POST /api/seo/analyze",
            "geo_analyze": "POST /api/geo/analyze", 
            "traffic_estimate": "POST /api/traffic/estimate"
        }
    }

# Health check - Railway expects 200 OK
@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"status": "healthy", "service": "seo-audit-api"},
        status_code=200
    )

# Real SEO Analysis functionality
async def fetch_page_content(url: str) -> tuple:
    """Fetch page content and return HTML + response time"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, 
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={'User-Agent': 'Mozilla/5.0 (compatible; SEOAuditBot/1.0)'}
            ) as response:
                html = await response.text()
                load_time = (asyncio.get_event_loop().time() - start_time) * 1000
                return html, response.status, load_time
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

def parse_seo_elements(html: str, base_url: str) -> dict:
    """Parse HTML and extract SEO elements"""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    
    # Title
    title_tag = soup.find('title')
    title = title_tag.get_text(strip=True) if title_tag else None
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    meta_description = meta_desc.get('content') if meta_desc else None
    
    # Headings
    headings = {
        'h1': [h.get_text(strip=True) for h in soup.find_all('h1')],
        'h2': [h.get_text(strip=True) for h in soup.find_all('h2')],
        'h3': [h.get_text(strip=True) for h in soup.find_all('h3')]
    }
    
    # Images without alt text
    images = soup.find_all('img')
    images_without_alt = len([img for img in images if not img.get('alt')])
    
    # Links
    links = soup.find_all('a', href=True)
    internal_links = 0
    external_links = 0
    
    for link in links:
        href = link['href']
        if href.startswith('http'):
            if base_domain in href:
                internal_links += 1
            else:
                external_links += 1
        elif href.startswith('/') or not href.startswith('#'):
            internal_links += 1
    
    # SSL check
    has_ssl = base_url.startswith('https')
    
    return {
        'title': title,
        'meta_description': meta_description,
        'headings': headings,
        'images_without_alt': images_without_alt,
        'internal_links': internal_links,
        'external_links': external_links,
        'has_ssl': has_ssl
    }

def generate_recommendations(data: dict) -> List[str]:
    """Generate SEO recommendations based on analysis"""
    recommendations = []
    
    if not data['title']:
        recommendations.append("❌ Missing page title - Add a descriptive <title> tag")
    elif len(data['title']) > 60:
        recommendations.append("⚠️ Title too long (>60 chars) - May be truncated in search results")
    elif len(data['title']) < 30:
        recommendations.append("⚠️ Title too short - Consider adding more descriptive keywords")
    
    if not data['meta_description']:
        recommendations.append("❌ Missing meta description - Add a compelling meta description")
    elif len(data['meta_description']) > 160:
        recommendations.append("⚠️ Meta description too long (>160 chars)")
    
    h1_count = len(data['headings']['h1'])
    if h1_count == 0:
        recommendations.append("❌ Missing H1 tag - Add one main H1 heading")
    elif h1_count > 1:
        recommendations.append("⚠️ Multiple H1 tags - Consider using only one H1 per page")
    
    if data['images_without_alt'] > 0:
        recommendations.append(f"⚠️ {data['images_without_alt']} images missing alt text - Add descriptive alt attributes")
    
    if not data['has_ssl']:
        recommendations.append("❌ No SSL certificate - Migrate to HTTPS for better rankings")
    
    if data['internal_links'] < 3:
        recommendations.append("💡 Low internal linking - Add more internal links to improve navigation")
    
    if not recommendations:
        recommendations.append("✅ Great job! No major SEO issues found.")
    
    return recommendations

def calculate_seo_score(data: dict) -> int:
    """Calculate SEO score from 0-100"""
    score = 100
    
    if not data['title']: score -= 15
    if not data['meta_description']: score -= 10
    if len(data['headings']['h1']) != 1: score -= 10
    if data['images_without_alt'] > 0: score -= min(data['images_without_alt'] * 2, 20)
    if not data['has_ssl']: score -= 20
    if data['internal_links'] < 3: score -= 5
    
    return max(0, score)

@app.post("/api/seo/analyze", response_model=SEOAnalysisResponse)
async def analyze_seo(request: SEOAnalysisRequest):
    """
    Perform comprehensive SEO analysis on a URL
    """
    url_str = str(request.url)
    
    try:
        html, status_code, load_time = await fetch_page_content(url_str)
        
        if status_code != 200:
            raise HTTPException(status_code=400, detail=f"URL returned status code {status_code}")
        
        seo_data = parse_seo_elements(html, url_str)
        seo_data['load_time_ms'] = round(load_time, 2)
        
        recommendations = generate_recommendations(seo_data)
        score = calculate_seo_score(seo_data)
        
        return {
            "url": url_str,
            "score": score,
            "title": seo_data['title'],
            "meta_description": seo_data['meta_description'],
            "headings": seo_data['headings'],
            "images_without_alt": seo_data['images_without_alt'],
            "internal_links": seo_data['internal_links'],
            "external_links": seo_data['external_links'],
            "has_ssl": seo_data['has_ssl'],
            "load_time_ms": seo_data['load_time_ms'],
            "recommendations": recommendations
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/geo/analyze")
async def analyze_geo(request: GeoAnalysisRequest):
    """
    Analyze geographic/server location of a domain
    """
    import socket
    import requests
    
    try:
        # Remove protocol if present
        domain = request.domain.replace('https://', '').replace('http://', '').split('/')[0]
        
        # Get IP address
        ip_address = socket.gethostbyname(domain)
        
        # Get geolocation data (using ip-api.com free tier)
        geo_response = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=5)
        geo_data = geo_response.json()
        
        return {
            "domain": domain,
            "ip_address": ip_address,
            "location": {
                "country": geo_data.get("country"),
                "region": geo_data.get("regionName"),
                "city": geo_data.get("city"),
                "zip": geo_data.get("zip"),
                "lat": geo_data.get("lat"),
                "lon": geo_data.get("lon"),
                "timezone": geo_data.get("timezone"),
                "isp": geo_data.get("isp")
            },
            "status": "success"
        }
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Could not resolve domain: {request.domain}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/traffic/estimate")
async def estimate_traffic(request: TrafficEstimateRequest):
    """
    Estimate website traffic based on various metrics
    Note: This uses heuristics since real traffic data requires paid APIs
    """
    url_str = str(request.url)
    
    try:
        # Fetch basic page data
        html, status_code, load_time = await fetch_page_content(url_str)
        seo_data = parse_seo_elements(html, url_str)
        
        # Heuristic estimation based on SEO factors
        # This is a simplified model for demonstration
        base_score = 0
        
        # Domain age proxy (simplified)
        domain_age_factor = 50  # Placeholder
        
        # Content volume estimation
        content_length = len(html)
        pages_estimated = max(1, content_length // 50000)  # Rough estimate
        
        # SEO quality factor
        seo_score = calculate_seo_score(seo_data)
        
        # Estimate monthly visits (very rough heuristic)
        estimated_monthly_visits = (pages_estimated * 100) * (seo_score / 100) * (domain_age_factor / 50)
        estimated_monthly_visits = int(max(100, estimated_monthly_visits))
        
        # Estimate page views (assume 1.5 pages per visit)
        estimated_page_views = int(estimated_monthly_visits * 1.5)
        
        return {
            "url": url_str,
            "estimated_monthly_visits": estimated_monthly_visits,
            "estimated_monthly_pageviews": estimated_page_views,
            "confidence": "low",
            "methodology": "Heuristic estimation based on site structure, SEO score, and content volume",
            "factors": {
                "estimated_pages": pages_estimated,
                "seo_score": seo_score,
                "content_quality_indicators": {
                    "has_title": bool(seo_data['title']),
                    "has_meta_description": bool(seo_data['meta_description']),
                    "heading_structure": "Good" if len(seo_data['headings']['h1']) == 1 else "Needs improvement"
                }
            },
            "note": "For accurate traffic data, integrate with SimilarWeb, SEMrush, or Ahrefs APIs"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Traffic estimation failed: {str(e)}")

# Railway deployment configuration
if __name__ == "__main__":
    import uvicorn
    # Railway sets PORT env var, default to 8000 for local dev
    port = int(os.environ.get("PORT", 8000))
    # Railway requires 0.0.0.0 binding
    uvicorn.run(
        "main:app",  # Use string reference for proper reload support
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
