import json
import re
import os
import boto3
from schemas import Topology
from database import find_similar

SYSTEM_PROMPT = """You are a Juniper network topology expert.
When given a test scenario, generate a minimal but complete topology using ONLY these devices: SSR, SRX, EX, AP.

Return ONLY raw JSON — no explanation, no markdown code blocks, just the JSON object.

Example output:
{
  "name": "OSPF Basic Topology",
  "scenario": "Test OSPF between SSR and SRX",
  "devices": [
    {"name": "SSR1", "type": "SSR", "router_id": "1.1.1.1", "loopback": "1.1.1.1/32", "vlans": []},
    {"name": "SRX1", "type": "SRX", "router_id": "2.2.2.2", "loopback": "2.2.2.2/32", "vlans": []}
  ],
  "links": [
    {
      "from_device": "SSR1",
      "to_device": "SRX1",
      "from_iface": "ge-0/0/0",
      "to_iface": "ge-0/0/0",
      "ip_from": "10.0.0.1/30",
      "ip_to": "10.0.0.2/30",
      "ospf_area": "0.0.0.0"
    }
  ],
  "test_cases": [
    "Verify OSPF neighborship between SSR1 and SRX1",
    "Check route propagation from SSR1 to SRX1",
    "Verify loopback reachability"
  ]
}

Rules:
- SSR, SRX, EX use interfaces: ge-0/0/0, ge-0/0/1, ge-0/0/2, ge-0/0/3
- AP uses: eth0, eth1
- Use 10.0.X.X/30 subnets for point-to-point links
- Use 192.168.X.X/24 for LAN/access segments
- Always include at least 3 relevant test_cases
- router_id must be unique per device (1.1.1.1, 2.2.2.2, 3.3.3.3 ...)
"""


def generate(scenario: str) -> Topology:
    # Let boto3 automatically find credentials from the environment
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-west-2")
    )

    similar = find_similar(scenario)
    extra = ""
    if similar:
        extra = "\n\nHere are similar past successful topologies for reference:\n"
        for s, t in similar:
            extra += f"\nScenario: {s}\nTopology: {t}\n"

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": f"{extra}\nGenerate a topology for this scenario: {scenario}"}
        ]
    })

    response = client.invoke_model(
        modelId=os.getenv("BEDROCK_MODEL_ID"),
        body=body
    )

    raw_text = json.loads(response["body"].read())["content"][0]["text"]

    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    json_str = match.group() if match else raw_text
    data = json.loads(json_str)

    return Topology(**data)


def modify(existing_json: str, instruction: str) -> Topology:
    # Let boto3 automatically find credentials from the environment
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-west-2")
    )

    prompt = f"Existing topology:\n{existing_json}\n\nModification request: {instruction}\n\nReturn the complete modified topology JSON (same structure, all fields). Do not return markdown, just raw JSON."

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    })

    response = client.invoke_model(
        modelId=os.getenv("BEDROCK_MODEL_ID"),
        body=body
    )

    raw_text = json.loads(response["body"].read())["content"][0]["text"]

    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    json_str = match.group() if match else raw_text
    data = json.loads(json_str)

    return Topology(**data)
