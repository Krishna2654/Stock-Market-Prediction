from fastapi import APIRouter, HTTPException
from typing import List, Dict
from app.models.schemas import InstrumentConfig
from app.api.deps import configured_instruments, set_current_provider, current_provider_name, providers

router = APIRouter(prefix="/api/instruments", tags=["instruments"])

@router.get("/", response_model=List[InstrumentConfig])
def get_instruments():
    return configured_instruments

@router.post("/", response_model=InstrumentConfig)
def add_instrument(inst: InstrumentConfig):
    if len(configured_instruments) >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 instruments can be configured at a time.")
    
    # Check duplicate
    for existing in configured_instruments:
        if existing.symbol.upper() == inst.symbol.upper() or existing.ticker.upper() == inst.ticker.upper():
            raise HTTPException(status_code=400, detail=f"Instrument '{inst.symbol}' or ticker '{inst.ticker}' already exists.")
            
    configured_instruments.append(inst)
    return inst

@router.delete("/{symbol}")
def delete_instrument(symbol: str):
    global configured_instruments
    initial_len = len(configured_instruments)
    configured_instruments[:] = [i for i in configured_instruments if i.symbol.upper() != symbol.upper()]
    if len(configured_instruments) == initial_len:
        raise HTTPException(status_code=404, detail=f"Instrument '{symbol}' not found.")
    return {"message": f"Instrument '{symbol}' removed successfully"}

@router.get("/provider")
def get_provider_status():
    return {
        "current_provider": current_provider_name,
        "available_providers": list(providers.keys())
    }

@router.post("/provider/{provider_name}")
def change_provider(provider_name: str):
    if provider_name not in providers:
        raise HTTPException(status_code=400, detail=f"Provider '{provider_name}' not available. Choose from {list(providers.keys())}")
    set_current_provider(provider_name)
    return {"message": f"Data provider switched to {provider_name}"}
