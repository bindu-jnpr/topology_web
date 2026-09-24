from pydantic import BaseModel
from typing import List, Optional

class VlanEntry(BaseModel):
    vlan_id: int
    name: str
    subnet: str

class Device(BaseModel):
    name: str
    type: str                        # SSR | SRX | EX | AP
    router_id: Optional[str] = None
    loopback: Optional[str] = None
    vlans: List[VlanEntry] = []

class Link(BaseModel):
    from_device: str
    to_device: str
    from_iface: str
    to_iface: str
    ip_from: Optional[str] = None
    ip_to: Optional[str] = None
    ospf_area: Optional[str] = None

class Topology(BaseModel):
    name: str
    scenario: str
    devices: List[Device]
    links: List[Link]
    test_cases: List[str] = []

class GenerateRequest(BaseModel):
    scenario: str

class ModifyRequest(BaseModel):
    id: int
    instruction: str

class FeedbackRequest(BaseModel):
    id: int
    good: bool
