"""Specialized domain sub-agents.

Each sub-agent detects a specific repo archetype via signals, then
extracts domain-specific topology, proposes diagrams + documentation
sections, and attaches evidence pointers with confidence scores.

Sub-agents:
- **MicroservicesAgent**: Docker Compose / K8s / service mesh topology.
- **EventDrivenAgent**: Kafka / SQS / EventBridge / RabbitMQ flows.
- **MLAgent**: Training / inference / RAG / vector DB pipelines.
- **DataEngineeringAgent**: Airflow / dbt / Spark DAG lineage.
- **InfraAgent**: Terraform / Helm / K8s / Pulumi resource graphs.
"""

from .microservices_agent import MicroservicesAgent
from .event_driven_agent import EventDrivenAgent
from .ml_agent import MLAgent
from .data_engineering_agent import DataEngineeringAgent
from .infra_agent import InfraAgent

__all__ = [
    "MicroservicesAgent",
    "EventDrivenAgent",
    "MLAgent",
    "DataEngineeringAgent",
    "InfraAgent",
]
