import os


class GraphRepository:
    def __init__(self, uri=None, username=None, password=None, database=None):
        self.uri = uri or os.environ.get("NEO4J_URI")
        self.username = username or os.environ.get("NEO4J_USERNAME")
        self.password = password or os.environ.get("NEO4J_PASSWORD")
        self.database = database or os.environ.get("NEO4J_DATABASE")
        self._driver = None

    def enabled(self):
        return bool(self.uri)

    def _get_driver(self):
        if not self.enabled():
            return None
        if self._driver is None:
            from neo4j import GraphDatabase

            auth = (self.username, self.password) if self.username else None
            self._driver = GraphDatabase.driver(self.uri, auth=auth)
        return self._driver

    def upsert_document_facts(self, doc_name, chunks):
        driver = self._get_driver()
        if not driver:
            return {"written": 0}
        facts = self._extract_lightweight_facts(doc_name, chunks)
        with self._session(driver) as session:
            for fact in facts:
                session.run(
                    """
                    MERGE (s:Entity {name: $subject})
                    MERGE (o:Entity {name: $object})
                    MERGE (d:Document {name: $source})
                    MERGE (s)-[r:RELATED_TO {relationship: $relationship}]->(o)
                    SET r.source = $source
                    MERGE (d)-[:MENTIONS]->(s)
                    MERGE (d)-[:MENTIONS]->(o)
                    """,
                    **fact,
                )
        return {"written": len(facts)}

    def search_facts(self, query, limit=5):
        driver = self._get_driver()
        if not driver:
            return {"facts": []}
        with self._session(driver) as session:
            rows = session.run(
                """
                MATCH (s:Entity)-[r:RELATED_TO]->(o:Entity)
                WHERE toLower(s.name) CONTAINS toLower($search_text)
                   OR toLower(o.name) CONTAINS toLower($search_text)
                   OR toLower(r.relationship) CONTAINS toLower($search_text)
                RETURN s.name AS subject, r.relationship AS relationship, o.name AS object, r.source AS source
                LIMIT $limit
                """,
                search_text=query,
                limit=limit,
            )
            return {"facts": [dict(row) for row in rows]}

    def _session(self, driver):
        if self.database:
            return driver.session(database=self.database)
        return driver.session()

    def _extract_lightweight_facts(self, doc_name, chunks):
        facts = []
        for chunk in chunks[:20]:
            text = chunk.get("text", "").strip()
            if " requires " in text.lower():
                left, right = text.split(" requires ", 1) if " requires " in text else text.split(" Requires ", 1)
                facts.append(
                    {
                        "subject": left.strip()[:120],
                        "relationship": "REQUIRES",
                        "object": right.strip().split(".")[0][:120],
                        "source": doc_name,
                    }
                )
        return facts
