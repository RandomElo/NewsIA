ANALYSE_CLUSTERS_INSTRUCTION = """You are given a set of clusters, each labeled by an integer. Group them into 9 to 12 topics and produce a JSON entry for each topic with these keys:
- "id": a unique string identifier for this topic (e.g. "1", "2", ...).
- "title": a concise, factual title (8 to 15 words) that reflects the main theme of the topic, written in the style of a television news bulletin, in French.
- "cluster_ids": a list of one or more HDBSCAN cluster numbers (as strings) that belong to this topic.
- "questions": a list of 6 to 10 diverse, self-contained questions covering different angles of the topic (causes, consequences, key actors, context, reactions, outlook), written in French; these will be used to retrieve relevant articles via semantic search.

Additional rules:
1. Only include 7 to 10 topics. If a cluster is overly heterogeneous, pick the single most interesting subject. If a cluster is too niche or irrelevant (including any sports topics), skip it, otherwise the selection criteria is from the perspective of a TV news editorial.
2. For cybersecurity clusters: only keep topics about major, high-impact events (large-scale breaches, attacks on critical infrastructure, nation-state operations, landmark regulation/court rulings). Skip routine vulnerability disclosures, individual CVEs, or minor patch announcements — these are not TV-news-worthy on their own.
3. Each question must make sense on its own, without referring to "this investigation," "this report," etc.
4. Do not output any text outside the JSON array.
5. At the end of the JSON array, add a key "importance_order" whose value is a list of the chosen topic "id" values sorted by importance (most important first). The importance order should reflect global newsworthiness: international impact, number of people affected, novelty, and urgency.
6. If multiple clusters cover the same underlying event or topic, merge them into a single topic by listing all their cluster numbers in "cluster_ids" rather than creating separate topics.
7. Do NOT create any topic about financial markets, stock exchange movements, company earnings, or general economic/business news — these clusters must be entirely excluded from the output, even if they seem important. This includes routine market recaps as well as major financial events (crashes, rate decisions, bank failures, etc.): all financial/economic clusters are out of scope for this selection, with no exception.
Return exactly that JSON—nothing else."""

ANALYSE_CLUSTERS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cluster_schema",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "clusters": {
                    "type": "array",
                    "description": "List of topics, each representing a set of related questions.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique identifier for this topic."},
                            "title": {"type": "string", "description": "A concise newspaper-style headline."},
                            "cluster_ids": {
                                "type": "array",
                                "description": "List of HDBSCAN cluster numbers merged into this topic.",
                                "items": {"type": "string"}
                            },
                            "questions": {
                                "type": "array",
                                "description": "A list of independent questions.",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["id", "title", "cluster_ids", "questions"],
                        "additionalProperties": False
                    }
                },
                "importance_order": {
                    "type": "array",
                    "description": "Topic ids sorted by importance (most important first).",
                    "items": {"type": "string"}
                }
            },
            "required": ["clusters", "importance_order"],
            "additionalProperties": False
        }
    }
}