from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import DeviceCreate, DeviceUpdate, DeviceOut
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/api/devices", tags=["devices"], dependencies=[Depends(get_current_user)])
admin_dep = [Depends(require_admin)]


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return db.query(Device).order_by(Device.name).all()


@router.post("", response_model=DeviceOut, status_code=201, dependencies=admin_dep)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data["check_type"] == "tcp" and not data.get("tcp_port"):
        data["tcp_port"] = 443
    if data["check_type"] != "tcp":
        data["tcp_port"] = None
    existing = (
        db.query(Device)
        .filter(Device.ip == data["ip"], Device.check_type == data["check_type"], Device.tcp_port.is_(None) if data["tcp_port"] is None else Device.tcp_port == data["tcp_port"])
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um equipamento cadastrado com esse IP/host (e porta)")

    device = Device(**data)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.put("/{device_id}", response_model=DeviceOut, dependencies=admin_dep)
def update_device(device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, field, value)

    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=204, dependencies=admin_dep)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    db.delete(device)
    db.commit()
    return None
