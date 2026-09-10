"""
Builds a person -> document -> pattern -> document -> person style graph
for a given identity, using NetworkX as the in-memory graph representation.

For a production-scale deployment, this graph would live in a real graph
database (Neo4j / Amazon Neptune) so multi-hop queries stay fast as the
number of cases grows; NetworkX is a fine substitute at prototype scale.
"""
import networkx as nx
from sqlalchemy.orm import Session

from app.db.models import CheckpointEvent, Document, FraudFamily, Identity
from app.schemas.fraud import FraudNetworkResponse, GraphEdge, GraphNode


class FraudNetworkService:
    def build(self, db: Session, identity_id: str) -> FraudNetworkResponse:
        graph = nx.Graph()

        identity = db.query(Identity).filter(Identity.identity_id == identity_id).first()
        if identity is None:
            return FraudNetworkResponse(
                identity_id=identity_id, connected_cases=0, common_pattern=None,
                checkpoints_involved=[], nodes=[], edges=[],
            )

        graph.add_node(identity.identity_id, label=identity.name, type="person")

        docs = db.query(Document).filter(Document.identity_id == identity.identity_id).all()
        family_ids = set()
        for doc in docs:
            graph.add_node(doc.document_number, label=f"{doc.document_type} {doc.document_number}", type="document")
            graph.add_edge(identity.identity_id, doc.document_number)
            if doc.fraud_family_id:
                family_ids.add(doc.fraud_family_id)

        common_pattern = None
        checkpoints_involved: set[str] = set()

        for family_id in family_ids:
            family = db.query(FraudFamily).filter(FraudFamily.fraud_family_id == family_id).first()
            if family is None:
                continue
            common_pattern = family.common_pattern
            graph.add_node(family.fraud_family_id, label=f"Suspicious Pattern {family.fraud_family_id}", type="pattern")

            for doc in docs:
                if doc.fraud_family_id == family_id:
                    graph.add_edge(doc.document_number, family.fraud_family_id)

            siblings = db.query(Document).filter(Document.fraud_family_id == family_id).all()
            for sib in siblings:
                graph.add_node(sib.document_number, label=f"{sib.document_type} {sib.document_number}", type="document")
                graph.add_edge(family.fraud_family_id, sib.document_number)

                if sib.identity_id and sib.identity_id != identity.identity_id:
                    sib_identity = db.query(Identity).filter(Identity.identity_id == sib.identity_id).first()
                    if sib_identity:
                        graph.add_node(sib_identity.identity_id, label=sib_identity.name, type="person")
                        graph.add_edge(sib.document_number, sib_identity.identity_id)

        events = db.query(CheckpointEvent).filter(CheckpointEvent.identity_id == identity.identity_id).all()
        for event in events:
            checkpoints_involved.add(event.checkpoint_name)
            graph.add_node(event.checkpoint_name, label=event.checkpoint_name, type="checkpoint")
            graph.add_edge(identity.identity_id, event.checkpoint_name)

        nodes = [GraphNode(id=n, label=data.get("label", n), type=data.get("type", "unknown")) for n, data in graph.nodes(data=True)]
        edges = [GraphEdge(source=u, target=v) for u, v in graph.edges()]

        # "Connected cases" = number of distinct documents reachable through
        # the shared fraud pattern, excluding the identity's own document(s).
        connected_cases = sum(
            1 for n, data in graph.nodes(data=True) if data.get("type") == "document"
        )

        return FraudNetworkResponse(
            identity_id=identity.identity_id,
            connected_cases=connected_cases,
            common_pattern=common_pattern,
            checkpoints_involved=sorted(checkpoints_involved),
            nodes=nodes,
            edges=edges,
        )


def get_fraud_network_service() -> FraudNetworkService:
    return FraudNetworkService()
